"""Coverage Analyzer: turn the runner's raw Coverage.py data into a summary."""


def summarize_coverage(raw):
    """Return branch/statement percentages and the list of missing branches.

    `raw` is the "coverage" entry of a runner result (or None).
    """
    if not raw:
        return {"available": False, "branch_percent": None, "statement_percent": None,
                "num_branches": 0, "covered_branches": 0, "missing_branches": [],
                "missing_lines": []}
    branches, covered = raw.get("num_branches", 0), raw.get("covered_branches", 0)
    statements, lines = raw.get("num_statements", 0), raw.get("covered_lines", 0)
    return {
        "available": True,
        # With no branches at all (straight-line code) nothing is left uncovered.
        "branch_percent": round(100.0 * covered / branches, 1) if branches else 100.0,
        "statement_percent": round(100.0 * lines / statements, 1) if statements else 100.0,
        "num_branches": branches,
        "covered_branches": covered,
        "missing_branches": [list(pair) for pair in raw.get("missing_branches", [])],
        "missing_lines": list(raw.get("missing_lines", [])),
    }


def describe_missing_branches(missing_branches, source):
    """Plain-language lines such as 'line 2: the path to line 4 was never taken'."""
    lines = source.splitlines()
    notes = []
    for origin, target in missing_branches:
        text = lines[origin - 1].strip() if 0 < origin <= len(lines) else ""
        goal = "the end of the function" if target < 0 else f"line {target}"
        notes.append({"line": origin, "target": target, "code": text,
                      "message": f"line {origin} ({text}): the path to {goal} was never taken"})
    return notes
