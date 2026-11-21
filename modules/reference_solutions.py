"""Reference-solution repair: rewrite the function body from a known-correct recipe.

When the requirement says what the function must do (for example "sum of a list",
"factorial", "palindrome") and mutation/rule repair found nothing, we offer a clean
implementation of that requirement, keeping the user's function name, parameter names,
return type and everything outside the function. It is only a CANDIDATE: it is accepted
only if it passes the same verification as every other repair.

Catalogue size is deliberately small and honest: it covers common textbook tasks in
Python, and a subset in C, C++ and Java. For anything else use an LLM (llm_providers.py).
"""
import ast
import re

# --------------------------------------------------------------------------- intents
# name -> (regex on lower-cased requirement, arity, kinds of parameters, return kind)
#   kinds: "list" = list of ints, "int", "str", "num"
INTENTS = [
    ("sum_list", r"\bsum\b.*\b(list|array|numbers|elements|integers)\b", ["list"]),
    ("max_list", r"\b(maximum|largest|max)\b.*\b(list|array)\b", ["list"]),
    ("average", r"\baverage\b|\bmean\b", ["list"]),
    ("factorial", r"\bfactorial\b", ["int"]),
    ("palindrome", r"\bpalindrome\b", ["str"]),
    ("count_vowels", r"\bcount\b.*\bvowels?\b", ["str"]),
    ("absolute", r"\babsolute value\b", ["int"]),
    ("gcd", r"\bgreatest common divisor\b|\bgcd\b", ["int", "int"]),
    ("square", r"\bsquare of\b", ["int"]),
    ("string_length", r"\blength of a string\b", ["str"]),
    ("sqrt", r"\bsquare root\b", ["num"]),
    ("reverse_string", r"\breverse\b.*\bstring\b", ["str"]),
    ("smaller", r"\b(smaller|minimum|smallest)\b.*\btwo\b", ["int", "int"]),
    ("is_prime", r"\bprime\b", ["int"]),
    ("leap_year", r"\bleap year\b", ["int"]),
    ("fibonacci", r"\bfibonacci\b", ["int"]),
    ("even_numbers", r"\beven numbers\b", ["list"]),
    ("celsius", r"\bcelsius\b.*\bfahrenheit\b", ["num"]),
]
# Phrases that make the intent a different problem (same guard as the test templates).
_EXCLUDE = re.compile(r"\b(second|third|kth|nth|top|k)\s+(largest|smallest)\b|\bsecond\b|"
                      r"\bdistinct\b|\bunique\b|\brunning\b|\bcumulative\b|\bsorted\b|"
                      r"\bdescending\b|\bnon-?negative\b.*\bsqrt\b|\brounded\b")


def detect_intent(requirement):
    text = (requirement or "").lower()
    if _EXCLUDE.search(text):
        return None
    for name, pattern, kinds in INTENTS:
        if re.search(pattern, text):
            return name, kinds
    return None


# --------------------------------------------------------------------------- Python
def _py_body(intent, p):
    a = p[0] if p else "x"
    b = p[1] if len(p) > 1 else "y"
    return {
        "sum_list": f"total = 0\nfor item in {a}:\n    total += item\nreturn total",
        "max_list": f"best = {a}[0]\nfor item in {a}[1:]:\n    if item > best:\n        best = item\nreturn best",
        "average": f"if not {a}:\n    return 0\nreturn sum({a}) / len({a})",
        "factorial": f"result = 1\nfor i in range(2, {a} + 1):\n    result *= i\nreturn result",
        "palindrome": f"return {a} == {a}[::-1]",
        "count_vowels": f"return sum(1 for ch in {a} if ch in 'aeiou')",
        "absolute": f"return {a} if {a} >= 0 else -{a}",
        "gcd": f"while {b}:\n    {a}, {b} = {b}, {a} % {b}\nreturn {a}",
        "square": f"return {a} * {a}",
        "string_length": f"return len({a})",
        "sqrt": f"return {a} ** 0.5",
        "reverse_string": f"return {a}[::-1]",
        "smaller": f"return {a} if {a} < {b} else {b}",
        "is_prime": (f"if {a} < 2:\n    return False\ni = 2\nwhile i * i <= {a}:\n"
                     f"    if {a} % i == 0:\n        return False\n    i += 1\nreturn True"),
        "leap_year": f"return ({a} % 4 == 0 and {a} % 100 != 0) or {a} % 400 == 0",
        "fibonacci": f"x, y = 0, 1\nfor _ in range({a}):\n    x, y = y, x + y\nreturn x",
        "even_numbers": f"return [item for item in {a} if item % 2 == 0]",
        "celsius": f"return {a} * 9 / 5 + 32",
    }.get(intent)


def python_candidate(source, function, intent):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    node = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function),
                None)
    if node is None or node.args.vararg or node.args.kwarg:
        return None
    params = [a.arg for a in node.args.args]
    body = _py_body(intent, params)
    if body is None:
        return None
    lines = source.split("\n")
    start = (node.decorator_list[0].lineno if node.decorator_list else node.lineno) - 1
    # keep the user's own `def ...:` header (may span lines); body starts after it
    def_end = node.body[0].lineno - 1
    if isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None),
                                                        ast.Constant) \
            and isinstance(node.body[0].value.value, str):
        docstring = lines[node.body[0].lineno - 1:node.body[0].end_lineno]
    else:
        docstring = []
    head = lines[start:def_end]
    # a one-line `def f(x): return x` has no separate header line
    if node.body[0].lineno == node.lineno:
        head = [lines[node.lineno - 1].split(":", 1)[0] + ":"]
    indent = "    "
    new = head + docstring + [indent + ln if ln else ln for ln in body.split("\n")]
    candidate = "\n".join(lines[:start] + new + lines[node.end_lineno:])
    try:
        ast.parse(candidate)
    except SyntaxError:
        return None
    return candidate


# --------------------------------------------------------------------------- native
def _span_of_function(source, language, function):
    """(body_start, body_end) of the braces of `function`, or None."""
    from sandbox.native_runner import _C_SIG, _JAVA_SIG, _mask
    masked = _mask(source)
    pattern, group = (_JAVA_SIG, 3) if language == "java" else (_C_SIG, 2)
    found = [m for m in pattern.finditer(masked) if m.group(group) == function]
    if not found:
        return None
    start = found[0].end() - 1  # the "{"
    depth = 0
    for i in range(start, len(masked)):
        if masked[i] == "{":
            depth += 1
        elif masked[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i
    return None


def _native_body(intent, language, sig):
    p = [q["name"] for q in sig["params"]]
    t = [q["canon"] for q in sig["params"]]
    ret = sig["ret"]["raw"]
    ret_canon = sig["ret"]["canon"]
    a = p[0] if p else "x"
    b = p[1] if len(p) > 1 else "y"
    is_list = t and t[0] == "int[]"
    if language == "java":
        n_of = f"{a}.length" if is_list else None
        if is_list and ("List" in sig["params"][0]["raw"]):
            n_of = f"{a}.size()"
        item = (lambda i: f"{a}.get({i})") if is_list and "List" in sig["params"][0]["raw"] \
            else (lambda i: f"{a}[{i}]")
        length_of_s = f"{a}.length()"
        char_at = lambda s, i: f"{s}.charAt({i})"  # noqa: E731
    elif language == "cpp" and is_list and "vector" in sig["params"][0]["raw"]:
        n_of = f"(int){a}.size()"
        item = lambda i: f"{a}[{i}]"  # noqa: E731
        length_of_s = f"(int){a}.size()"
        char_at = lambda s, i: f"{s}[{i}]"  # noqa: E731
    else:  # C, or C++ with pointer + length
        n_of = sig["params"][0].get("len_name") if is_list else None
        item = lambda i: f"{a}[{i}]"  # noqa: E731
        length_of_s = f"(int)strlen({a})" if language == "c" else f"(int){a}.size()"
        char_at = lambda s, i: f"{s}[{i}]"  # noqa: E731
    if language == "cpp" and t and t[0] == "string":
        length_of_s = f"(int){a}.size()"
    if t and t[0] == "string" and language == "c":
        length_of_s = f"(int)strlen({a})"
    num = ret_canon in ("int", "long", "double")
    zero = "0.0" if ret_canon == "double" else "0"
    one = "1"
    loop = lambda n: f"for (int i = 0; i < {n}; i++)"  # noqa: E731

    if intent == "sum_list" and is_list and num:
        return f"{ret} s = {zero};\n    {loop(n_of)} s += {item('i')};\n    return s;"
    if intent == "max_list" and is_list and num and n_of:
        return (f"{ret} best = {item('0')};\n    for (int i = 1; i < {n_of}; i++)\n"
                f"        if ({item('i')} > best) best = {item('i')};\n    return best;")
    if intent == "average" and is_list and num and n_of:
        cast = "(double)" if ret_canon == "double" else ""
        return (f"if ({n_of} == 0) return 0;\n    long long s = 0;\n"
                f"    {loop(n_of)} s += {item('i')};\n    return {cast}s / {n_of};"
                if ret_canon != "double" else
                f"if ({n_of} == 0) return 0.0;\n    double s = 0;\n"
                f"    {loop(n_of)} s += {item('i')};\n    return s / {n_of};")
    if intent == "factorial" and t == ["int"] and num:
        return f"{ret} r = 1;\n    for (int i = 2; i <= {a}; i++) r *= i;\n    return r;"
    if intent == "absolute" and t == ["int"] and num:
        return f"return {a} < 0 ? -{a} : {a};"
    if intent == "square" and t == ["int"] and num:
        return f"return ({ret}){a} * {a};"
    if intent == "smaller" and t == ["int", "int"] and num:
        return f"return {a} < {b} ? {a} : {b};"
    if intent == "gcd" and t == ["int", "int"] and num:
        return (f"while ({b} != 0) {{\n        int tmp = {b};\n        {b} = {a} % {b};\n"
                f"        {a} = tmp;\n    }}\n    return {a};")
    if intent == "is_prime" and t == ["int"] and ret_canon == "bool":
        t_, f_ = ("true", "false")
        return (f"if ({a} < 2) return {f_};\n    for (int i = 2; (long long)i * i <= {a}; i++)\n"
                f"        if ({a} % i == 0) return {f_};\n    return {t_};")
    if intent == "leap_year" and t == ["int"] and ret_canon == "bool":
        return f"return ({a} % 4 == 0 && {a} % 100 != 0) || {a} % 400 == 0;"
    if intent == "sqrt" and t and t[0] in ("int", "double") and ret_canon == "double":
        return f"return {'Math.sqrt' if language == 'java' else 'sqrt'}({a});"
    if intent == "string_length" and t == ["string"] and num:
        return f"return {length_of_s};"
    if intent == "palindrome" and t == ["string"] and ret_canon == "bool":
        return (f"int i = 0, j = {length_of_s} - 1;\n    while (i < j) {{\n"
                f"        if ({char_at(a, 'i')} != {char_at(a, 'j')}) return false;\n"
                "        i++;\n        j--;\n    }\n    return true;")
    if intent == "count_vowels" and t == ["string"] and num:
        c = char_at(a, "i")
        test = (f"{c} == 'a' || {c} == 'e' || {c} == 'i' || {c} == 'o' || {c} == 'u'")
        return (f"{ret} count = 0;\n    for (int i = 0; i < {length_of_s}; i++)\n"
                f"        if ({test}) count++;\n    return count;")
    if intent == "celsius" and t and t[0] in ("int", "double") and ret_canon == "double":
        return f"return {a} * 9.0 / 5.0 + 32.0;"
    return None


def _needed_include(language, body):
    if language == "c" and "strlen" in body:
        return "#include <string.h>"
    if language in ("c", "cpp") and "sqrt(" in body:
        return "#include <math.h>" if language == "c" else "#include <cmath>"
    return None


def native_candidate(source, language, function, intent):
    try:
        from sandbox.native_runner import Unsupported, parse_signature
        sig = parse_signature(source, language, function)
    except Exception:  # noqa: BLE001 - unsupported signature: no reference repair
        return None
    body = _native_body(intent, language, sig)
    span = _span_of_function(source, language, function)
    if body is None or span is None:
        return None
    start, end = span
    candidate = source[:start + 1] + "\n    " + body + "\n" + source[end:]
    include = _needed_include(language, body)
    if include and include not in candidate:
        candidate = include + "\n" + candidate
    return candidate


def reference_candidate(source, requirement, function, language):
    """Returns (description, candidate_source) or None."""
    found = detect_intent(requirement)
    if not found or not function:
        return None
    intent, _ = found
    cand = (python_candidate(source, function, intent) if language == "python"
            else native_candidate(source, language, function, intent))
    if not cand or cand.strip() == source.strip():
        return None
    return (f"Rewrite '{function}' from the built-in reference for \"{intent.replace('_', ' ')}\" "
            "(keeps your function name, parameters and the code around it).", cand)


# ------------------------------------------------- requirement tests for C/C++/Java
def _fact(n):
    out = 1
    for i in range(2, n + 1):
        out *= i
    return out


def _gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def _prime(n):
    return n >= 2 and all(n % i for i in range(2, int(n ** 0.5) + 1))


# intent -> (parameter kinds, oracle, inputs); "wide" inputs only when the return is `long`
_NATIVE_ORACLES = {
    "sum_list": (["int[]"], sum, [([1, 2, 3], "normal"), ([], "edge"), ([5], "boundary"),
                                   ([-1, 1], "boundary"), ([10, -3, 4], "normal")]),
    "max_list": (["int[]"], max, [([3, 1, 2], "normal"), ([7], "boundary"),
                                   ([-5, -2, -9], "edge"), ([2, 2, 2], "boundary"),
                                   ([1, 9, 4, 9], "normal")]),
    "factorial": (["int"], _fact, [(0, "boundary"), (1, "boundary"), (5, "normal"),
                                    (3, "normal"), (7, "normal")]),
    "absolute": (["int"], abs, [(-3, "normal"), (4, "normal"), (0, "boundary"),
                                 (-100, "normal")]),
    "square": (["int"], lambda n: n * n, [(3, "normal"), (-4, "normal"), (0, "boundary"),
                                           (1, "boundary")]),
    "smaller": (["int", "int"], min, [((3, 5), "normal"), ((5, 3), "normal"), ((2, 2), "boundary"),
                                       ((-1, 0), "edge")]),
    "gcd": (["int", "int"], _gcd, [((12, 18), "normal"), ((7, 13), "normal"), ((10, 5), "normal"),
                                    ((9, 9), "boundary")]),
    "is_prime": (["int"], _prime, [(0, "edge"), (1, "edge"), (2, "boundary"), (9, "normal"),
                                    (13, "normal"), (25, "normal")]),
    "leap_year": (["int"], lambda y: (y % 4 == 0 and y % 100 != 0) or y % 400 == 0,
                  [(2000, "boundary"), (1900, "boundary"), (2024, "normal"), (2023, "normal")]),
    "palindrome": (["string"], lambda s: s == s[::-1],
                   [("level", "normal"), ("abc", "normal"), ("", "edge"), ("a", "boundary"),
                    ("ab", "boundary"), ("abca", "boundary"), ("abba", "normal")]),
    "count_vowels": (["string"], lambda s: sum(1 for ch in s if ch in "aeiou"),
                     [("hello", "normal"), ("", "edge"), ("xyz", "edge"), ("aeiou", "boundary")]),
    "string_length": (["string"], len, [("abc", "normal"), ("", "edge"),
                                         ("hello world", "normal")]),
}
# extra inputs that only make sense when the return type is wide enough (long)
_WIDE = {"square": [(46341, "boundary")], "factorial": [(15, "boundary")]}


def native_requirement_tests(requirement, source, language, function):
    """Tests built from the requirement for C/C++/Java, or None when not applicable.

    Returns {"template", "cases", "assumptions"} shaped like the Python templates.
    """
    found = detect_intent(requirement)
    if not found or found[0] not in _NATIVE_ORACLES or not function:
        return None
    intent = found[0]
    try:
        from sandbox.native_runner import parse_signature
        sig = parse_signature(source, language, function)
    except Exception:  # noqa: BLE001
        return None
    kinds, oracle, inputs = _NATIVE_ORACLES[intent]
    canon = [p["canon"] for p in sig["params"]]
    mapped = ["int" if c in ("int", "long") else c for c in canon]
    if mapped != kinds or sig["ret"]["canon"] not in ("int", "long", "bool"):
        return None  # shape does not match the recipe: a wrong oracle would be worse than none
    if intent in ("is_prime", "leap_year", "palindrome") and sig["ret"]["canon"] != "bool":
        return None
    if intent not in ("is_prime", "leap_year", "palindrome") and sig["ret"]["canon"] == "bool":
        return None
    inputs = list(inputs)
    if sig["ret"]["canon"] == "long" and canon and canon[0] == "int":
        inputs += _WIDE.get(intent, [])
    cases = []
    for number, (value, kind) in enumerate(inputs, 1):
        args = list(value) if isinstance(value, tuple) else [value]
        cases.append({"id": f"tpl-{number}", "kind": kind, "args": args,
                      "expected": oracle(*args), "note": "", "kwargs": {}})
    return {"template": f"{intent.replace('_', ' ')} (reference)", "cases": cases,
            "assumptions": ["Expected values come from a built-in reference solution."]}
