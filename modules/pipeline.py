"""Pipeline: runs the six FactGuard AI steps and returns one result dictionary.

 1 input  ->  2 static + API  ->  3 tests (+ coverage)  ->  4 classify
          ->  5 repair        ->  6 re-check, assurance level and report

Languages: Python, C, C++ and Java. For C/C++/Java the "static + API" step is the
compiler (strict warnings) and the tests run in the native sandbox runner.
"""
from .api_validator import validate_api
from .assurance import assess
from .coverage_analyzer import describe_missing_branches, summarize_coverage
from .execution_engine import NATIVE, run_in_sandbox
from .findings import ERROR, defects
from .hallucination_detector import classify_run, combine
from .input_manager import validate_inputs
from .multilang import LANGUAGES, detect_language, diagnostics_to_findings, locate_function
from .repair_engine import repair
from .static_analyzer import analyze_static
from .test_generator import (generate_from_requirement, merge_cases,
                             suggest_probe_cases)
from .test_strength import edge_case_gaps, measure
from .verification_engine import baseline_from_run, verify_candidate


def _function_info(tree, name):
    for node in tree.body if tree else []:
        if getattr(node, "name", None) == name and hasattr(node, "args"):
            return node.lineno, [a.arg for a in node.args.args]
    return None, []


def _python_arity(source, function):
    """Number of parameters of `function`, or None when it cannot be determined."""
    import ast
    try:
        for node in ast.parse(source).body:
            if isinstance(node, ast.FunctionDef) and node.name == function:
                return len(node.args.args)
    except SyntaxError:
        pass
    return None


def _oracle(given, template):
    if given and template:
        return "your test cases + requirement template"
    if given:
        return "your test cases"
    if template:
        return "requirement template"
    return "none"


def analyze(requirement, source, *, language="python", function_name=None, cases=None,
            timeout=5, allow_local=False, use_templates=True,
            use_coverage_guided=False, do_repair=True, llm_fn=None, output_type=None,
            measure_strength=True):
    """Analyze one piece of code. Never raises for bad user code.

    `language` is "python", "c", "cpp", "java" or "auto" (guess from the text).
    """
    result = {"ok": False, "steps": [], "errors": [], "warnings": []}
    steps = result["steps"]
    if language == "auto":
        language = detect_language(source)
    if language not in LANGUAGES:
        result["errors"] = [f"Unsupported language '{language}'."]
        return result
    native = language in NATIVE
    result["language"] = language

    # Step 1: input
    inputs = validate_inputs(requirement, source, function_name, cases, language)
    result["warnings"] += inputs["warnings"]
    if not inputs["ok"]:
        result["errors"] = inputs["errors"]
        return result
    function = inputs["function_name"]
    steps.append("Inputs validated")

    given = inputs["cases"]
    template = generate_from_requirement(requirement) if use_templates else None
    if template and language == "python":  # arity guard: wrong shape = wrong oracle
        wanted = len(template["cases"][0]["args"])
        have = _python_arity(source, function)
        if have is not None and have != wanted:
            result["warnings"].append(
                f"Requirement template '{template['template']}' was skipped: it tests "
                f"functions with {wanted} argument(s) but '{function}' takes {have}.")
            template = None
    if native and use_templates:
        # richer, type-checked tests for C/C++/Java; fall back to the generic template
        from .reference_solutions import native_requirement_tests
        template = native_requirement_tests(requirement, source, language, function) or template
    generated = template["cases"] if template else []
    all_cases = merge_cases(given, generated)
    result.update({"template": template["template"] if template else None,
                   "assumptions": template["assumptions"] if template else [],
                   "cases": all_cases, "function": function,
                   "oracle": _oracle(bool(given), bool(template))})

    run, run_findings, coverage, probes = None, [], summarize_coverage(None), []
    static_findings, api, unsupported = [], [], None
    function_line = None

    if native:
        # Steps 2 and 3 together: the sandbox compiles, then runs the tests.
        run = run_in_sandbox(source, function or "", all_cases, timeout=timeout,
                             allow_local=allow_local, language=language)
        if run.get("ok"):
            static_findings = diagnostics_to_findings(run.get("diagnostics", []), source,
                                                      language)
            unsupported = run.get("unsupported")
            syntax_ok = run.get("compile_ok", True)
            if unsupported:
                result["warnings"].append(
                    f"The tests could not be run: {unsupported}. Only compiler checks ran.")
            if syntax_ok and not unsupported:
                run_findings = classify_run(run, function, locate_function(source, function),
                                            output_type)
            steps.append("Compiler checks done; tests executed")
        else:
            syntax_ok = True
            result["errors"].append("The sandbox could not run: " + run.get("runner_error", ""))
        if not all_cases and syntax_ok and not unsupported:
            result["warnings"].append(
                "No test cases and no matching requirement template: only compiler "
                "checks ran. Add test cases for a real answer.")
        result["syntax_ok"] = syntax_ok
        result.update({"static": static_findings, "api": []})
    else:
        # Step 2: static and API checks
        static = analyze_static(source)
        static_findings = static["findings"]
        api = validate_api(tree=static["tree"]) if static["syntax_ok"] else []
        syntax_ok = static["syntax_ok"]
        steps.append("Static and API checks done")
        result.update({"static": static_findings, "api": api, "syntax_ok": syntax_ok})

        # Step 3: tests and coverage (only when the code can be parsed)
        function_line, params = _function_info(static["tree"], function)
        if syntax_ok and function:
            if not all_cases:
                result["warnings"].append(
                    "No test cases and no matching requirement template: only static "
                    "checks and crash probes could run. Add test cases for stronger results.")
            base = [c for c in all_cases if c["kind"] != "assumption"] or all_cases
            seed_cases = all_cases or ([{"id": "seed", "args": [], "kwargs": {},
                                         "kind": "seed", "probe": True}] if not params else [])
            run = run_in_sandbox(source, function, seed_cases, timeout=timeout,
                                 allow_local=allow_local)
            if run.get("ok"):
                coverage = summarize_coverage(run["coverage"])
                if use_coverage_guided and coverage["missing_branches"] and base:
                    probes = suggest_probe_cases(static["tree"], function, params, base,
                                                 coverage["missing_branches"])
                    if probes:
                        before = coverage
                        run2 = run_in_sandbox(source, function, all_cases + probes,
                                              timeout=timeout,
                                              allow_local=allow_local)
                        if run2.get("ok"):
                            run = run2
                            coverage = summarize_coverage(run2["coverage"])
                            coverage["before_percent"] = before["branch_percent"]
                            coverage["probes_added"] = len(probes)
                run_findings = classify_run(run, function, function_line, output_type,
                                            requirement)
                steps.append("Tests executed and coverage measured")
            else:
                result["errors"].append("The sandbox could not run: "
                                        + run.get("runner_error", ""))
        elif syntax_ok:
            result["warnings"].append("No function to test, so dynamic checks were skipped.")

    coverage["missing_notes"] = describe_missing_branches(
        coverage.get("missing_branches", []), source) if not native else []
    cases_run = [c for c in (run or {}).get("cases", []) if not c.get("probe")]
    result.update({"run": run, "coverage": coverage, "probes": probes,
                   "tests_total": len(cases_run),
                   "tests_passed": len([c for c in cases_run if c["status"] == "pass"])})

    # Step 4: classify
    findings = combine(static_findings, api, run_findings, source, requirement)
    result["findings"] = findings
    steps.append("Findings classified")

    # Test strength (mutation score): only needed to judge a "no defect" outcome.
    required = [c for c in all_cases if c["kind"] != "assumption"]
    strength = None
    if (measure_strength and not defects(findings) and not result["errors"] and required
            and function and result["tests_total"] and not unsupported):
        strength = measure(source, language, function, required, timeout=timeout,
                           allow_local=allow_local)
        steps.append("Test strength measured")
    result["strength"] = strength
    gaps = edge_case_gaps(required) if (required and result["tests_total"]) else []
    result["edge_gaps"] = gaps
    result.update(assess(findings, result["tests_total"], result["tests_passed"], strength,
                         errors=result["errors"], unsupported=unsupported, edge_gaps=gaps))

    # Steps 5 and 6: repair, then re-check
    result["repair"] = None
    if do_repair and defects(findings):
        verify_cases = required if native else required + probes
        baseline = baseline_from_run(run) if run else {}

        def evaluate(candidate):
            return verify_candidate(candidate, function or "", verify_cases, baseline,
                                    timeout=timeout, allow_local=allow_local,
                                    language=language)

        result["repair"] = repair(source, requirement, findings, function, evaluate,
                                  llm_fn=llm_fn, language=language)
        steps.append("Repair attempted and re-checked")
        if result["repair"]["accepted"] and not native:
            verification = result["repair"]["verification"]
            run_after = verification.get("run") or {}
            result["repair"]["coverage_after"] = summarize_coverage(run_after.get("coverage"))
    result["ok"] = True
    return result
