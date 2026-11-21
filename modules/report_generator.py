"""Report Generator: plain-text/Markdown and JSON reports."""
import json

from .findings import ERROR, INFO, WARNING


def to_json(result):
    """JSON report (tree objects and other non-data values are dropped)."""
    keep = ("ok", "language", "status", "function", "verdict", "oracle", "findings", "coverage",
            "tests_total", "tests_passed", "strength", "edge_gaps", "template", "assumptions",
            "warnings", "errors", "steps")
    data = {key: result.get(key) for key in keep}
    repair = result.get("repair")
    if repair:
        data["repair"] = {k: repair.get(k) for k in
                          ("accepted", "strategy", "description", "source", "diff", "tried")}
        if repair.get("verification"):
            data["repair"]["checks"] = repair["verification"]["checks"]
    return json.dumps(data, indent=2, default=str)


def to_markdown(result, requirement="", source=""):
    """Readable Markdown report for the screen or a download."""
    if not result.get("ok"):
        return "# FactGuard AI report\n\nNo analysis: " + " ".join(result.get("errors", []))
    lines = ["# FactGuard AI report", ""]
    if requirement:
        lines += ["**Requirement:** " + requirement, ""]
    lines += [f"**Language:** {result.get('language', 'python')}  ·  "
              f"**Test oracle:** {result.get('oracle', '-')}", ""]
    lines += [f"**Verdict:** {result['verdict']}", ""]
    lines += [f"**Tests:** {result['tests_passed']}/{result['tests_total']} passed", ""]
    strength = result.get("strength")
    if strength and strength.get("score") is not None:
        lines += [f"**Test strength:** the tests noticed {strength['killed']} of "
                  f"{strength['total']} small deliberate changes ({round(100 * strength['score'])}%)", ""]
    for gap in result.get("edge_gaps") or []:
        lines.append(f"- edge-case gap: {gap}")
    cov = result["coverage"]
    if cov.get("available"):
        lines.append(f"**Branch coverage:** {cov['branch_percent']}% "
                     f"({cov['covered_branches']}/{cov['num_branches']} branches)")
        if cov.get("probes_added"):
            lines.append(f"  (raised from {cov['before_percent']}% by "
                         f"{cov['probes_added']} coverage-guided probe inputs)")
        for note in cov.get("missing_notes", []):
            lines.append(f"  - missed: {note['message']}")
        lines.append("")
    if result.get("assumptions"):
        lines += ["**Assumptions:**"] + [f"- {a}" for a in result["assumptions"]] + [""]
    lines.append("## Findings")
    shown = [f for f in result["findings"] if f["severity"] != INFO]
    if not shown:
        lines.append("None.")
    for f in shown:
        mark = {"error": "DEFECT", "warning": "REVIEW"}[f["severity"]]
        where = f"line {f['line']}" if f["line"] else "whole program"
        lines += [f"- **[{mark}] {f['label']}** ({where}) - {f['message']}",
                  f"  - paper term: {f['paper_term']}", f"  - evidence: {f['evidence']}"]
        if f.get("explanation"):
            lines.append(f"  - why: {f['explanation']}")
    lines.append("")
    repair = result.get("repair")
    if repair is not None:
        lines.append("## Repair")
        if repair["accepted"]:
            lines += [f"Accepted candidate ({repair['strategy']}): {repair['description']}",
                      "", "Corrected code:", "", "```", repair["source"].rstrip(), "```", "",
                      "Changes:", "", "```diff", repair["diff"].rstrip(), "```", "", "Re-checks:"]
            lines += [f"- {'PASS' if c['passed'] else 'FAIL'}: {c['name']}"
                      for c in repair["verification"]["checks"]]
        else:
            lines.append("No candidate repair passed every check, so none is offered. "
                         + repair.get("why_not", "") + " The original code is unchanged.")
        lines.append("")
    lines.append("*Passing every check does not prove the code is correct; it only "
                 "means no defect was found by these checks.*")
    return "\n".join(lines)
