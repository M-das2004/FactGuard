"""Detection Engine: combine evidence into labelled, explained findings.

Rules are deliberately simple and transparent (blueprint section 7.6):
every label is backed by evidence such as a failing test or a checker message.
"""
import json
import re

from .findings import (API, DATA, ERROR, INFO, LOGIC, NAMING, RESOURCE, STRUCTURE,
                       WARNING, defects, make_finding)

_EXCEPTION_LABELS = {
    "NameError": NAMING, "UnboundLocalError": NAMING,
    "IndexError": STRUCTURE, "KeyError": STRUCTURE,
    "TypeError": DATA, "ValueError": DATA, "AttributeError": DATA,
    "ImportError": API, "ModuleNotFoundError": API,
    "RecursionError": RESOURCE, "MemoryError": RESOURCE, "Timeout": RESOURCE,
}
NO_ISSUE = "No issue detected by current checks."


def label_for_exception(name):
    """Map an exception / sanitizer report name to a prototype label.

    Python names are looked up exactly. Names from Java, C++ and the C sanitizers
    ("ArrayIndexOutOfBoundsException", "out_of_range",
    "AddressSanitizer: heap-buffer-overflow", ...) are matched by keyword.
    """
    if name in _EXCEPTION_LABELS:
        return _EXCEPTION_LABELS[name]
    low = (name or "").lower()
    if any(k in low for k in ("stackoverflow", "stack-overflow", "outofmemory", "bad_alloc",
                              "out of memory", "timeout", "bad_array_new")):
        return RESOURCE
    if any(k in low for k in ("buffer-overflow", "out of bounds", "outofbounds", "out_of_range",
                              "indexoutof", "null", "use-after", "segmentation", "segv",
                              "negative index", "stringindex", "arraystore", "heap-use",
                              "invalid memory")):
        return STRUCTURE
    if any(k in low for k in ("arithmetic", "division", "divide", "overflow", "shift",
                              "numberformat", "classcast", "invalid_argument", "bad_cast",
                              "illegalargument", "testcasetypeerror", "bool")):
        return DATA
    if any(k in low for k in ("nosuchmethod", "nosuchfield", "classnotfound", "linkage",
                              "noclassdef")):
        return API
    return LOGIC


def _show(value, limit=120):
    text = value if isinstance(value, str) and False else json.dumps(value, default=repr)
    return text if len(text) <= limit else text[:limit] + "..."


# Words in a requirement that make changing the input legitimate.
_INPLACE = re.compile(r"in[- ]place|modif|mutat|update|sort the (list|array)|reverse the "
                      r"(list|array)|shuffle|append|remove|insert|swap|rotate|\bdelete|"
                      r"\bclear|\bpop\b|\bfill", re.I)


def property_findings(run, function, function_line, requirement):
    """Template-free oracle (review F2): no test is needed to know that a function
    which was asked to *return* something should not silently change its argument.
    Python only. Skipped when the requirement talks about modifying the input."""
    if _INPLACE.search(requirement or ""):
        return []
    for case in run.get("cases", []):
        if case.get("mutated_args") and case["status"] in ("pass", "fail", "ok"):
            return [make_finding(
                LOGIC, f"The function changed its own argument {_show(case['args'])} "
                       "although the requirement does not ask for that.",
                line=function_line, severity=ERROR if not case.get("probe") else WARNING,
                evidence=f"property check: input unchanged after the call ({case['id']})",
                source="property", function=function)]
    return []


def classify_run(run, function=None, function_line=None, output_type=None, requirement=""):
    """Turn a sandbox result into findings (failed tests, crashes, timeouts)."""
    findings = property_findings(run, function, function_line, requirement)
    import_error = run.get("import_error")
    if import_error:
        label = label_for_exception(import_error["type"])
        findings.append(make_finding(
            label, f"Running the module failed: {import_error['type']}: "
                   f"{import_error['message']}",
            line=import_error.get("line"),
            evidence="exception raised while importing the candidate",
            source="dynamic", function=function))

    for case in run.get("cases", []):
        status, probe = case["status"], case.get("probe")
        soft = probe or case.get("kind") == "assumption"  # uncertain evidence
        severity = WARNING if soft else ERROR
        where = case.get("exception") or {}
        if status in ("pass", "ok"):
            continue
        if status == "fail":
            label = LOGIC
            if output_type and case.get("actual_type") and case["actual_type"] != output_type:
                label = DATA
            findings.append(make_finding(
                label,
                f"For input {_show(case['args'])} expected {_show(case['expected'])} "
                f"but got {_show(case['actual'])}.",
                line=function_line, severity=severity,
                evidence=f"failing test {case['id']} ({case.get('kind')})"
                + (" - rests on a stated assumption" if case.get("kind") == "assumption" else ""),
                source="dynamic", function=function))
        elif status in ("error", "timeout"):
            if import_error and where == import_error:
                continue  # already reported once for the whole module
            label = label_for_exception(where.get("type", ""))
            if where.get("type") == "AttributeError" and "module '" in where.get("message", ""):
                label = API  # e.g. module 'math' has no attribute 'sqroot'
            prefix = "Probe input" if probe else "Test input"
            findings.append(make_finding(
                label,
                f"{prefix} {_show(case['args'])} raised {where.get('type')}: "
                f"{where.get('message')}",
                line=where.get("line") or function_line, severity=severity,
                evidence=("coverage probe (no expected value) - needs human review"
                          if probe else f"failing test {case['id']} ({case.get('kind')})"),
                source="dynamic", function=function))
    return findings


def explain_logic(source, requirement):
    """A plain-language hint for common logical mistakes, or ''."""
    req = (requirement or "").lower()
    if re.search(r"\.(startswith|endswith)\(", source, re.I) and re.search(
            r"contain|anywhere|includ|\bhas\b", req):
        which = "startswith" if "startswith" in source.lower() else "endswith"
        side = "first" if which == "startswith" else "last"
        return (f"{which}() only looks at the {side} characters, but the requirement "
                "asks whether the text occurs anywhere in the word.")
    return ""


def verdict_legacy(findings):
    """One-line summary of everything that was found."""
    errors = defects(findings)
    warnings = [f for f in findings if f["severity"] == WARNING]
    if errors:
        labels = sorted({f["label"] for f in errors})
        return f"Defects detected: {', '.join(labels)}."
    if warnings:
        return "No confirmed defect, but some results need a human review."
    return NO_ISSUE


def combine(static_findings, api_findings, run_findings, source="", requirement=""):
    """Merge all evidence, add explanations, and sort by line."""
    findings = [dict(f) for f in static_findings + api_findings + run_findings]
    hint = explain_logic(source, requirement)
    for finding in findings:
        if finding["label"] == LOGIC and finding["severity"] == ERROR and hint:
            finding["explanation"] = hint
    order = {ERROR: 0, WARNING: 1, INFO: 2}
    findings.sort(key=lambda f: (order.get(f["severity"], 3), f["line"] or 0))
    return findings
