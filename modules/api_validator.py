"""API Validator: do imported modules, attributes and call signatures exist?

Only an allowlist of well-known standard-library modules is imported inside the
main process. Anything else is looked up with importlib.util.find_spec (which
does not run the module) and reported as "not inspected", never as an error.
Dynamic attributes, decorators and version differences can still make this check
incomplete, so unresolved cases are warnings, not defects.
"""
import difflib
import importlib
import importlib.util
import inspect

from .ast_analyzer import collect_structure
from .findings import API, ERROR, WARNING, make_finding

SAFE_MODULES = {
    "math", "re", "json", "collections", "itertools", "functools", "string",
    "statistics", "random", "datetime", "decimal", "fractions", "heapq",
    "bisect", "operator", "typing", "textwrap", "copy", "time", "enum",
    "dataclasses", "abc", "numbers", "array", "queue", "unicodedata",
}


def _close(name, options):
    matches = difflib.get_close_matches(name, options, n=1, cutoff=0.7)
    return f" Did you mean '{matches[0]}'?" if matches else ""


def _resolve_chain(obj, chain):
    """Follow attributes; return (object, failed_attribute)."""
    for attr in chain:
        if not hasattr(obj, attr):
            return None, attr
        obj = getattr(obj, attr)
    return obj, None


def _signature_problem(func, n_pos, kw_names):
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return None  # cannot inspect, so stay silent
    try:
        signature.bind(*([0] * n_pos), **{name: 0 for name in kw_names})
    except TypeError as exc:
        return f"{exc} (signature: {signature})"
    return None


def validate_api(source=None, tree=None):
    """Return API findings for the imports and calls in `source`."""
    import ast
    if tree is None:
        tree = ast.parse(source)
    structure = collect_structure(tree)
    findings = []
    modules = {}   # alias -> imported module object
    objects = {}   # from-imported name -> object

    for item in structure["imports"]:
        top = item["module"].split(".")[0]
        line = item["line"]
        if top in SAFE_MODULES:
            try:
                module = importlib.import_module(item["module"])
            except ImportError as exc:
                findings.append(make_finding(
                    API, f"Module '{item['module']}' cannot be imported.",
                    line=line, evidence=str(exc), source="api-validator"))
                continue
            if item["kind"] == "import":
                modules[item["alias"]] = importlib.import_module(top) \
                    if item["alias"] == top else module
            else:
                if hasattr(module, item["name"]):
                    objects[item["alias"]] = getattr(module, item["name"])
                else:
                    findings.append(make_finding(
                        API,
                        f"'{item['name']}' does not exist in module '{item['module']}'."
                        + _close(item["name"], dir(module)),
                        line=line, evidence="hasattr() check on the imported module",
                        source="api-validator"))
        else:
            try:
                found = importlib.util.find_spec(top) is not None
            except (ImportError, ValueError):
                found = False
            if not found:
                findings.append(make_finding(
                    API, f"Module '{top}' was not found in this environment.",
                    line=line, evidence="importlib.util.find_spec returned None",
                    source="api-validator"))
            else:
                findings.append(make_finding(
                    API, f"Module '{top}' is not on the allowlist, so its "
                    "attributes were not checked.", line=line, severity=WARNING,
                    evidence="uncertain: not inspected", source="api-validator"))

    for call in structure["calls"]:
        chain, line = call["chain"], call["line"]
        root = chain[0]
        if root in modules and len(chain) > 1:
            target, missing = _resolve_chain(modules[root], chain[1:])
            if missing:
                parent, _ = _resolve_chain(modules[root], chain[1:chain.index(missing)])
                options = dir(parent if parent is not None else modules[root])
                findings.append(make_finding(
                    API, f"'{'.'.join(chain)}' does not exist: no attribute '{missing}'."
                    + _close(missing, options),
                    line=line, evidence="hasattr() check on the imported module",
                    source="api-validator"))
                continue
        elif root in objects and len(chain) == 1:
            target = objects[root]
        else:
            continue
        if callable(target) and not call["has_star"]:
            problem = _signature_problem(target, call["n_pos"], call["kw_names"])
            if problem:
                findings.append(make_finding(
                    API, f"Call to '{'.'.join(chain)}' does not match its signature.",
                    line=line, evidence=problem, source="api-validator"))
    return findings
