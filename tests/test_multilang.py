"""C, C++ and Java: compile-time and run-time hallucinations, repair, verification."""
import pytest

from modules.execution_engine import missing_tools
from modules.multilang import detect_language
from modules.pipeline import analyze

SUM_CASES = ('[{"args": [[1, 2, 3]], "expected": 6}, {"args": [[]], "expected": 0}, '
             '{"args": [[5]], "expected": 5}]')


def need(language):
    if missing_tools(language):
        pytest.skip(f"{language} compiler is not installed on this computer")


def go(req, src, language, run_mode, **kw):
    need(language)
    kw.setdefault("timeout", 5)
    return analyze(req, src, language=language, allow_local=True, **kw)


C_SUM = "int total(const int *xs, int n) {\n    int s = 0;\n    for (int i = %s; i %s n; i++) s += xs[i];\n    return s;\n}\n"
REQ_SUM = "Return the sum of a list of numbers."


def test_language_detection():
    assert detect_language("def f(x):\n    return x\n") == "python"
    assert detect_language("#include <stdio.h>\nint f(int x) { return x; }\n") == "c"
    assert detect_language("#include <vector>\nstd::vector<int> f() { return {}; }\n") == "cpp"
    assert detect_language("public class A {\n  static int f() { return 1; }\n}\n") == "java"


def test_c_logic_bug_found_and_repaired(run_mode):
    result = go(REQ_SUM, C_SUM % ("1", "<"), "c", run_mode, cases=SUM_CASES)
    assert result["status"] == "defects"
    assert result["repair"]["accepted"]
    assert "i = 0" in result["repair"]["source"]


def test_c_correct_code_is_not_flagged(run_mode):
    result = go(REQ_SUM, C_SUM % ("0", "<"), "c", run_mode, cases=SUM_CASES)
    assert result["status"] != "defects"


def test_c_buffer_overflow_is_found_by_the_sanitizer(run_mode):
    result = go(REQ_SUM, C_SUM % ("0", "<="), "c", run_mode, cases=SUM_CASES, do_repair=False)
    assert result["status"] == "defects"
    assert any("Sanitizer" in f["evidence"] or "overflow" in f["message"].lower()
               or "out-of-bounds" in f["message"].lower() for f in result["findings"])


def test_c_hallucinated_function(run_mode):
    code = "#include <string.h>\nint len(const char *s) {\n    return (int) strlenn(s);\n}\n"
    result = go("Return the length of a string.", code, "c", run_mode,
                cases='[{"args": ["abc"], "expected": 3}]')
    assert result["status"] == "defects"
    assert result["repair"]["accepted"] and "strlen(" in result["repair"]["source"]


def test_cpp_undeclared_name(run_mode):
    code = "#include <vector>\nint total(std::vector<int> xs) {\n    int s = 0;\n    for (int x : xs) s += x;\n    return ss;\n}\n"
    result = go(REQ_SUM, code, "cpp", run_mode, cases=SUM_CASES)
    assert result["status"] == "defects"
    assert any(f["label"] == "Naming / identity issue" for f in result["findings"])


def test_cpp_first_letter_bug_repaired_by_rule(run_mode):
    code = ("#include <string>\n#include <vector>\nstd::vector<std::string> findWords("
            "std::vector<std::string> words) {\n    std::vector<std::string> out;\n"
            "    for (auto &w : words)\n        if (!w.empty() && w[0] == 'a') out.push_back(w);\n"
            "    return out;\n}\n")
    result = go("Find all words containing the letter 'a' from a list of words.", code,
                "cpp", run_mode)
    assert result["status"] == "defects" and result["repair"]["accepted"]


def test_java_hallucinated_method_gets_a_javap_hint_and_repair(run_mode):
    code = "public class Solution {\n    public static double root(double n) {\n        return Math.sqroot(n);\n    }\n}\n"
    result = go("Return the square root of a number.", code, "java", run_mode,
                cases='[{"args": [16], "expected": 4.0}, {"args": [2], "expected": 1.4142135623730951}]')
    assert result["status"] == "defects"
    assert any("sqrt" in " ".join(f.get("notes", [])) for f in result["findings"])
    assert result["repair"]["accepted"] and "Math.sqrt" in result["repair"]["source"]


def test_java_runtime_exception_is_reported(run_mode):
    code = ("public class Solution {\n    public static int total(int[] xs) {\n        int s = 0;\n"
            "        for (int i = 0; i <= xs.length; i++) s += xs[i];\n        return s;\n    }\n}\n")
    result = go(REQ_SUM, code, "java", run_mode, cases=SUM_CASES, do_repair=False)
    assert result["status"] == "defects"
    assert any("ArrayIndexOutOfBounds" in f["message"] for f in result["findings"])


def test_java_infinite_recursion_is_a_resource_issue(run_mode):
    code = "public class Solution {\n    public static int fact(int n) {\n        return n * fact(n - 1);\n    }\n}\n"
    result = go("Compute the factorial of a number.", code, "java", run_mode, do_repair=False)
    assert result["status"] == "defects"
    assert any(f["label"] == "Resource issue" for f in result["findings"])


def test_unsupported_signature_is_unverified_not_clean(run_mode):
    code = "#include <stdlib.h>\nint *make(int n) {\n    return malloc(n * sizeof(int));\n}\n"
    result = go("Return an array of n integers.", code, "c", run_mode,
                cases='[{"args": [3], "expected": [0, 0, 0]}]', do_repair=False)
    assert result["status"] != "no_defect_found"


def test_missing_toolchain_is_reported_clearly(run_mode, monkeypatch):
    import modules.pipeline as pipeline
    monkeypatch.setattr(pipeline, "missing_tools", lambda language: ["gcc"], raising=False)
    import modules.execution_engine as engine
    monkeypatch.setattr(engine, "missing_tools", lambda language: ["gcc"])
    result = analyze(REQ_SUM, C_SUM % ("0", "<"), language="c", allow_local=True)
    assert result["status"] in ("incomplete", None) or not result["ok"] or \
        "gcc" in " ".join(result["errors"] + result["warnings"]) + result.get("verdict", "")


@pytest.mark.parametrize("language,function,requirement,source", [
    ("c", "biggest", "Return the largest number in a list.",
     "int biggest(const int *xs, int n) {\n    int b = 0;\n    for (int i = 0; i < n; i++) if (xs[i] < b) b = xs[i];\n    return b;\n}\n"),
    ("cpp", "isPal", "Check whether a string is a palindrome.",
     "#include <string>\n\nbool isPal(std::string s) {\n    return s[0] == s[s.size() - 1];\n}\n"),
    ("cpp", "square", "Return the square of an integer.",
     "long long square(int n) {\n    int r = n * n;\n    return r;\n}\n"),
    ("java", "f", "Compute the factorial of a number.",
     "public class M {\n  public static int f(int n) {\n    return 0;\n  }\n}\n"),
])
def test_requirement_tests_catch_and_reference_repair_fixes(run_mode, language, function,
                                                            requirement, source):
    result = go(requirement, source, language, run_mode, function_name=function)
    assert result["status"] == "defects"
    assert result["repair"]["accepted"], result["repair"]["why_not"]
    # the corrected code really is correct: re-analysing it finds no defect
    again = go(requirement, result["repair"]["source"], language, run_mode,
               function_name=function)
    assert again["status"] != "defects"
