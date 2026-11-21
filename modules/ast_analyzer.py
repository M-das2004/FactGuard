"""AST helpers: collect imports, functions and calls; read branch conditions."""
import ast


def collect_structure(tree):
    """Return imports, function definitions and attribute/name calls."""
    imports, functions, calls = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({"kind": "import", "module": alias.name,
                                "name": None, "alias": alias.asname or alias.name.split(".")[0],
                                "line": node.lineno})
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import: cannot be resolved here
                continue
            for alias in node.names:
                imports.append({"kind": "from", "module": node.module or "",
                                "name": alias.name, "alias": alias.asname or alias.name,
                                "line": node.lineno})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({"name": node.name, "line": node.lineno,
                              "args": [a.arg for a in node.args.args]})
        elif isinstance(node, ast.Call):
            chain = _attribute_chain(node.func)
            if chain:
                calls.append({
                    "chain": chain,
                    "line": node.lineno,
                    "n_pos": len(node.args),
                    "kw_names": [k.arg for k in node.keywords if k.arg],
                    "has_star": any(isinstance(a, ast.Starred) for a in node.args)
                    or any(k.arg is None for k in node.keywords),
                })
    return {"imports": imports, "functions": functions, "calls": calls}


def _attribute_chain(node):
    """`a.b.c(...)` -> ['a', 'b', 'c']; returns None for other call targets."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return list(reversed(parts))
    return None


def find_branch_conditions(tree, line):
    """Comparisons used in the if/while/assert/ternary that starts at `line`.

    Used by coverage-guided testing to guess inputs that reach a missed branch.
    Returns a list of {"name", "op", "const"} dictionaries.
    """
    conditions = []
    for node in ast.walk(tree):
        if getattr(node, "lineno", None) != line:
            continue
        if isinstance(node, (ast.If, ast.While, ast.IfExp, ast.Assert)):
            for sub in ast.walk(node.test):
                if not isinstance(sub, ast.Compare):
                    continue
                left, via_len = sub.left, False
                # `len(x) > 3` -> condition on x's length
                if (isinstance(left, ast.Call) and isinstance(left.func, ast.Name)
                        and left.func.id == "len" and len(left.args) == 1
                        and isinstance(left.args[0], ast.Name)):
                    left, via_len = left.args[0], True
                if isinstance(left, ast.Name):
                    for op, right in zip(sub.ops, sub.comparators):
                        if isinstance(right, ast.Constant):
                            conditions.append({"name": left.id,
                                               "op": type(op).__name__,
                                               "const": right.value,
                                               "via_len": via_len})
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            conditions.append({"name": None, "op": "Loop", "const": None})
    return conditions
