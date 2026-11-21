"""Input Manager: validates the requirement, source code and test cases."""
import ast
import json
import re

MAX_SOURCE_CHARS = 20000
MAX_CASES = 200


def detect_function_name(source):
    """Return the first top-level function name, or None."""
    try:
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node.name
        return None
    except SyntaxError:
        match = re.search(r"^\s*def\s+([A-Za-z_]\w*)\s*\(", source, re.M)
        return match.group(1) if match else None


def normalize_cases(raw):
    """Accept a JSON string or a list and return a clean list of cases.

    Each case may use either {"args": [...], "expected": ...} or the shorthand
    {"input": <single argument>, "expected": ...}.
    """
    if raw is None or raw == "":
        return [], []
    errors = []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            return [], [f"Test cases are not valid JSON: {exc.msg} (line {exc.lineno})."]
    if isinstance(raw, dict) and "cases" in raw:
        raw = raw["cases"]
    if not isinstance(raw, list):
        return [], ["Test cases must be a JSON list of objects."]
    cases = []
    for index, item in enumerate(raw[:MAX_CASES]):
        if not isinstance(item, dict) or "expected" not in item:
            errors.append(f"Test case {index + 1} needs an 'expected' value.")
            continue
        if "args" in item:
            args = item["args"]
            if not isinstance(args, list):
                errors.append(f"Test case {index + 1}: 'args' must be a list.")
                continue
        elif "input" in item:
            args = [item["input"]]
        else:
            errors.append(f"Test case {index + 1} needs 'args' or 'input'.")
            continue
        cases.append({
            "id": item.get("id", f"case-{index + 1}"),
            "args": args,
            "kwargs": item.get("kwargs", {}),
            "expected": item["expected"],
            "kind": item.get("kind", "given"),
            "note": item.get("note", ""),
        })
    if len(raw) > MAX_CASES:
        errors.append(f"Only the first {MAX_CASES} test cases are used.")
    return cases, errors


def validate_inputs(requirement, source, function_name=None, cases=None, language="python"):
    """Validate everything the user typed in.

    Returns {"ok", "errors", "warnings", "function_name", "cases"}.
    """
    errors, warnings = [], []
    requirement = (requirement or "").strip()
    source = source or ""
    if not source.strip():
        errors.append("Please paste some Python source code.")
    if len(source) > MAX_SOURCE_CHARS:
        errors.append(f"Source code is longer than {MAX_SOURCE_CHARS} characters.")
    if not requirement:
        warnings.append(
            "No requirement given: requirement-level (logical) checks need one.")
    if language == "python":
        name = (function_name or "").strip() or detect_function_name(source)
    else:
        from .multilang import detect_function_name as detect_native
        name = (function_name or "").strip() or detect_native(source, language)
    if source.strip() and not name:
        warnings.append("No function found: tests can only call a function by name.")
    parsed_cases, case_errors = normalize_cases(cases)
    warnings.extend(case_errors)
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "requirement": requirement,
        "function_name": name,
        "cases": parsed_cases,
    }
