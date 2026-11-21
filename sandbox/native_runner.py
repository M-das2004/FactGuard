"""Native runner: compile and run C, C++ and Java candidates against test cases.

Standalone (imports nothing from FactGuard AI) because it is copied into a
temporary working folder and run as a separate process. Usage:

    python native_runner.py payload.json result.json

payload.json  {"language": "c"|"cpp"|"java", "source", "function", "cases",
               "timeout", "stop_on_fail"}
result.json   same per-case format as runner.py, plus compiler diagnostics:
              "compile_ok", "diagnostics", "unsupported", "sanitizers".

How it works
  1. Compile the candidate alone with strict warnings (this is where undeclared
     names, missing headers, non-existent methods and syntax errors surface).
  2. Read the function signature and generate a small driver `main` with one
     branch per test case (literal arguments, JSON result on stdout).
  3. Build the driver (C/C++: AddressSanitizer + UndefinedBehaviorSanitizer) and
     run it once per test case in its own process, so a crash or an endless loop
     affects only that case.

Supported parameter and return types (anything else is reported as unsupported):
  int, long, double, bool, string, int array, string array
  C:    int/long/double/bool, char*, int* followed by a length parameter
  C++:  the above plus std::string, std::vector<int>, std::vector<std::string>
  Java: int, long, double, boolean, String, int[], String[], List<Integer>, List<String>
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

MAX_OUT = 20000
FILES = {"c": "candidate.c", "cpp": "candidate.cpp"}
CANDIDATE_NAMES = ("candidate.c", "candidate.cpp")


class Unsupported(Exception):
    pass


# ---------------------------------------------------------------- utilities
def _env():
    keep = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "LANG")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["ASAN_OPTIONS"] = "detect_leaks=0:abort_on_error=0:detect_stack_use_after_return=0"
    env["UBSAN_OPTIONS"] = "print_stacktrace=1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run(cmd, cwd, timeout):
    """Run a command. Returns (returncode, stdout, stderr, timed_out)."""
    try:
        done = subprocess.run(cmd, cwd=cwd, env=_env(), capture_output=True, text=True,
                              errors="replace", timeout=timeout)
        return done.returncode, done.stdout[:MAX_OUT], _clean(done.stderr)[:MAX_OUT], False
    except subprocess.TimeoutExpired:
        return -9, "", "", True
    except OSError as exc:
        return 127, "", f"cannot start {cmd[0]}: {exc}", False


def _clean(text):
    """Drop JVM launcher noise such as 'Picked up JAVA_TOOL_OPTIONS'."""
    return "\n".join(line for line in text.splitlines()
                     if not line.startswith("Picked up "))


def _mask(src):
    """Blank out comments, strings, char literals and preprocessor lines."""
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
    masked = "".join(out)
    return re.sub(r"(?m)^[ \t]*#.*$", lambda m: " " * len(m.group(0)), masked)


# ------------------------------------------------------ diagnostics parsing
_GCC = re.compile(r"^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+): "
                  r"(?P<sev>fatal error|error|warning|note): (?P<msg>.*)$")
_JAVAC = re.compile(r"^(?P<file>[^:\n]+\.java):(?P<line>\d+): "
                    r"(?P<sev>error|warning): (?P<msg>.*)$")
_GCC_NOFILE = re.compile(r"^(?P<file>[^:\n]+): (?P<sev>fatal error|error): (?P<msg>.*)$")


def parse_diagnostics(text, language):
    """Compiler output -> [{severity, line, column, message, notes}]."""
    diags, lines = [], text.splitlines()
    for index, raw in enumerate(lines):
        match = _JAVAC.match(raw) if language == "java" else _GCC.match(raw)
        if not match:
            if language != "java" and not diags:
                alt = _GCC_NOFILE.match(raw)
                if alt:
                    diags.append({"severity": "error", "line": None, "column": None,
                                  "message": alt.group("msg"), "notes": []})
            continue
        sev = match.group("sev")
        if sev == "note":
            if diags:
                diags[-1]["notes"].append(match.group("msg"))
            continue
        entry = {"severity": "error" if "error" in sev else "warning",
                 "line": int(match.group("line")),
                 "column": int(match.group("col")) if "col" in match.groupdict()
                 and match.groupdict().get("col") else None,
                 "message": match.group("msg"), "notes": []}
        if language == "java":  # javac prints "  symbol:   method foo(int)" below
            for follow in lines[index + 1:index + 6]:
                if re.match(r"\s+(symbol|location):", follow):
                    entry["notes"].append(follow.strip())
        diags.append(entry)
    return diags[:25]


# ------------------------------------------------------- signature parsing
_C_SIG = re.compile(
    r"(?m)(?:^|(?<=[{};]))\s*((?:(?:static|inline|extern|const|unsigned|signed|struct)\s+)*"
    r"[A-Za-z_][\w:<>,\s\*&]*?[\s\*&])(\w+)\s*\(([^()]*)\)\s*(?:const\s*)?"
    r"(?:noexcept\s*)?\{")
_JAVA_SIG = re.compile(
    r"(?m)(?:^|(?<=[{};]))\s*((?:(?:public|private|protected|static|final|synchronized|abstract)\s+)*)"
    r"([\w<>\[\],.?\s]+?)\s+(\w+)\s*\(([^()]*)\)\s*(?:throws\s+[\w\s,.]+)?\{")

_BASE = {
    "int": "int", "short": "int", "int32_t": "int", "long": "long", "long int": "long",
    "long long": "long", "long long int": "long", "size_t": "long", "int64_t": "long",
    "double": "double", "float": "double", "bool": "bool", "_Bool": "bool",
    "boolean": "bool", "string": "string", "String": "string", "char*": "string",
    "vector<int>": "int[]", "vector<string>": "string[]", "int[]": "int[]",
    "String[]": "string[]", "List<Integer>": "int[]", "List<String>": "string[]",
    "int*": "int*",
}
_LEN_NAMES = re.compile(r"^(n|len|length|size|count|num\w*|n_\w+|\w*_len|\w*_size|\w*_count)$")


def _norm_type(text):
    text = re.sub(r"\b(const|struct|volatile|register|final|static|inline|extern)\b", " ", text)
    text = text.replace("std::", "").replace("java.util.", "")
    text = re.sub(r"\s*&\s*", " ", text)
    text = re.sub(r"\s*\*\s*", "*", text)
    text = re.sub(r"\s*<\s*", "<", text)
    text = re.sub(r"\s*>\s*", ">", text)
    text = re.sub(r"\s*,\s*", ",", text)
    text = re.sub(r"\s*\[\s*\]", "[]", text)
    text = re.sub(r"\b(unsigned|signed)\s+", "", text)
    return " ".join(text.split())


def _split_params(text):
    parts, depth, current = [], 0, ""
    for ch in text:
        if ch in "<(":
            depth += 1
        elif ch in ">)":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current)
    return parts


def parse_signature(source, language, function):
    """Return {"params": [...], "ret": {...}, "static": bool, "class": str|None}."""
    masked = _mask(source)
    cls = None
    if language == "java":
        found = re.search(r"\bclass\s+(\w+)", masked)
        cls = found.group(1) if found else None
        matches = [m for m in _JAVA_SIG.finditer(masked) if m.group(3) == function]
        if not matches:
            raise Unsupported(f"method '{function}' was not found in the Java source")
        m = matches[0]
        ret_raw, params_raw, static = m.group(2), m.group(4), "static" in m.group(1)
    else:
        matches = [m for m in _C_SIG.finditer(masked) if m.group(2) == function]
        if not matches:
            raise Unsupported(f"function '{function}' was not found in the source")
        m = matches[0]
        ret_raw, params_raw, static = m.group(1), m.group(3), True

    params = []
    for piece in _split_params(params_raw):
        piece = re.sub(r"=.*$", "", piece.strip()).strip()
        if piece in ("", "void"):
            continue
        name_match = re.search(r"(\w+)\s*(\[\s*\])?\s*$", piece)
        if not name_match:
            raise Unsupported(f"cannot read parameter '{piece}'")
        name = name_match.group(1)
        type_text = piece[:name_match.start()] + ("*" if name_match.group(2) and language != "java"
                                                   else "[]" if name_match.group(2) else "")
        raw = _norm_type(type_text)
        if raw not in _BASE:
            raise Unsupported(f"parameter type '{raw}' is not supported by the test harness")
        params.append({"raw": raw, "canon": _BASE[raw], "name": name})

    logical, i = [], 0
    while i < len(params):
        p = params[i]
        if p["canon"] == "int*":
            nxt = params[i + 1] if i + 1 < len(params) else None
            if not (nxt and nxt["canon"] == "int" and _LEN_NAMES.match(nxt["name"])):
                raise Unsupported(f"pointer parameter '{p['name']}' needs a length parameter "
                                  "right after it (for example: int* xs, int n)")
            logical.append({"raw": "int*", "canon": "int[]", "name": p["name"], "pair": True,
                            "len_name": nxt["name"]})
            i += 2
        else:
            logical.append(dict(p, pair=False))
            i += 1

    ret_raw = _norm_type(ret_raw)
    if ret_raw not in _BASE or _BASE[ret_raw] == "int*":
        raise Unsupported(f"return type '{ret_raw}' is not supported by the test harness")
    return {"params": logical, "ret": {"raw": ret_raw, "canon": _BASE[ret_raw]},
            "static": static, "class": cls}


# ---------------------------------------------------------- literal helpers
def _c_str(text):
    out = ['"']
    for byte in text.encode("utf-8"):
        ch = chr(byte)
        if 32 <= byte < 127 and ch not in '"\\?':
            out.append(ch)
        else:
            out.append("\\%03o" % byte)
    out.append('"')
    return "".join(out)


def _check(canon, value):
    """Does the JSON value fit the parameter type?"""
    isint = lambda v: isinstance(v, int) and not isinstance(v, bool)  # noqa: E731
    if canon in ("int", "long"):
        return isint(value)
    if canon == "double":
        return isinstance(value, (int, float)) and not isinstance(value, bool) \
            and math.isfinite(value)
    if canon == "bool":
        return isinstance(value, bool)
    if canon == "string":
        return isinstance(value, str)
    if canon == "int[]":
        return isinstance(value, list) and all(isint(v) for v in value)
    if canon == "string[]":
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    return False


def _num(v):
    return f"({v})" if (isinstance(v, (int, float)) and v < 0) else str(v)


def _decl_c(lang, p, idx, value):
    """Return (declaration code, call expressions) for one logical argument."""
    var, canon = f"a{idx}", p["canon"]
    if canon == "int":
        return "", [_num(value)]
    if canon == "long":
        return "", [_num(value) + "LL"]
    if canon == "double":
        return "", [_num(float(value))]
    if canon == "bool":
        return "", ["true" if value else "false"]
    if canon == "string":
        if "char*" in p["raw"]:
            return f"char {var}[] = {_c_str(value)};", [var]
        return f"std::string {var} = {_c_str(value)};", [var]
    if canon == "int[]":
        items = ", ".join(_num(v) for v in value)
        if p.get("pair"):
            size = max(1, len(value))
            return (f"int {var}[{size}] = {{{items or '0'}}};", [var, str(len(value))])
        return f"std::vector<int> {var} = {{{items}}};", [var]
    if canon == "string[]":
        items = ", ".join(_c_str(v) for v in value)
        return f"std::vector<std::string> {var} = {{{items}}};", [var]
    raise Unsupported(f"cannot build argument of type {canon}")


def _decl_java(p, idx, value):
    var, canon = f"a{idx}", p["canon"]
    if canon == "int":
        return "", [_num(value)]
    if canon == "long":
        return "", [_num(value) + "L"]
    if canon == "double":
        return "", [_num(float(value))]
    if canon == "bool":
        return "", ["true" if value else "false"]
    if canon == "string":
        return "", [json.dumps(value)]
    if canon == "int[]":
        items = ", ".join(_num(v) for v in value)
        if p["raw"] == "List<Integer>":
            return (f"java.util.List<Integer> {var} = new java.util.ArrayList<Integer>("
                    f"java.util.Arrays.asList(new Integer[]{{{items}}}));"), [var]
        return f"int[] {var} = new int[]{{{items}}};", [var]
    if canon == "string[]":
        items = ", ".join(json.dumps(v) for v in value)
        if p["raw"] == "List<String>":
            return (f"java.util.List<String> {var} = new java.util.ArrayList<String>("
                    f"java.util.Arrays.asList(new String[]{{{items}}}));"), [var]
        return f"String[] {var} = new String[]{{{items}}};", [var]
    raise Unsupported(f"cannot build argument of type {canon}")


# ------------------------------------------------------------ driver source
_C_HELPERS = r"""
static void cg_str(const char *s) {
    if (!s) { fputs("null", stdout); return; }
    putchar('"');
    for (; *s; s++) {
        unsigned char c = (unsigned char)*s;
        if (c == '"') fputs("\\\"", stdout);
        else if (c == '\\') fputs("\\\\", stdout);
        else if (c == '\n') fputs("\\n", stdout);
        else if (c == '\t') fputs("\\t", stdout);
        else if (c == '\r') fputs("\\r", stdout);
        else if (c < 32 || c >= 127) printf("\\u%04x", c);
        else putchar(c);
    }
    putchar('"');
}
"""


def build_driver(language, sig, cases, class_name):
    """Generate the driver source with one branch per test case."""
    params, ret, fn = sig["params"], sig["ret"]["canon"], sig["function"]
    branches = []
    for idx, case in enumerate(cases):
        decls, exprs = [], []
        for position, (p, value) in enumerate(zip(params, case["args"])):
            d, e = (_decl_java(p, position, value) if language == "java"
                    else _decl_c(language, p, position, value))
            if d:
                decls.append(d)
            exprs.extend(e)
        call = f"{fn}({', '.join(exprs)})"
        if language == "java":
            target = (f"{class_name}.{call}" if sig["static"]
                      else f"new {class_name}().{call}")
            body = " ".join(decls) + f" Object r = {target}; " \
                   f'System.out.println("CG_RESULT " + j(r)); '
        elif language == "c":
            body = " ".join(decls) + " " + _c_emit(ret, sig["ret"]["raw"], call)
        else:
            body = " ".join(decls) + " " + _cpp_emit(ret, sig["ret"]["raw"], call)
        branches.append(f"case {idx}: {{ {body} break; }}")
    switch = "\n        ".join(branches)

    if language == "c":
        return ("#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n"
                "#include <stdbool.h>\n#include <math.h>\n" + _C_HELPERS
                + "#define main FactGuard_user_main\n#include \"candidate.c\"\n#undef main\n"
                "int main(int argc, char **argv) {\n    int which = argc > 1 ? atoi(argv[1]) : -1;\n"
                f"    switch (which) {{\n        {switch}\n        default: return 3;\n    }}\n"
                "    return 0;\n}\n")
    if language == "cpp":
        return ("#include <iostream>\n#include <vector>\n#include <string>\n#include <cstdio>\n"
                "#include <cstdlib>\n#include <cmath>\n#include <cstring>\n" + _C_HELPERS
                + _CPP_HELPERS + "#define main FactGuard_user_main\n"
                "#include \"candidate.cpp\"\n#undef main\n"
                "int main(int argc, char **argv) {\n    int which = argc > 1 ? atoi(argv[1]) : -1;\n"
                f"    switch (which) {{\n        {switch}\n        default: return 3;\n    }}\n"
                "    return 0;\n}\n")
    return _JAVA_DRIVER.replace("@@SWITCH@@", switch)


def _c_emit(ret, raw, call):
    if ret == "int" or ret == "long":
        return f'long long r = (long long){call}; printf("CG_RESULT %lld\\n", r);'
    if ret == "double":
        return f'double r = (double){call}; printf("CG_RESULT %.17g\\n", r);'
    if ret == "bool":
        return f'bool r = (bool){call}; printf("CG_RESULT %s\\n", r ? "true" : "false");'
    return f'const char *r = {call}; fputs("CG_RESULT ", stdout); cg_str(r); putchar(10);'


def _cpp_emit(ret, raw, call):
    if ret in ("int", "long"):
        return f'long long r = (long long){call}; printf("CG_RESULT %lld\\n", r);'
    if ret == "double":
        return f'double r = (double){call}; printf("CG_RESULT %.17g\\n", r);'
    if ret == "bool":
        return f'bool r = (bool){call}; printf("CG_RESULT %s\\n", r ? "true" : "false");'
    if ret == "string":
        if "char*" in raw:
            return f'const char *r = {call}; fputs("CG_RESULT ", stdout); cg_str(r); putchar(10);'
        return (f'std::string r = {call}; fputs("CG_RESULT ", stdout); cg_str(r.c_str()); '
                "putchar(10);")
    if ret == "int[]":
        return (f'std::vector<int> r = {call}; fputs("CG_RESULT [", stdout); '
                'for (size_t i = 0; i < r.size(); i++) printf(i ? ",%d" : "%d", r[i]); '
                'puts("]");')
    return (f'std::vector<std::string> r = {call}; fputs("CG_RESULT [", stdout); '
            'for (size_t i = 0; i < r.size(); i++) { if (i) putchar(44); cg_str(r[i].c_str()); } '
            'puts("]");')


_CPP_HELPERS = ""

_JAVA_DRIVER = r"""
public class CGDriver {
    static String q(String s) {
        if (s == null) return "null";
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            if (c == '"') b.append("\\\"");
            else if (c == '\\') b.append("\\\\");
            else if (c == '\n') b.append("\\n");
            else if (c == '\t') b.append("\\t");
            else if (c == '\r') b.append("\\r");
            else if (c < 32 || c >= 127) b.append(String.format("\\u%04x", (int) c));
            else b.append(c);
        }
        return b.append('"').toString();
    }
    static String j(Object o) {
        if (o == null) return "null";
        if (o instanceof String) return q((String) o);
        if (o instanceof Double) {
            double d = (Double) o;
            return (Double.isNaN(d) || Double.isInfinite(d)) ? q(String.valueOf(d)) : Double.toString(d);
        }
        if (o instanceof int[]) {
            StringBuilder b = new StringBuilder("[");
            int[] a = (int[]) o;
            for (int i = 0; i < a.length; i++) { if (i > 0) b.append(','); b.append(a[i]); }
            return b.append(']').toString();
        }
        if (o instanceof Object[]) {
            StringBuilder b = new StringBuilder("[");
            Object[] a = (Object[]) o;
            for (int i = 0; i < a.length; i++) { if (i > 0) b.append(','); b.append(j(a[i])); }
            return b.append(']').toString();
        }
        if (o instanceof java.util.List) {
            StringBuilder b = new StringBuilder("[");
            boolean first = true;
            for (Object x : (java.util.List<?>) o) { if (!first) b.append(','); first = false; b.append(j(x)); }
            return b.append(']').toString();
        }
        return o.toString();
    }
    public static void main(String[] args) throws Throwable {
        int which = Integer.parseInt(args[0]);
        switch (which) {
        @@SWITCH@@
        default: System.exit(3);
        }
    }
}
"""


# -------------------------------------------------------- result handling
def _normalize(value):
    return value


def _equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    return a == b


def _exception_from(rc, err, language):
    """Work out an exception type, message and line from a failed process."""
    line = None
    if language == "java":
        match = re.search(r'Exception in thread "[^"]*" ([\w.$]+)(?:: (.*))?', err)
        if match:
            name = match.group(1).split(".")[-1]
            frames = re.findall(r"at [\w.$<>]+\((\w+)\.java:(\d+)\)", err)
            mine = next((int(n) for f, n in frames if f != "CGDriver"), None)
            return {"type": name, "message": (match.group(2) or "")[:300], "line": mine}
        if "OutOfMemoryError" in err:
            return {"type": "OutOfMemoryError", "message": "Java heap space", "line": None}
    asan = re.search(r"ERROR: AddressSanitizer: ([\w-]+)", err)
    if asan:
        frame = re.search(r"#\d+ 0x[0-9a-f]+ in [^\n]*? [^\s:]*candidate\.(?:c|cpp):(\d+)", err)
        line = int(frame.group(1)) if frame else None
        return {"type": "AddressSanitizer: " + asan.group(1), "message": "memory error",
                "line": line}
    ub = re.search(r"candidate\.(?:c|cpp):(\d+):\d+: runtime error: ([^\n]*)", err)
    if ub:
        text = ub.group(2)
        kind = re.split(r"[:,]", text)[0].strip()
        return {"type": "UndefinedBehavior: " + kind, "message": text[:300],
                "line": int(ub.group(1))}
    thrown = re.search(r"terminate called after throwing an instance of '([^']+)'", err)
    if thrown:
        what = re.search(r"what\(\):\s*(.*)", err)
        return {"type": thrown.group(1).replace("std::", ""),
                "message": (what.group(1) if what else "")[:300], "line": None}
    if rc == -11:
        return {"type": "SegmentationFault", "message": "invalid memory access", "line": None}
    if rc == -8:
        return {"type": "ArithmeticException", "message": "floating point / divide error",
                "line": None}
    if rc == -6:
        return {"type": "Abort", "message": "the program aborted", "line": None}
    return {"type": "NonZeroExit", "message": f"exit code {rc}", "line": None}


def _case_outcome(case, rc, out, err, timed_out, language, timeout):
    entry = {"id": case.get("id"), "kind": case.get("kind", "given"), "probe": False,
             "args": case.get("args", []), "expected": case.get("expected"),
             "status": "error", "actual": None, "actual_type": None, "exception": None}
    if timed_out:
        entry["status"] = "timeout"
        entry["exception"] = {"type": "Timeout", "message": f"no result after {timeout} s",
                              "line": None}
        return entry
    line = next((ln for ln in out.splitlines() if ln.startswith("CG_RESULT ")), None)
    if rc != 0 or line is None:
        entry["exception"] = _exception_from(rc, err, language)
        return entry
    try:
        actual = json.loads(line[len("CG_RESULT "):])
    except ValueError:
        entry["exception"] = {"type": "HarnessError", "message": "unreadable result",
                              "line": None}
        return entry
    entry["actual"], entry["actual_type"] = actual, type(actual).__name__
    entry["status"] = "pass" if _equal(actual, case.get("expected")) else "fail"
    return entry


# --------------------------------------------------------------------- main
def _compile_diagnostics(language, workdir, candidate):
    if language == "c":
        cmd = ["gcc", "-std=gnu11", "-fsyntax-only", "-Wall", "-Wextra", "-Wno-unused-parameter",
               "-Werror=implicit-function-declaration", "-Werror=implicit-int",
               "-Werror=int-conversion", "-Werror=incompatible-pointer-types", candidate]
    elif language == "cpp":
        cmd = ["g++", "-std=c++17", "-fsyntax-only", "-Wall", "-Wextra",
               "-Wno-unused-parameter", candidate]
    else:
        os.makedirs(os.path.join(workdir, "diag_out"), exist_ok=True)
        cmd = ["javac", "-Xlint:all", "-d", "diag_out", candidate]
    rc, out, err, timed_out = _run(cmd, workdir, 60)
    diags = parse_diagnostics(err + "\n" + out, language)
    if language == "java":
        _java_hints(diags, workdir)
    return rc, diags, err, timed_out


def _java_hints(diags, workdir):
    """javac never says "did you mean": ask javap which members the class really has."""
    import difflib
    cache = {}
    for diag in diags:
        if "cannot find symbol" not in diag["message"]:
            continue
        notes = " ".join(diag["notes"])
        symbol = re.search(r"symbol:\s+(?:method|variable)\s+(\w+)", notes)
        owner = (re.search(r"location:\s+(?:class|interface)\s+([\w.]+)", notes)
                 or re.search(r"of type\s+(\w+)", notes))
        if not (symbol and owner):
            continue
        cls = owner.group(1)
        if cls not in cache:
            names = set()
            for package in ("java.lang.", "java.util.", ""):
                rc, out, _err, _timed = _run(["javap", "-public", package + cls], workdir, 20)
                if rc == 0:
                    names = set(re.findall(r"\b(\w+)\s*\(", out)) | set(re.findall(r"\b(\w+);", out))
                    break
            cache[cls] = names
        close = difflib.get_close_matches(symbol.group(1), cache[cls] - {symbol.group(1)},
                                          n=1, cutoff=0.6)
        if close:
            diag["notes"].append(f"did you mean '{close[0]}'?")


def main():
    payload_path, result_path = sys.argv[1], sys.argv[2]
    with open(payload_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    workdir = os.path.dirname(os.path.abspath(payload_path))
    language, function = payload["language"], payload["function"]
    timeout = float(payload.get("timeout", 5))
    cases = payload.get("cases", [])
    started = time.time()
    result = {"language": language, "compile_ok": True, "diagnostics": [], "unsupported": None,
              "sanitizers": False, "import_error": None, "cases": [], "coverage": None,
              "stdout": ""}

    source = payload["source"]
    class_name = None
    if language == "java":
        source = re.sub(r"(?m)^\s*package\s+[\w.]+\s*;\s*$", "", source)
        found = re.search(r"\bclass\s+(\w+)", _mask(source))
        class_name = found.group(1) if found else "Candidate"
        candidate = class_name + ".java"
    else:
        candidate = FILES[language]
    with open(os.path.join(workdir, candidate), "w", encoding="utf-8") as handle:
        handle.write(source)

    rc, diags, err, timed_out = _compile_diagnostics(language, workdir, candidate)
    result["diagnostics"] = diags
    if timed_out:
        result.update(compile_ok=False, diagnostics=[{
            "severity": "error", "line": None, "column": None, "notes": [],
            "message": "the compiler timed out"}])
    elif rc != 0 and not any(d["severity"] == "error" for d in diags):
        result["compile_ok"] = False
        result["diagnostics"].append({"severity": "error", "line": None, "column": None,
                                      "notes": [], "message": err.strip()[:300] or
                                      f"the compiler failed (exit code {rc})"})
    elif any(d["severity"] == "error" for d in diags):
        result["compile_ok"] = False
    if not result["compile_ok"] or not cases:
        return _finish(result, result_path, started)

    try:
        sig = parse_signature(source, language, function)
    except Unsupported as exc:
        result["unsupported"] = str(exc)
        return _finish(result, result_path, started)
    sig["function"] = function

    runnable, entries = [], {}
    for case in cases:
        args = case.get("args", [])
        problem = None
        if len(args) != len(sig["params"]):
            problem = (f"the function takes {len(sig['params'])} argument(s) but the "
                       f"test case has {len(args)} (a C pointer plus its length parameter "
                       "counts as ONE argument: pass just the list)")
        else:
            for p, value in zip(sig["params"], args):
                if not _check(p["canon"], value):
                    problem = f"argument '{p['name']}' must be of type {p['canon']}"
                    break
        if problem:
            entries[case["id"]] = {
                "id": case.get("id"), "kind": case.get("kind", "given"), "probe": False,
                "args": args, "expected": case.get("expected"), "status": "error",
                "actual": None, "actual_type": None,
                "exception": {"type": "TestCaseTypeError", "message": problem, "line": None}}
        else:
            runnable.append(case)

    try:
        driver_name = "CGDriver.java" if language == "java" else \
            "driver." + ("c" if language == "c" else "cpp")
        with open(os.path.join(workdir, driver_name), "w", encoding="utf-8") as handle:
            handle.write(build_driver(language, sig, runnable, class_name))
    except Unsupported as exc:
        result["unsupported"] = str(exc)
        return _finish(result, result_path, started)

    if language == "java":
        build = ["javac", "-d", "out", candidate, driver_name]
        os.makedirs(os.path.join(workdir, "out"), exist_ok=True)
        runner = ["java", "-Xmx192m", "-XX:+UseSerialGC", "-XX:TieredStopAtLevel=1",
                  "-cp", "out", "CGDriver"]
        rc, _o, err, _t = _run(build, workdir, 90)
    else:
        compiler = "gcc" if language == "c" else "g++"
        std = "-std=gnu11" if language == "c" else "-std=c++17"
        base = [compiler, std, "-O0", "-g", "-Wno-all", "-w", driver_name, "-o", "prog"]
        if language == "c":
            base += ["-lm"]
        sanitize = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                    "-fno-omit-frame-pointer"]
        rc, _o, err, _t = _run(base[:1] + sanitize + base[1:], workdir, 90)
        result["sanitizers"] = rc == 0
        if rc != 0:  # sanitizers unavailable on this machine: build without them
            rc, _o, err, _t = _run(base, workdir, 90)
        runner = [os.path.join(workdir, "prog")]
    if rc != 0:
        result["unsupported"] = ("the generated test driver did not compile: "
                                 + " ".join(err.split())[:300])
        return _finish(result, result_path, started)

    def execute(case_index):
        case = runnable[case_index]
        rc2, out, err2, timed = _run(runner + [str(case_index)], workdir, timeout)
        return _case_outcome(case, rc2, out, err2, timed, language, timeout)

    results = {}
    if payload.get("stop_on_fail"):
        for index in range(len(runnable)):
            outcome = execute(index)
            results[runnable[index]["id"]] = outcome
            if outcome["status"] != "pass":
                break
    else:
        workers = max(1, min(4, os.cpu_count() or 1))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for index, outcome in enumerate(pool.map(execute, range(len(runnable)))):
                results[runnable[index]["id"]] = outcome
    results.update(entries)
    result["cases"] = [results[c["id"]] for c in cases if c["id"] in results]
    return _finish(result, result_path, started)


def _finish(result, result_path, started):
    result["elapsed"] = round(time.time() - started, 3)
    with open(result_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle)


if __name__ == "__main__":
    main()
