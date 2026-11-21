from modules.findings import ERROR
from modules.pipeline import analyze
from modules.report_generator import to_json, to_markdown

DEMO_REQ = "Find all words containing the letter 'a' from a list of words."
DEMO_BAD = 'def find_words(words):\n    return [w for w in words if w.startswith("a")]\n'
DEMO_GOOD = 'def find_words(words):\n    return [w for w in words if "a" in w]\n'
SUM_REQ = "Return the sum of a list of numbers."

NO_RECIPE_REQ = "Return the total of the numbers in xs."
NO_RECIPE_CASES = '[{"input": [1, 2], "expected": 3}, {"input": [], "expected": 0}]'


def go(req, src, run_mode, **kw):
    return analyze(req, src, allow_local=run_mode["allow_local"],
                   timeout=2, **kw)


def test_demo_bug_detected_and_repaired(run_mode):
    result = go(DEMO_REQ, DEMO_BAD, run_mode)
    assert result["verdict"].startswith("Defects")
    assert any(f["label"] == "Logical hallucination" and f["severity"] == ERROR
               for f in result["findings"])
    repair = result["repair"]
    assert repair["accepted"] and '"a" in w' in repair["source"]
    assert all(c["passed"] for c in repair["verification"]["checks"])


def test_correct_code_is_not_flagged_or_repaired(run_mode):
    result = go(DEMO_REQ, DEMO_GOOD, run_mode)
    assert result["status"] == "no_defect_found"
    assert result["repair"] is None


def test_original_source_is_never_modified(run_mode):
    original = DEMO_BAD
    result = go(DEMO_REQ, original, run_mode)
    assert original == DEMO_BAD and result["repair"]["source"] != original


def test_each_fault_type(run_mode):
    cases = {
        "Naming / identity issue": (SUM_REQ,
            "def t(xs):\n    s = 0\n    for x in xs:\n        s += x\n    return ss\n"),
        "External API issue": ("Return the square root of a number.",
            "import math\ndef r(n):\n    return math.sqroot(n)\n"),
        "Syntax issue": (SUM_REQ, "def t(xs)\n    return sum(xs)\n"),
        "Resource issue": (SUM_REQ, "def t(xs):\n    while True:\n        pass\n"),
    }
    for label, (req, src) in cases.items():
        result = go(req, src, run_mode)
        assert label in result["verdict"], (label, result["verdict"])


def test_repair_is_rejected_when_no_candidate_passes(run_mode):
    # The requirement cannot be met by any single small change to this code.
    src = "def t(xs):\n    return 42\n"
    result = go(NO_RECIPE_REQ, src, run_mode, cases=NO_RECIPE_CASES)
    assert result["verdict"].startswith("Defects")
    assert result["repair"] and not result["repair"]["accepted"]


def test_reference_solution_gives_correct_code(run_mode):
    result = go(SUM_REQ, "def t(xs):\n    return 42\n", run_mode)
    assert result["repair"]["accepted"]
    assert result["repair"]["strategy"] == "reference solution"
    assert "return total" in result["repair"]["source"]


def test_coverage_guided_probes_raise_coverage(run_mode):
    src = ('def t(xs):\n    if len(xs) > 3:\n        return sum(xs)\n    return sum(xs)\n')
    result = go(SUM_REQ, src, run_mode, cases='[{"input": [1, 2], "expected": 3}]',
                use_templates=False, use_coverage_guided=True)
    assert result["coverage"]["branch_percent"] == 100.0
    assert result["coverage"]["probes_added"] > 0


def test_sandbox_failure_never_reads_as_clean(run_mode, monkeypatch):
    import modules.pipeline as pipeline
    monkeypatch.setattr(pipeline, "run_in_sandbox",
                        lambda *a, **k: {"ok": False, "runner_error": "boom", "cases": [],
                                         "coverage": None, "import_error": None})
    result = go(SUM_REQ, "def t(xs):\n    return sum(xs)\n", run_mode)
    assert result["verdict"].startswith("Analysis incomplete")


def test_bad_input_is_rejected_without_crashing(run_mode):
    assert not go("", "", run_mode)["ok"]


def test_reports_render(run_mode):
    result = go(DEMO_REQ, DEMO_BAD, run_mode)
    assert "Logical hallucination" in to_markdown(result, DEMO_REQ, DEMO_BAD)
    assert '"verdict"' in to_json(result)


def test_llm_hook_candidate_is_still_verified(run_mode):
    src = "def t(xs):\n    return 42\n"
    liar = lambda prompt: "```python\ndef t(xs):\n    return 7\n```"
    assert not go(NO_RECIPE_REQ, src, run_mode, cases=NO_RECIPE_CASES,
                  llm_fn=liar)["repair"]["accepted"]
    honest = lambda prompt: "```python\ndef t(xs):\n    return sum(xs)\n```"
    result = go(NO_RECIPE_REQ, src, run_mode, cases=NO_RECIPE_CASES, llm_fn=honest)
    assert result["repair"]["accepted"]
    assert result["repair"]["strategy"].startswith("LLM")
