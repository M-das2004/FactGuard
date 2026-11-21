"""Verification Engine: a repair is accepted only if every check passes.

The repair method (rules, mutation search or an LLM) is never the judge.
This module repeats the static checks and the full test suite on the
candidate and compares it with the original run (regression check).

Works for Python and for C, C++ and Java (where "static checks" means the
compiler: errors block a candidate, warnings do not).
"""
from .api_validator import validate_api
from .execution_engine import NATIVE, run_in_sandbox
from .findings import ERROR, defects
from .static_analyzer import analyze_static


def baseline_from_run(run):
    """Map test id -> status for the original code."""
    return {case["id"]: case["status"] for case in (run or {}).get("cases", [])}


def verify_candidate(source, function, cases, baseline, *, timeout=5,
                     allow_local=False, language="python"):
    """Run all required checks on candidate source code.

    Returns {"accepted": bool, "checks": [{"name", "passed", "detail"}], "run": ...}.
    """
    checks = []
    native = language in NATIVE

    def add(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    required = [c for c in cases if not c.get("probe") and c.get("kind") != "assumption"]

    if native:
        # The compiler is the static check; it runs inside the sandbox with the tests.
        run = run_in_sandbox(source, function, required or cases, timeout=timeout,
                             allow_local=allow_local, language=language, stop_on_fail=True)
        if not run.get("ok", True):
            add("Sandbox ran the candidate", False, run.get("runner_error", ""))
            return {"accepted": False, "checks": checks, "run": run}
        errors = [d for d in run.get("diagnostics", []) if d["severity"] == "error"]
        add("Compiles without errors", run.get("compile_ok", True) and not errors,
            "; ".join(f"line {d['line']}: {d['message']}" for d in errors[:3]))
        if not run.get("compile_ok", True):
            return {"accepted": False, "checks": checks, "run": run}
        if run.get("unsupported"):
            add("Test harness can run this code", False, run["unsupported"])
            return {"accepted": False, "checks": checks, "run": run}
    else:
        static = analyze_static(source)
        problems = defects(static["findings"])
        if static["syntax_ok"]:
            problems += [f for f in validate_api(tree=static["tree"])
                         if f["severity"] == ERROR]
        add("Static and API checks are clean", not problems,
            "; ".join(f"line {f['line']}: {f['message']}" for f in problems[:3]))
        if not static["syntax_ok"]:
            return {"accepted": False, "checks": checks, "run": None}
        run = run_in_sandbox(source, function, cases, timeout=timeout,
                             allow_local=allow_local) if cases else {
            "ok": True, "cases": [], "import_error": None}
        if not run.get("ok", True):
            add("Sandbox ran the candidate", False, run.get("runner_error", ""))
            return {"accepted": False, "checks": checks, "run": run}
        add("Module and function load without errors", not run.get("import_error"),
            str(run.get("import_error") or ""))

    results = {c["id"]: c for c in run["cases"]}
    failing = [c for c in required if results.get(c["id"], {}).get("status") != "pass"]
    if required:
        add("All required tests pass (original + requirement-based)", not failing,
            f"{len(required) - len(failing)}/{len(required)} passed"
            + (f"; first failure: {failing[0]['id']}" if failing else ""))
    else:
        add("All required tests pass (original + requirement-based)", True,
            "no tests were available, so only static checks could be verified")

    # Only compare tests that were actually re-run on the candidate.
    rerun = {c["id"] for c in (required if native else cases)}
    baseline = {cid: status for cid, status in baseline.items() if cid in rerun}
    regressions = [cid for cid, status in baseline.items()
                   if status == "pass" and results.get(cid, {}).get("status") != "pass"]
    add("Regression: tests that passed before still pass", not regressions,
        ", ".join(regressions[:5]))

    if not native:
        new_crashes = [cid for cid, status in baseline.items()
                       if status == "ok" and results.get(cid, {}).get("status") != "ok"]
        add("No new crashes on coverage-probe inputs", not new_crashes,
            ", ".join(new_crashes[:5]))

    timeouts = [c["id"] for c in run["cases"] if c["status"] == "timeout"
                and baseline.get(c["id"]) != "timeout"]
    add("No new timeouts", not timeouts, ", ".join(timeouts[:5]))

    return {"accepted": all(check["passed"] for check in checks), "checks": checks,
            "run": run}
