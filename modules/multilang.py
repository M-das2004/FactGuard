"""Multi-language support (C, C++, Java) for the main process.

The compile-and-run work happens in sandbox/native_runner.py (inside the sandbox).
This module only does things that need no execution:

  * detect the language and the function under test
  * turn compiler diagnostics into FactGuard findings (labels, evidence, hints)
  * propose repairs: targeted rules and small text mutations
"""
import difflib
import re

from .findings import (API, DATA, ERROR, INFO, LOGIC, NAMING, STRUCTURE, SYNTAX, WARNING,
                       make_finding)

LANGUAGES = ("python", "c", "cpp", "java")
LANGUAGE_NAMES = {"python": "Python", "c": "C", "cpp": "C++", "java": "Java"}
COMPILERS = {"c": "gcc", "cpp": "g++", "java": "javac"}
KEYWORDS = {
    "if", "else", "for", "while", "do", "switch", "case", "break", "continue", "return",
    "int", "long", "double", "float", "char", "void", "bool", "boolean", "short", "unsigned",
    "signed", "const", "static", "struct", "class", "public", "private", "protected", "new",
    "true", "false", "null", "this", "sizeof", "auto", "namespace", "using", "std", "final",
    "import", "package", "try", "catch", "throw", "throws", "string", "String", "include",
}


def detect_language(source):
    """Best guess from the text: python | c | cpp | java."""
    text = source or ""
    if re.search(r"\bpublic\s+(static\s+)?(class|interface)\b|\bimport\s+java\.|"
                 r"\bSystem\.out\b|\bclass\s+\w+\s*\{", text):
        return "java"
    if re.search(r"#include\s*<(iostream|vector|string|map|set|algorithm|cstdio|cmath)>|"
                 r"\bstd::|\busing\s+namespace\b|\btemplate\s*<", text):
        return "cpp"
    if re.search(r"#include\s*[<\"]|^\s*(int|void|double|char|long|float)\s+\**\w+\s*\(.*\)\s*\{?\s*$",
                 text, re.M) and not re.search(r"^\s*def\s", text, re.M):
        return "c"
    return "python"


def _mask(src):
    """Blank out comments, strings and preprocessor lines (same length)."""
    out, i, n = list(src), 0, len(src)

    def blank(a, b):
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        two = src[i:i + 2]
        if two == "//":
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif two == "/*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
        elif src[i] in "\"'":
            quote, j = src[i], i + 1
            while j < n and src[j] != quote and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            blank(i, j + 1)
            i = j + 1
        else:
            i += 1
    return re.sub(r"(?m)^[ \t]*#.*$", lambda m: " " * len(m.group(0)), "".join(out))


_FUNC = re.compile(
    r"(?m)(?:^|(?<=[{};]))\s*(?:(?:public|private|protected|static|final|inline|extern|"
    r"unsigned|const|synchronized)\s+)*[A-Za-z_][\w:<>,\[\]\*&\s\.]*?[\s\*&](\w+)\s*\([^()]*\)"
    r"\s*(?:const\s*)?(?:throws\s+[\w\s,.]+)?\{")
_NOT_FUNCTIONS = {"if", "for", "while", "switch", "catch", "main", "else", "return", "sizeof"}


def detect_function_name(source, language):
    """Name of the first function that is not main()."""
    for match in _FUNC.finditer(_mask(source)):
        if match.group(1) not in _NOT_FUNCTIONS:
            return match.group(1)
    return None


# --------------------------------------------------------------- diagnostics
def _quoted(text):
    found = re.findall(r"['‘`]([A-Za-z_][\w:]*)['’]", text)
    return found[0] if found else None


def classify_diagnostic(diag, source, language):
    """Return (label, severity, evidence) for one compiler diagnostic."""
    msg = diag["message"]
    low = msg.lower()
    notes = " ".join(diag.get("notes", []))
    text_line = ""
    lines = source.splitlines()
    if diag.get("line") and 0 < diag["line"] <= len(lines):
        text_line = lines[diag["line"] - 1]
    tool = COMPILERS[language]

    if diag["severity"] == "warning":
        if "control reaches end of non-void" in low:
            return STRUCTURE, WARNING, f"{tool} warning: a path returns nothing"
        if "uninitialized" in low:
            return STRUCTURE, WARNING, f"{tool} warning: value used before it is set"
        if "above array bounds" in low or "array subscript" in low and "bounds" in low:
            return STRUCTURE, WARNING, f"{tool} warning: index outside the array"
        if "division by zero" in low:
            return DATA, WARNING, f"{tool} warning: division by zero"
        if "format" in low and ("expects" in low or "argument" in low):
            return DATA, WARNING, f"{tool} warning: format does not match its arguments"
        return NAMING, INFO, f"{tool} warning (style note)"

    evidence = f"{tool} error"
    if re.search(r"expected|illegal start|reached end of file|unterminated|stray|missing "
                 r"terminating|class, interface|not a statement|unmatched|invalid preprocessing",
                 low) and "no matching" not in low and "expected primary" not in low:
        return SYNTAX, ERROR, evidence
    if re.search(r"no such file|package .* does not exist|implicit declaration|has no member|"
                 r"no member named|no matching function|does not name a type|"
                 r"too (many|few) arguments|undefined reference|is not a member of|"
                 r"cannot be dereferenced|method .* in class .* cannot be applied", low):
        return API, ERROR, evidence + " (name or call that does not exist in the library)"
    if "cannot find symbol" in low:
        kind = re.search(r"symbol:\s+(\w+)", notes)
        if kind and kind.group(1) in ("variable",):
            return NAMING, ERROR, evidence + " (unknown variable)"
        return API, ERROR, evidence + " (method or class that does not exist)"
    if "undeclared" in low or "was not declared" in low or "not declared" in low:
        ident = _quoted(msg)
        if ident and re.search(rf"\b{re.escape(ident)}\s*\(", text_line):
            return API, ERROR, evidence + " (function that is not declared)"
        return NAMING, ERROR, evidence + " (unknown name)"
    if re.search(r"incompatible|invalid conversion|cannot convert|makes (integer|pointer)|"
                 r"bad operand|cannot be applied|invalid operands|lossy|possible loss", low):
        return DATA, ERROR, evidence + " (types do not match)"
    if "missing return" in low:
        return STRUCTURE, ERROR, evidence + " (a path returns nothing)"
    return SYNTAX, ERROR, evidence + " (unclassified)"


def diagnostics_to_findings(diagnostics, source, language):
    """Convert the runner's compiler diagnostics into findings."""
    findings = []
    for diag in diagnostics:
        label, severity, evidence = classify_diagnostic(diag, source, language)
        finding = make_finding(label, diag["message"], line=diag.get("line"),
                               severity=severity, source="compiler",
                               evidence=evidence + (" - " + " ".join(diag["notes"])
                                                    if diag.get("notes") else ""))
        finding["column"] = diag.get("column")
        finding["notes"] = diag.get("notes", [])
        findings.append(finding)
    return findings


# ------------------------------------------------------------------- repairs
def _identifiers(source):
    return {w for w in re.findall(r"\b[A-Za-z_]\w*\b", _mask(source)) if w not in KEYWORDS}


def native_rule_repairs(source, requirement, findings, language):
    """Targeted repairs that need only the compiler's own messages."""
    candidates, lines = [], source.split("\n")

    def add(strategy, description, new_source):
        if new_source != source and all(c["source"] != new_source for c in candidates):
            candidates.append({"strategy": strategy, "description": description,
                               "source": new_source})

    for f in findings:
        if f["severity"] != ERROR or f.get("source") != "compiler":
            continue
        message, line_no = f["message"], f.get("line")
        notes = " ".join(f.get("notes", []))

        # 1. missing semicolon
        if re.search(r"expected ';'|';' expected", message) and line_no and \
                0 < line_no <= len(lines):
            col, text = f.get("column"), lines[line_no - 1]
            fixed = list(lines)
            if col and col - 1 <= len(text) and text[col - 1:].strip() == "":
                fixed[line_no - 1] = text[:col - 1] + ";" + text[col - 1:]
            else:
                fixed[line_no - 1] = text.rstrip() + ";"
            add("rule: add missing semicolon",
                f"Add the missing ';' at the end of line {line_no}.", "\n".join(fixed))

        # 2. the compiler itself suggests a name ("did you mean 'strlen'?")
        hint = re.search(r"(?:did you mean|suggested alternative:?)\s*['‘]?(\w+)['’]?",
                         message + " " + notes)
        wrong = _quoted(message) or (re.search(
            r"symbol:\s+(?:method|variable)\s+(\w+)", notes) or [None, None])[1]
        if hint and wrong and hint.group(1) != wrong:
            add("rule: use the name the compiler suggests",
                f"Replace '{wrong}' with '{hint.group(1)}', as the compiler suggests.",
                re.sub(rf"\b{re.escape(wrong)}\b", hint.group(1), source))
            continue

        # 3. unknown variable: a similarly spelled name that exists
        if f["label"] == NAMING:
            wrong = _quoted(message) or (re.search(r"symbol:\s+variable\s+(\w+)", notes) or
                                         [None, None])[1]
            if wrong:
                pool = _identifiers(source) - {wrong}
                close = difflib.get_close_matches(wrong, pool, n=1, cutoff=0.6)
                if close:
                    add("rule: rename unknown variable",
                        f"Rename '{wrong}' to the similar existing name '{close[0]}'.",
                        re.sub(rf"\b{re.escape(wrong)}\b", close[0], source))

    # 3b. the compiler says which header / import is missing
    for f in findings:
        if f["severity"] != ERROR or f.get("source") != "compiler":
            continue
        blob = f["message"] + " " + " ".join(f.get("notes", []))
        header = re.search(r"#include <([\w./]+)>", blob) or \
            re.search(r"include ['‘]<([\w./]+)>['’]", blob)
        if header and language in ("c", "cpp"):
            add("rule: add missing #include",
                f"Add #include <{header.group(1)}>, as the compiler suggests.",
                f"#include <{header.group(1)}>\n" + source)
        if language == "java":
            sym = re.search(r"symbol:\s+class\s+(\w+)", blob)
            if sym and sym.group(1) in _JAVA_UTIL:
                add("rule: add missing import",
                    f"Add 'import java.util.{sym.group(1)};'.",
                    f"import java.util.{sym.group(1)};\n" + source)

    # 4. "starts with" written where the requirement says "contains"
    contains_req = re.search(r"contain|anywhere|includ|\bhas\b", (requirement or "").lower())
    if contains_req and language == "cpp":
        add("rule: starts-with idiom -> find",
            "Use find() != npos, because the requirement asks for text anywhere in the value.",
            re.sub(r"(\w+)\.rfind\(([^,()]+),\s*0\)\s*==\s*0",
                   r"\1.find(\2) != std::string::npos", source))
    if contains_req and language == "cpp":
        add("rule: first-character test -> find",
            "Use find() != npos, because the requirement asks for text anywhere in the value.",
            re.sub(r"(\w+)\[0\]\s*==\s*('[^']+'|\"[^\"]*\")",
                   lambda m: f"{m.group(1)}.find({m.group(2)}) != std::string::npos", source))
    if contains_req and language == "java":
        add("rule: charAt(0) -> contains",
            "Use contains(), because the requirement asks for text anywhere in the value.",
            re.sub(r"(\w+)\.charAt\(0\)\s*==\s*'([^']+)'",
                   lambda m: f'{m.group(1)}.contains("{m.group(2)}")', source))
    if contains_req and language == "c":
        add("rule: first-character test -> strchr",
            "Use strchr(), because the requirement asks for a character anywhere in the string.",
            ("#include <string.h>\n" if "string.h" not in source else "") +
            re.sub(r"(\w+)\[0\]\s*==\s*('[^']+')",
                   lambda m: f"strchr({m.group(1)}, {m.group(2)}) != NULL", source))
    if contains_req and language == "c":
        add("rule: strncmp -> strstr",
            "Use strstr(), because the requirement asks for text anywhere in the value.",
            re.sub(r"strncmp\((\w+),\s*(\"[^\"]*\"),\s*\d+\)\s*==\s*0",
                   r"strstr(\1, \2) != NULL", source))

    # 5. Java: startsWith where the requirement says "contains"
    if language == "java" and re.search(r"contain|anywhere|includ|\bhas\b",
                                        (requirement or "").lower()):
        fixed = re.sub(r"\.(startsWith|endsWith)\(", ".contains(", source)
        add("rule: startsWith/endsWith -> contains",
            "Use contains(), because the requirement asks for text that occurs anywhere.",
            fixed)
    return candidates


_OPS_ANYWHERE = re.compile(r"(?<![<>=!+\-&|*/%^])(<=|>=|==|!=|&&|\|\||\+=|-=)(?![=<>&|])")
_OPS_SPACED = re.compile(r"(?<=\s)(<|>|\+|-)(?=\s)")
_OPS_TIGHT = re.compile(r"(?<=[\w)\]])(?:(<)(?![<=])|(>)(?![>=])|(\+)(?![+=])|(-)(?![-=>]))(?=[\w(])")
_NUMBER = re.compile(r"(?<![\w.\[])(\d+)(?![\w.])")
_JAVA_UTIL = {"List", "ArrayList", "Arrays", "Map", "HashMap", "Set", "HashSet", "Scanner",
              "LinkedList", "Collections", "Queue", "Deque", "ArrayDeque", "TreeMap", "Stack"}
_SWAP = {"<=": "<", "<": "<=", ">=": ">", ">": ">=", "==": "!=", "!=": "==",
         "&&": "||", "||": "&&", "+": "-", "-": "+", "+=": "-=", "-=": "+="}
_METHOD_SWAPS = [("startsWith", "endsWith"), ("endsWith", "startsWith"),
                 ("Math.max", "Math.min"), ("Math.min", "Math.max"),
                 ("std::max", "std::min"), ("std::min", "std::max")]


def iter_text_mutants(source, language, limit=60):
    """Yield (description, new_source): one small textual change per mutant.

    Changes that do not compile are rejected cheaply by the compiler later, so
    ambiguous symbols (such as `<` in `vector<int>`) are allowed here.
    """
    masked = _mask(source)
    found = {}

    def site(start, end, replacement, text):
        found.setdefault((start, replacement), (start, end, replacement, text))

    for m in _OPS_ANYWHERE.finditer(masked):
        site(m.start(1), m.end(1), _SWAP[m.group(1)],
             f"change '{m.group(1)}' to '{_SWAP[m.group(1)]}'")
    for m in _OPS_SPACED.finditer(masked):
        site(m.start(1), m.end(1), _SWAP[m.group(1)],
             f"change '{m.group(1)}' to '{_SWAP[m.group(1)]}'")
    for m in _OPS_TIGHT.finditer(masked):
        op = next(g for g in m.groups() if g)
        index = next(i for i, g in enumerate(m.groups(), 1) if g)
        site(m.start(index), m.end(index), _SWAP[op], f"change '{op}' to '{_SWAP[op]}'")
    for m in _NUMBER.finditer(masked):
        value = int(m.group(1))
        for new in ([value + 1] + ([value - 1] if value > 0 else [])):
            site(m.start(1), m.end(1), str(new), f"change {value} to {new}")
    for old, new in _METHOD_SWAPS:
        for m in re.finditer(re.escape(old), masked):
            site(m.start(), m.end(), new, f"use {new} instead of {old}")

    for start, end, replacement, text in sorted(found.values(), key=lambda x: (x[0], x[3]))[:limit]:
        line = source.count("\n", 0, start) + 1
        yield f"line {line}: {text}", source[:start] + replacement + source[end:]


def locate_function(source, function):
    """1-based line where `function` is defined, or None."""
    for match in _FUNC.finditer(_mask(source)):
        if match.group(1) == function:
            return source.count("\n", 0, match.start(1)) + 1
    return None
