"""Assurance: how much can we trust a "no defect" answer?

The model review (F5) showed that "nothing found" was reported the same way
whether the code had been well tested or never executed at all. This module
separates the outcomes:

  defects          at least one confirmed defect
  incomplete       a tool failed, so no conclusion can be drawn
  review           no confirmed defect, but some results need a human look
  unverified       NO tests ran (no test cases and no matching requirement
                   template): static checks only, nothing known about behaviour
  weak_evidence    tests ran and passed, but they are weak: they miss many
                   small mutations of this very code, or no test tries the usual
                   edge inputs (zero/negative numbers, empty lists or strings)
  no_defect_found  tests ran and passed, and they are reasonably sharp

"no_defect_found" never means "correct".
"""
from .findings import ERROR, WARNING

STATUS_TITLES = {
    "defects": "Defects detected",
    "incomplete": "Analysis incomplete",
    "review": "Needs review",
    "unverified": "Could not verify",
    "weak_evidence": "Weak evidence",
    "no_defect_found": "No defect found",
}

WEAK_BELOW = 0.5  # mutation score under which tests are called weak


def assess(findings, tests_total, tests_passed, strength=None, *, errors=(),
           unsupported=None, edge_gaps=()):
    """Return {"status", "verdict"} for one analysis."""
    confirmed = [f for f in findings if f["severity"] == ERROR]
    warnings = [f for f in findings if f["severity"] == WARNING]

    if confirmed:
        labels = sorted({f["label"] for f in confirmed})
        return {"status": "defects",
                "verdict": f"Defects detected: {', '.join(labels)}."}
    if errors:
        return {"status": "incomplete",
                "verdict": "Analysis incomplete: " + " ".join(errors)
                + " No conclusion can be drawn about this code."}
    if warnings:
        return {"status": "review",
                "verdict": "No confirmed defect, but some results need a human review."}
    if tests_total == 0:
        why = unsupported or ("no test cases were given and the requirement matches no "
                              "built-in template")
        return {"status": "unverified",
                "verdict": f"Could not verify: no tests ran ({why}). The static checks "
                           "found no defect, but that says nothing about behaviour. "
                           "Add test cases to get a real answer."}
    if edge_gaps:
        return {"status": "weak_evidence",
                "verdict": "No defect found, but the tests skip common edge cases ("
                           + "; ".join(edge_gaps[:2]) + "). Passing tests that never "
                           "try the boundaries do not show the code is right; add "
                           "edge-case tests."}
    if strength and strength.get("total"):
        score = strength["score"]
        detail = (f"the tests caught {strength['killed']} of {strength['total']} "
                  f"small mutations of this code ({round(100 * score)}%)")
        if score < WEAK_BELOW:
            return {"status": "weak_evidence",
                    "verdict": f"No defect found, but the evidence is weak: {detail}. "
                               "Passing tests this weak do not show the code is right; "
                               "add edge-case tests."}
        return {"status": "no_defect_found",
                "verdict": f"No defect found: {tests_passed}/{tests_total} tests passed; "
                           f"{detail}. This is not a proof of correctness."}
    return {"status": "no_defect_found",
            "verdict": f"No defect found: {tests_passed}/{tests_total} tests passed "
                       "(test strength could not be measured for this code). "
                       "This is not a proof of correctness."}
