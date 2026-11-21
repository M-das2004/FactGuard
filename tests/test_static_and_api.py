from modules.api_validator import validate_api
from modules.findings import API, ERROR, NAMING, STRUCTURE, SYNTAX, WARNING
from modules.input_manager import detect_function_name, normalize_cases, validate_inputs
from modules.static_analyzer import analyze_static


def test_syntax_error_is_reported_with_line():
    result = analyze_static("def f(x)\n    return x")
    assert not result["syntax_ok"]
    assert result["findings"][0]["label"] == SYNTAX
    assert result["findings"][0]["line"] == 1


def test_undefined_name_found():
    result = analyze_static("def f():\n    return missing_name\n")
    labels = [(f["label"], f["severity"]) for f in result["findings"]]
    assert (NAMING, ERROR) in labels


def test_clean_code_has_no_defects():
    result = analyze_static("def f(xs):\n    return sum(xs)\n")
    assert not [f for f in result["findings"] if f["severity"] == ERROR]


def test_range_step_zero_and_constant_index():
    result = analyze_static("def f():\n    a = [1, 2]\n    b = [1, 2][5]\n"
                            "    return list(range(0, 3, 0))\n")
    assert len([f for f in result["findings"] if f["label"] == STRUCTURE]) == 2


def test_fake_attribute_gets_suggestion():
    findings = validate_api("import math\ndef f(x):\n    return math.sqroot(x)\n")
    assert findings and findings[0]["label"] == API
    assert "sqrt" in findings[0]["message"]


def test_bad_from_import_and_missing_module():
    findings = validate_api("from math import factorial2\nimport nothing_here_123\n")
    messages = " ".join(f["message"] for f in findings)
    assert "factorial2" in messages and "nothing_here_123" in messages


def test_signature_mismatch():
    findings = validate_api("import math\nmath.floor(1, 2)\n")
    assert any("signature" in f["message"] for f in findings)


def test_unlisted_module_is_only_a_warning():
    findings = validate_api("import pytest\n")  # installed, but not allowlisted
    assert findings and findings[0]["severity"] == WARNING


def test_function_detection_and_input_validation():
    assert detect_function_name("x = 1\ndef go(a):\n    pass\n") == "go"
    assert detect_function_name("def go(a)\n    pass\n") == "go"
    assert not validate_inputs("r", "   ")["ok"]
    assert validate_inputs("", "def f(): pass")["warnings"]


def test_case_normalisation():
    cases, errors = normalize_cases('[{"input": 3, "expected": 9}, {"args": [1, 2], "expected": 3}]')
    assert [c["args"] for c in cases] == [[3], [1, 2]] and not errors
    cases, errors = normalize_cases("not json")
    assert not cases and errors
    cases, errors = normalize_cases('[{"input": 1}]')
    assert not cases and errors
