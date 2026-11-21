"""Static Analyzer: syntax errors, Pyflakes warnings and a few extra AST checks."""
import ast

from pyflakes.checker import Checker

from .findings import (ERROR, INFO, NAMING, STRUCTURE, SYNTAX, WARNING,
                       make_finding)


def analyze_syntax(source):
    """Try to parse the source. Returns {"ok", "tree"} or {"ok": False, ...}."""
    try:
        return {"ok": True, "tree": ast.parse(source)}
    except SyntaxError as exc:
        return {"ok": False, "line": exc.lineno, "message": exc.msg,
                "text": (exc.text or "").strip()}


# Pyflakes message classes we treat as real hallucination evidence.
_NAMING_MESSAGES = {"UndefinedName", "UndefinedLocal", "UndefinedExport"}
_WARNING_MESSAGES = {"ImportStarUsed", "ImportStarUsage", "ReturnOutsideFunction"}


def run_pyflakes(tree, filename="candidate.py"):
    """Run Pyflakes on an already parsed tree and convert the messages."""
    findings = []
    checker = Checker(tree, filename=filename)
    for message in sorted(checker.messages, key=lambda m: m.lineno):
        kind = type(message).__name__
        text = message.message % message.message_args
        if kind in _NAMING_MESSAGES:
            findings.append(make_finding(NAMING, text, line=message.lineno,
                                         evidence=f"Pyflakes: {kind}",
                                         source="pyflakes"))
        elif kind in _WARNING_MESSAGES:
            findings.append(make_finding(NAMING, text, line=message.lineno,
                                         severity=WARNING,
                                         evidence=f"Pyflakes: {kind}",
                                         source="pyflakes"))
        else:
            findings.append(make_finding(NAMING, text, line=message.lineno,
                                         severity=INFO,
                                         evidence=f"Pyflakes: {kind} (style note)",
                                         source="pyflakes"))
    return findings


def run_extra_checks(tree):
    """Small, transparent AST rules (examples from the SDHD paper)."""
    findings = []
    for node in ast.walk(tree):
        # range(..., 0): an invalid step always raises ValueError.
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "range" and len(node.args) == 3):
            step = node.args[2]
            if isinstance(step, ast.Constant) and step.value == 0:
                findings.append(make_finding(
                    STRUCTURE, "range() is called with a step of 0.",
                    line=node.lineno, evidence="Rule: constant range step is zero",
                    source="ast-rule"))
        # A literal list/tuple indexed with a constant that is out of range.
        if (isinstance(node, ast.Subscript)
                and isinstance(node.value, (ast.List, ast.Tuple))
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, int)):
            size = len(node.value.elts)
            idx = node.slice.value
            if idx >= size or idx < -size:
                findings.append(make_finding(
                    STRUCTURE,
                    f"Index {idx} is outside a literal sequence of length {size}.",
                    line=node.lineno, evidence="Rule: constant index out of range",
                    source="ast-rule"))
    return findings


def analyze_static(source):
    """Full static pass. Returns {"syntax_ok", "tree", "findings"}."""
    syntax = analyze_syntax(source)
    if not syntax["ok"]:
        finding = make_finding(
            SYNTAX, syntax["message"], line=syntax["line"],
            evidence=f"ast.parse failed near: {syntax['text']}" if syntax["text"]
            else "ast.parse failed",
            source="ast")
        return {"syntax_ok": False, "tree": None, "findings": [finding]}
    tree = syntax["tree"]
    findings = run_pyflakes(tree) + run_extra_checks(tree)
    return {"syntax_ok": True, "tree": tree, "findings": findings}
