"""Test strength: a mutation score instead of coverage (review finding F4).

Branch coverage was 100% on tasks whose bugs survived, so it cannot say whether
the tests are any good. The mutation score asks a sharper question: if we make a
small, plausible change to this very code (flip a comparison, shift a constant,
swap an operator), do the tests notice? A test suite that notices few of them
would probably also miss a real bug.

Limits: mutants that behave exactly like the original ("equivalent mutants")
count as survivors, which lowers the score a little. At most `limit` mutants
are run, spread evenly over the code.
"""
from .execution_engine import run_in_sandbox
from .repair_engine import iter_mutants


def _spread(items, limit):
    if len(items) <= limit:
        return items
    step = len(items) / limit
    return [items[int(i * step)] for i in range(limit)]


def _mutants(source, language, function, limit):
    if language == "python":
        return _spread(list(iter_mutants(source, function, limit=200)), limit)
    from .multilang import iter_text_mutants
    return _spread(list(iter_text_mutants(source, language, limit=200)), limit)


def measure(source, language, function, required_cases, *, timeout=5,
            allow_local=False, limit=12):
    """Mutation score of `required_cases` against `source`.

    Returns {"total", "killed", "score", "survivors"}. `total` counts only mutants
    that could be built and run (a mutant that does not compile is skipped).
    """
    result = {"total": 0, "killed": 0, "score": None, "survivors": []}
    if not required_cases:
        return result
    for description, mutant in _mutants(source, language, function, limit):
        run = run_in_sandbox(mutant, function, required_cases, timeout=timeout,
                             allow_local=allow_local, language=language, stop_on_fail=True)
        if not run.get("ok"):
            continue
        if language != "python" and (not run.get("compile_ok", True) or run.get("unsupported")):
            continue  # an invalid mutant tells us nothing about the tests
        result["total"] += 1
        noticed = bool(run.get("import_error")) or any(
            case["status"] != "pass" for case in run.get("cases", []))
        if noticed:
            result["killed"] += 1
        else:
            result["survivors"].append(description)
    if result["total"]:
        result["score"] = round(result["killed"] / result["total"], 3)
    return result


def edge_case_gaps(required_cases):
    """Edge inputs that NO test uses, per argument position.

    A suite whose tests never try zero/negative numbers or empty lists and strings
    cannot notice bugs that live at those boundaries, whatever its mutation score
    (a missing `n < 2` guard is invisible to operator mutations). This is a plain
    heuristic, not a proof: it only reports boundaries that are absent.
    """
    gaps, width = [], max((len(c.get("args", [])) for c in required_cases), default=0)
    for position in range(width):
        values = [c["args"][position] for c in required_cases
                  if position < len(c.get("args", []))]
        if not values:
            continue
        numbers = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
        containers = [v for v in values if isinstance(v, (list, str))]
        if numbers and len(numbers) == len(values) and not any(v <= 0 for v in numbers):
            gaps.append(f"argument {position + 1}: no test uses zero or a negative number")
        if containers and len(containers) == len(values) and not any(len(v) == 0 for v in containers):
            gaps.append(f"argument {position + 1}: no test uses an empty list or string")
    return gaps
