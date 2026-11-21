"""Ground-truth checking: run a task's code against its HIDDEN tests.

Used by tests/test_dataset.py (are the labels right?) and by run_experiment.py
(is an accepted repair really right?). No system under evaluation ever calls this.
"""
import ast

from modules.execution_engine import run_in_sandbox


def hidden_cases(task):
    return [dict(c, id=f"h{i}") for i, c in enumerate(task["hidden"])]


def hidden_outcome(task, allow_local=True, source=None, timeout=3):
    """One of: all-pass, fails, side-effect, syntax, compile-error, import-error,
    unsupported, sandbox-error."""
    source = task["code"] if source is None else source
    language = task["language"]
    if language == "python":
        try:
            ast.parse(source)
        except SyntaxError:
            return "syntax"
    run = run_in_sandbox(source, task["function"], hidden_cases(task), timeout=timeout,
                         allow_local=allow_local, language=language)
    if not run.get("ok"):
        return "sandbox-error"
    if run.get("unsupported"):
        return "unsupported"
    if language != "python" and run.get("compile_ok") is False:
        return "compile-error"
    if run.get("import_error"):
        return "import-error"
    cases = run["cases"]
    if not cases or any(c["status"] != "pass" for c in cases):
        return "fails"
    if task.get("hidden_property") == "args_unchanged" and any(
            c.get("mutated_args") for c in cases):
        return "side-effect"
    return "all-pass"


def is_correct_outcome(outcome):
    return outcome == "all-pass"
