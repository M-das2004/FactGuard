"""Repair Engine: propose minimal candidate patches. Never overwrites the original.

Strategies, tried in this order:
  1. targeted rules     - e.g. startswith -> `in`, rename a misspelled name or API
  2. mutation search    - one small change at a time (operators, constants,
                          swapped methods); the first candidate that the
                          verification engine accepts wins
  3. optional LLM hook  - pass `llm_fn(prompt) -> str`; its answer is verified
                          exactly like every other candidate

Every candidate is only a suggestion until verify_candidate() accepts it.
"""
import ast
import difflib
import re

from .findings import ERROR, NAMING, API

_STARTS = re.compile(
    r"([A-Za-z_][\w\.\[\]]*)\.(startswith|endswith)\(\s*"
    r"(\"[^\"]*\"|'[^']*'|[A-Za-z_]\w*)\s*\)")


def make_diff(original, candidate):
    """Unified diff of the original and the candidate source."""
    return "".join(difflib.unified_diff(
        original.splitlines(True), candidate.splitlines(True),
        "original.py", "candidate.py"))


def _defined_names(source):
    tree = ast.parse(source)
    names = set(dir(__builtins__) if not isinstance(__builtins__, dict) else __builtins__)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
    return names


def propose_rule_repairs(source, requirement, findings):
    """Targeted, explainable repairs. Returns a list of candidate dictionaries."""
    candidates = []

    # Missing colon at the end of a block header (the most common syntax slip).
    try:
        ast.parse(source)
    except SyntaxError as exc:
        if exc.msg == "expected ':'" and exc.lineno:
            lines = source.splitlines()
            index = exc.lineno - 1
            if 0 <= index < len(lines) and not lines[index].rstrip().endswith(":"):
                lines[index] = lines[index].rstrip() + ":"
                candidates.append({
                    "strategy": "rule: add missing colon",
                    "description": f"Add the missing ':' at the end of line {exc.lineno}.",
                    "source": "\n".join(lines) + ("\n" if source.endswith("\n") else "")})
        return candidates

    # Requirement says "contains", code uses startswith/endswith.
    if re.search(r"contain|anywhere|includ|\bhas\b", (requirement or "").lower()):
        fixed = _STARTS.sub(lambda m: f"{m.group(3)} in {m.group(1)}", source)
        if fixed != source:
            candidates.append({
                "strategy": "rule: startswith/endswith -> in",
                "description": "Use an `in` check, because the requirement asks for text "
                               "that occurs anywhere in the value.",
                "source": fixed})

    names = None
    for finding in findings:
        if finding["severity"] != ERROR:
            continue
        message = finding["message"]
        if finding["label"] == NAMING:
            match = re.search(r"name '(\w+)'", message)
            if match:
                names = names or _defined_names(source)
                wrong = match.group(1)
                close = difflib.get_close_matches(wrong, names - {wrong}, n=1, cutoff=0.6)
                if close:
                    fixed = re.sub(rf"\b{wrong}\b", close[0], source)
                    candidates.append({
                        "strategy": "rule: rename undefined name",
                        "description": f"Rename '{wrong}' to the similar defined name "
                                       f"'{close[0]}'.",
                        "source": fixed})
        elif finding["label"] == API:
            hint = re.search(r"Did you mean '(\w+)'\?", message)
            missing = re.search(r"(?:attribute|^')'?(\w+)'", message)
            wrong = re.search(r"no attribute '(\w+)'|^'(\w+)' does not exist", message)
            if hint and wrong:
                wrong_name = wrong.group(1) or wrong.group(2)
                fixed = re.sub(rf"\b{wrong_name}\b", hint.group(1), source)
                candidates.append({
                    "strategy": "rule: fix API name",
                    "description": f"Replace '{wrong_name}' with the real name "
                                   f"'{hint.group(1)}' from the library.",
                    "source": fixed})
    unique, seen = [], {source}
    for item in candidates:
        if item["source"] not in seen:
            seen.add(item["source"])
            unique.append(item)
    return unique


# --- mutation search -------------------------------------------------------

_CMP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
        ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In,
        ast.Is: ast.IsNot, ast.IsNot: ast.Is}
_SYMBOL = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==",
           ast.NotEq: "!=", ast.In: "in", ast.NotIn: "not in", ast.Is: "is",
           ast.IsNot: "is not"}
_ATTR_SWAPS = {"startswith": "endswith", "endswith": "startswith",
               "lower": "upper", "upper": "lower", "lstrip": "rstrip", "rstrip": "lstrip"}
_NAME_SWAPS = {"min": "max", "max": "min", "any": "all", "all": "any"}


class _Mutator(ast.NodeTransformer):
    """Applies exactly one change: the `target`-th mutation site in the function."""

    def __init__(self, target, function):
        self.target, self.function = target, function
        self.in_target = function is None
        self.count, self.applied, self.description = -1, False, ""

    def _hit(self, text, line):
        self.count += 1
        if self.count == self.target:
            self.applied, self.description = True, f"line {line}: {text}"
            return True
        return False

    def visit_FunctionDef(self, node):
        before = self.in_target
        if self.function and node.name == self.function:
            self.in_target = True
        self.generic_visit(node)
        self.in_target = before
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        if self.in_target:
            for index, op in enumerate(node.ops):
                swap = _CMP.get(type(op))
                if swap and self._hit(
                        f"change '{_SYMBOL[type(op)]}' to '{_SYMBOL[swap]}'", node.lineno):
                    node.ops[index] = swap()
                    break
        return node

    def visit_Constant(self, node):
        if self.in_target and type(node.value) is int:
            if self._hit(f"change {node.value} to {node.value + 1}", node.lineno):
                return ast.copy_location(ast.Constant(node.value + 1), node)
            if self._hit(f"change {node.value} to {node.value - 1}", node.lineno):
                return ast.copy_location(ast.Constant(node.value - 1), node)
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if self.in_target and isinstance(node.op, (ast.Add, ast.Sub)):
            new = ast.Sub if isinstance(node.op, ast.Add) else ast.Add
            if self._hit(f"swap '{'+' if new is ast.Sub else '-'}' for "
                         f"'{'-' if new is ast.Sub else '+'}'", node.lineno):
                node.op = new()
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if self.in_target:
            new = ast.Or if isinstance(node.op, ast.And) else ast.And
            if self._hit(f"swap '{'and' if new is ast.Or else 'or'}' for "
                         f"'{'or' if new is ast.Or else 'and'}'", node.lineno):
                node.op = new()
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if self.in_target and isinstance(node.op, ast.Not):
            if self._hit("remove 'not'", node.lineno):
                return node.operand
        return node

    def visit_Attribute(self, node):
        self.generic_visit(node)
        if self.in_target and node.attr in _ATTR_SWAPS:
            if self._hit(f"use .{_ATTR_SWAPS[node.attr]}() instead of .{node.attr}()",
                         node.lineno):
                node.attr = _ATTR_SWAPS[node.attr]
        return node

    def visit_Name(self, node):
        if self.in_target and isinstance(node.ctx, ast.Load) and node.id in _NAME_SWAPS:
            if self._hit(f"use {_NAME_SWAPS[node.id]}() instead of {node.id}()", node.lineno):
                return ast.copy_location(ast.Name(_NAME_SWAPS[node.id], ast.Load()), node)
        return node


def iter_mutants(source, function=None, limit=80):
    """Yield (description, new_source) for single-change variants of the function."""
    for target in range(limit):
        tree = ast.parse(source)
        mutator = _Mutator(target, function)
        mutated = mutator.visit(tree)
        if not mutator.applied:
            return
        yield mutator.description, ast.unparse(ast.fix_missing_locations(mutated))



# --- optional LLM hook -----------------------------------------------------

def build_repair_prompt(requirement, source, findings, language="python"):
    """Structured prompt asking for a minimal patch, not a rewrite."""
    names = {"python": "Python", "c": "C", "cpp": "C++", "java": "Java"}
    name, fence = names.get(language, "Python"), {"cpp": "cpp"}.get(language, language)
    evidence = "\n".join(f"- [{f['label']}] line {f['line']}: {f['message']}"
                         for f in findings if f["severity"] == ERROR)
    return (
        f"You repair {name} code. Return ONLY the full corrected code in one "
        f"```{fence} block. Change as little as possible; keep the function name and "
        "signature.\n\n"
        f"Requirement:\n{requirement}\n\nCode:\n```{fence}\n{source}\n```\n\n"
        f"Evidence from automated checks:\n{evidence}\n")


def _extract_code(text):
    match = re.search(r"```[A-Za-z+]*\n(.*?)```", text, re.S)
    return (match.group(1) if match else text).strip() + "\n"


# --- orchestration ----------------------------------------------------------

def _why_not(tried, n_rules, n_mutants):
    """One sentence explaining why no repair was accepted (review finding F7)."""
    if not tried:
        return ("no candidate repair could be generated: no repair rule applies to this "
                "kind of fault and the small-change search produced nothing")
    counts = {}
    for item in tried:
        for part in item["reason"].replace("failed: ", "").split("; "):
            if part:
                counts[part] = counts.get(part, 0) + 1
    top = max(counts, key=counts.get) if counts else "unknown"
    return (f"{len(tried)} candidate(s) were tried ({n_rules} from rules, {n_mutants} from "
            f"small-change search) and none passed every check; the most common failed "
            f"check was: {top}")


def repair(source, requirement, findings, function, evaluate, *, llm_fn=None,
           max_mutants=60, language="python"):
    """Try repair strategies until `evaluate(candidate_source)` accepts one.

    `evaluate` must return the dictionary produced by verify_candidate().
    Returns {"accepted", "strategy", "description", "source", "diff",
    "verification", "tried": [...], "why_not": str}.
    """
    tried = []
    counts = {"rules": 0, "mutants": 0}
    native = language != "python"

    def attempt(strategy, description, candidate):
        if not native:
            try:
                ast.parse(candidate)
            except SyntaxError as exc:
                tried.append({"strategy": strategy, "description": description,
                              "accepted": False,
                              "reason": f"failed: candidate has a syntax error ({exc.msg})"})
                return None
        verification = evaluate(candidate)
        failed = [c["name"] for c in verification["checks"] if not c["passed"]]
        tried.append({"strategy": strategy, "description": description,
                      "accepted": verification["accepted"],
                      "reason": "" if verification["accepted"] else "failed: " + "; ".join(failed)})
        if verification["accepted"]:
            return {"accepted": True, "strategy": strategy, "description": description,
                    "source": candidate, "diff": make_diff(source, candidate),
                    "verification": verification, "tried": tried, "why_not": ""}
        return None

    if native:
        from .multilang import iter_text_mutants, native_rule_repairs
        rules = native_rule_repairs(source, requirement, findings, language)
    else:
        rules = propose_rule_repairs(source, requirement, findings)
    for item in rules:
        counts["rules"] += 1
        done = attempt(item["strategy"], item["description"], item["source"])
        if done:
            return done

    if native:
        original = source.strip()
        # Text mutants that do not compile are cheap to reject, so allow a few more.
        for index, (description, candidate) in enumerate(
                iter_text_mutants(source, language, limit=max_mutants)):
            if candidate.strip() == original:
                continue
            counts["mutants"] += 1
            done = attempt("mutation search", description, candidate)
            if done:
                return done
    else:
        try:
            ast.parse(source)
            parsable = True
        except SyntaxError:
            parsable = False  # mutation search needs a parsable program

        if parsable:
            original_form = ast.unparse(ast.parse(source)).strip()
            for index, (description, candidate) in enumerate(iter_mutants(source, function)):
                if index >= max_mutants:
                    break
                if candidate.strip() == original_form:
                    continue
                counts["mutants"] += 1
                done = attempt("mutation search", description, candidate)
                if done:
                    return done

    from .reference_solutions import reference_candidate
    ref = reference_candidate(source, requirement, function, language)
    if ref:
        counts["rules"] += 1
        done = attempt("reference solution", ref[0], ref[1])
        if done:
            return done

    if llm_fn is not None:
        try:
            reply = llm_fn(build_repair_prompt(requirement, source, findings, language))
            done = attempt("LLM suggestion (verified)", "Candidate written by the LLM.",
                           _extract_code(reply))
            if done:
                return done
        except Exception as exc:  # noqa: BLE001 - an LLM failure must not break analysis
            tried.append({"strategy": "LLM suggestion (verified)", "description": "",
                          "accepted": False, "reason": f"failed: LLM call failed ({exc})"})

    return {"accepted": False, "strategy": None, "description": "", "source": None,
            "diff": "", "verification": None, "tried": tried,
            "why_not": _why_not(tried, counts["rules"], counts["mutants"])}
