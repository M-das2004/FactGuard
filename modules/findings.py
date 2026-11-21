"""Common finding format shared by every module.

Every module returns findings as plain dictionaries so they can be shown in
Streamlit, saved as JSON and compared in experiments.
"""

# Prototype labels (section 7.6 of the blueprint).
SYNTAX = "Syntax issue"
NAMING = "Naming / identity issue"
API = "External API issue"
STRUCTURE = "Structure-access issue"
LOGIC = "Logical hallucination"
DATA = "Data-compliance issue"
RESOURCE = "Resource issue"

# Mapping of prototype labels to the terminology of the SDHD paper
# (Yang et al., IEEE TSE 2026). Syntax errors are a general category there.
PAPER_TERMS = {
    SYNTAX: "Syntactic error (general category)",
    NAMING: "Identity Hallucination (IH)",
    API: "External Source Hallucination (ESH)",
    STRUCTURE: "Structure Access Hallucination (SAH)",
    LOGIC: "Logical Deviation / Failure Hallucination (LDH / LFH)",
    DATA: "Data Compliance Hallucination (DCH)",
    RESOURCE: "Computational Boundary Hallucination (CBH)",
}

ERROR = "error"      # confirmed defect
WARNING = "warning"  # uncertain or unconfirmed, needs a human look
INFO = "info"        # style note, not counted as a defect


def make_finding(label, message, *, line=None, severity=ERROR,
                 evidence="", source="static", function=None):
    """Build one finding dictionary."""
    return {
        "label": label,
        "paper_term": PAPER_TERMS.get(label, ""),
        "severity": severity,
        "line": line,
        "function": function,
        "message": message,
        "evidence": evidence,
        "source": source,
    }


def defects(findings):
    """Findings that count as confirmed defects (severity == error)."""
    return [f for f in findings if f.get("severity") == ERROR]
