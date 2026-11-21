import ast

import pytest

from modules.coverage_analyzer import summarize_coverage
from modules.execution_engine import SandboxUnavailable, run_in_sandbox
from modules.test_generator import generate_from_requirement, suggest_probe_cases


def run(source, cases, mode, **kw):
    return run_in_sandbox(source, "f", cases, allow_local=True, **kw)


def case(args, expected=None, **extra):
    return {"id": "c", "args": args, "expected": expected, **extra}


def test_pass_and_fail(run_mode):
    result = run("def f(x):\n    return x + 1\n",
                 [dict(case([1], 2), id="a"), dict(case([1], 3), id="b")], run_mode)
    assert [c["status"] for c in result["cases"]] == ["pass", "fail"]


def test_exception_reports_line(run_mode):
    result = run("def f(x):\n    return x[5]\n", [case([[1]], 1)], run_mode)
    exc = result["cases"][0]["exception"]
    assert exc["type"] == "IndexError" and exc["line"] == 2


def test_timeout_is_caught_and_later_cases_still_run(run_mode):
    src = "def f(x):\n    while x:\n        pass\n    return x\n"
    cases = [dict(case([1], 1), id="loop"), dict(case([0], 0), id="ok")]
    result = run(src, cases, run_mode, timeout=1)
    assert result["ok"]
    assert [c["status"] for c in result["cases"]] == ["timeout", "pass"]


def test_module_level_error_is_reported(run_mode):
    result = run("raise ValueError('boom')\ndef f(x): return x\n", [case([1], 1)], run_mode)
    assert result["import_error"]["type"] == "ValueError"


def test_tuple_and_list_compare_equal(run_mode):
    result = run("def f(x):\n    return (x, x)\n", [case([1], [1, 1])], run_mode)
    assert result["cases"][0]["status"] == "pass"


def test_branch_coverage_and_probes(run_mode):
    src = 'def f(score):\n    if score >= 50:\n        return "pass"\n    return "fail"\n'
    first = run(src, [case([80], "pass")], run_mode)
    cov = summarize_coverage(first["coverage"])
    assert cov["branch_percent"] == 50.0 and cov["missing_branches"] == [[2, 4]]
    probes = suggest_probe_cases(ast.parse(src), "f", ["score"], [{"args": [80]}],
                                 cov["missing_branches"])
    assert probes
    second = run(src, [case([80], "pass")] + probes, run_mode)
    assert summarize_coverage(second["coverage"])["branch_percent"] == 100.0


def test_local_run_refused_without_permission():
    with pytest.raises(SandboxUnavailable):
        run_in_sandbox("def f(): pass", "f", [], allow_local=False)


def test_templates_match_requirements():
    gen = generate_from_requirement("Find all words containing the letter 'a' from a list")
    assert gen and gen["template"] == "filter words containing a letter"
    assert generate_from_requirement("Order a pizza from the API") is None


def test_thread_timeout_path_used_on_windows(tmp_path):
    """Windows has no SIGALRM: the runner falls back to a worker-thread timeout."""
    import json
    import os
    import subprocess
    import sys
    from modules.execution_engine import RUNNER_SOURCE

    cases = [{"id": "loop", "args": [1], "expected": 1},
             {"id": "ok", "args": [0], "expected": 0}]
    payload = {"source": "def f(x):\n    while x:\n        pass\n    return x\n",
               "function": "f", "cases": cases, "timeout": 1}
    (tmp_path / "payload.json").write_text(json.dumps(payload))
    env = dict(os.environ, FactGuard_THREAD_TIMEOUT="1")
    subprocess.run([sys.executable, str(RUNNER_SOURCE), str(tmp_path / "payload.json"),
                    str(tmp_path / "result.json")], env=env, timeout=60, check=True)
    result = json.loads((tmp_path / "result.json").read_text())
    assert [c["status"] for c in result["cases"]] == ["timeout", "pass"]
    assert result["coverage"] is not None
