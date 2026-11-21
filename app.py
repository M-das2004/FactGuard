"""FactGuard AI - Streamlit demo app (Python, C, C++ and Java).

Run with:  python -m streamlit run app.py
"""
import json

import streamlit as st

from modules.execution_engine import (NATIVE, SandboxUnavailable,
                                      missing_tools)
from modules.findings import ERROR, WARNING
from modules.multilang import LANGUAGE_NAMES, detect_language
from modules.llm_providers import make_anthropic_llm
from modules.pipeline import analyze
from modules.report_generator import to_json, to_markdown

st.set_page_config(page_title="FactGuard AI", page_icon="🛡️", layout="wide")

SUM_CASES = '[{"args": [[1, 2, 3]], "expected": 6}, {"args": [[]], "expected": 0}, {"args": [[5]], "expected": 5}]'

EXAMPLES = {
    "Python - logic bug: startswith vs contains (demo)": {
        "language": "python",
        "requirement": "Find all words containing the letter 'a' from a list of words.",
        "code": 'def find_words(words):\n    return [w for w in words if w.startswith("a")]\n',
        "cases": ""},
    "Python - undefined variable": {
        "language": "python",
        "requirement": "Return the sum of a list of numbers.",
        "code": "def total(xs):\n    s = 0\n    for x in xs:\n        s += x\n    return ss\n",
        "cases": ""},
    "Python - fake API: math.sqroot": {
        "language": "python",
        "requirement": "Return the square root of a number.",
        "code": "import math\n\ndef root(n):\n    return math.sqroot(n)\n",
        "cases": '[{"input": 16, "expected": 4.0}, {"input": 2, "expected": 1.4142135623730951}]'},
    "Python - correct code": {
        "language": "python",
        "requirement": "Return the sum of a list of numbers.",
        "code": "def total(xs):\n    return sum(xs)\n", "cases": SUM_CASES},
    "Python - no tests, no template (cannot verify)": {
        "language": "python",
        "requirement": "Return the number of words in a sentence.",
        "code": "def count_words(s):\n    return len(s.split(' '))\n", "cases": ""},
    "C - off-by-one loop": {
        "language": "c",
        "requirement": "Return the sum of a list of numbers.",
        "code": "int total(const int *xs, int n) {\n    int s = 0;\n    for (int i = 1; i < n; i++) s += xs[i];\n    return s;\n}\n",
        "cases": SUM_CASES},
    "C - hallucinated function: strlenn": {
        "language": "c",
        "requirement": "Return the length of a string.",
        "code": "#include <string.h>\n\nint len(const char *s) {\n    return (int) strlenn(s);\n}\n",
        "cases": '[{"args": ["abc"], "expected": 3}]'},
    "C - buffer overflow (found at run time)": {
        "language": "c",
        "requirement": "Return the sum of a list of numbers.",
        "code": "int total(const int *xs, int n) {\n    int s = 0;\n    for (int i = 0; i <= n; i++) s += xs[i];\n    return s;\n}\n",
        "cases": SUM_CASES},
    "C++ - undeclared variable": {
        "language": "cpp",
        "requirement": "Return the sum of a list of numbers.",
        "code": "#include <vector>\n\nint total(std::vector<int> xs) {\n    int s = 0;\n    for (int x : xs) s += x;\n    return ss;\n}\n",
        "cases": SUM_CASES},
    "C++ - logic bug: first letter only": {
        "language": "cpp",
        "requirement": "Find all words containing the letter 'a' from a list of words.",
        "code": "#include <string>\n#include <vector>\n\nstd::vector<std::string> findWords(std::vector<std::string> words) {\n    std::vector<std::string> out;\n    for (auto &w : words)\n        if (!w.empty() && w[0] == 'a') out.push_back(w);\n    return out;\n}\n",
        "cases": ""},
    "Java - hallucinated method: Math.sqroot": {
        "language": "java",
        "requirement": "Return the square root of a number.",
        "code": "public class Solution {\n    public static double root(double n) {\n        return Math.sqroot(n);\n    }\n}\n",
        "cases": '[{"args": [16], "expected": 4.0}, {"args": [2], "expected": 1.4142135623730951}]'},
    "Java - logic bug: startsWith vs contains": {
        "language": "java",
        "requirement": "Find all words containing the letter 'a' from a list of words.",
        "code": 'import java.util.*;\n\npublic class Solution {\n    public static List<String> findWords(List<String> words) {\n        List<String> out = new ArrayList<>();\n        for (String w : words) if (w.startsWith("a")) out.add(w);\n        return out;\n    }\n}\n',
        "cases": ""},
    "Java - correct code": {
        "language": "java",
        "requirement": "Return the sum of a list of numbers.",
        "code": "public class Solution {\n    public static int total(int[] xs) {\n        int s = 0;\n        for (int x : xs) s += x;\n        return s;\n    }\n}\n",
        "cases": SUM_CASES},
}
LANG_CHOICES = {"Auto-detect": "auto", "Python": "python", "C": "c", "C++": "cpp", "Java": "java"}
HIGHLIGHT = {"python": "python", "c": "c", "cpp": "cpp", "java": "java"}


def load_example():
    example = EXAMPLES[st.session_state.example]
    st.session_state.requirement = example["requirement"]
    st.session_state.code = example["code"]
    st.session_state.cases = example["cases"]
    st.session_state.language_choice = next(
        name for name, key in LANG_CHOICES.items() if key == example["language"])


def show_table(rows):
    """Plain Markdown table. Avoids st.dataframe, which needs pyarrow (its DLL is
    blocked by some Windows Application Control policies)."""
    if not rows:
        st.write("None.")
        return
    columns = list(rows[0].keys())

    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(cell(row.get(c, "")) for c in columns) + " |" for row in rows]
    st.markdown("\n".join(lines))


for key, value in (("requirement", ""), ("code", ""), ("cases", ""),
                   ("language_choice", "Auto-detect")):
    st.session_state.setdefault(key, value)

st.title("🛡️ FactGuard AI")
st.caption("Finds and fixes hidden mistakes in AI-written Python, C, C++ and Java code. "
           "Compiler/static checks + requirement tests + test-strength check + verified repair.")

with st.sidebar:
    st.header("Settings")
    # st.warning("Code runs locally on this computer and is **not isolated**. "
    #            "Use trusted sample programs only.")
    local_tools = {name: not missing_tools(key) for name, key in
                   (("C (gcc)", "c"), ("C++ (g++)", "cpp"), ("Java (javac)", "java"))}
    st.caption("Compilers on this computer: " + ", ".join(
        f"{name} {'✅' if found else '❌'}" for name, found in local_tools.items()))
    allow_local = st.checkbox("Allow local (non-isolated) execution", value=False,
                              help="Only for trusted examples while developing. For C, C++ "
                                   "and Java the code is compiled and run on this computer.")
    timeout = st.slider("Timeout per test (seconds)", 1, 10, 3)
    use_templates = st.checkbox("Generate requirement-based tests", True)
    use_strength = st.checkbox("Measure test strength (mutation score)", True,
                               help="Checks whether the tests would notice small deliberate "
                                    "changes to this code. Slower, but it stops weak tests "
                                    "from looking like proof.")
    use_cov = st.checkbox("Coverage-guided extra tests (experimental)", False,
                          help="Our evaluation found no measurable benefit, so this is off "
                               "by default.")
    do_repair = st.checkbox("Try to repair defects", True)
    api_key = st.text_input("Optional: API key for LLM repair", type="password",
                            help="Used only when built-in repair cannot fix the code. Your code "
                                 "and requirement are sent to the provider. The key is not saved. "
                                 "Any LLM answer is verified before it is shown.")
    st.divider()
    st.selectbox("Load an example", list(EXAMPLES), key="example")
    st.button("Load example", on_click=load_example)

left, right = st.columns(2)
with left:
    st.selectbox("Language", list(LANG_CHOICES), key="language_choice")
    requirement = st.text_area("Requirement (what the code should do)", key="requirement",
                               height=100)
    code = st.text_area("Code to check", key="code", height=280)
with right:
    cases = st.text_area(
        "Optional test cases (JSON)", key="cases", height=140,
        help='Example: [{"input": [1,2,3], "expected": 6}]  or  '
             '{"args": [[1, 2, 3]], "expected": 6}. In C an array argument also fills the '
             'length parameter that follows it.')
    function_name = st.text_input("Function / method name (leave empty to detect)")
    st.caption("Without test cases, FactGuard AI uses a requirement template when it "
               "recognises the task (sum, even numbers, palindrome, 'contains a letter', ...). "
               "If neither exists it says **could not verify** instead of 'no issue'. "
               "Supported test types in C/C++/Java: int, long, double, bool, string, int "
               "arrays and string lists.")

if st.button("Analyze code", type="primary"):
    language = LANG_CHOICES[st.session_state.language_choice]
    if language == "auto":
        language = detect_language(code)
        st.info(f"Language detected: {LANGUAGE_NAMES[language]}")
    with st.spinner("Compiling, running tests and checking test strength..."):
        try:
            result = analyze(requirement, code, language=language,
                             function_name=function_name or None, cases=cases or None,
                             timeout=timeout, allow_local=allow_local,
                             use_templates=use_templates, use_coverage_guided=use_cov,
                             do_repair=do_repair, measure_strength=use_strength,
                             llm_fn=make_anthropic_llm(api_key or None) if api_key else None)
            st.session_state.result = result
            st.session_state.snapshot = (requirement, code)
        except SandboxUnavailable as exc:
            st.session_state.result = None
            st.error(str(exc))

result = st.session_state.get("result")
if result:
    req, src = st.session_state.get("snapshot", ("", ""))
    if not result["ok"]:
        for message in result["errors"]:
            st.error(message)
    else:
        lang = result["language"]
        for message in result["warnings"]:
            st.warning(message)
        for message in result["errors"]:
            st.error(message)

        status = result["status"]
        {"defects": st.error, "no_defect_found": st.success}.get(status, st.warning)(
            result["verdict"])
        st.caption(f"Language: {LANGUAGE_NAMES[lang]}  ·  Test oracle: {result['oracle']}  ·  "
                   "Pipeline: " + " → ".join(result["steps"]))

        types = sorted({f["label"] for f in result["findings"] if f["severity"] == ERROR})
        fix = result["repair"]
        if types:
            st.subheader("Hallucination type(s): " + ", ".join(types))
        if fix and fix["accepted"]:
            st.subheader("Corrected code")
            st.caption(f"{fix['description']}  Verified: it passes all {len(fix['verification']['checks'])} "
                       "re-checks (see the Repair tab).")
            st.code(fix["source"], language=HIGHLIGHT[lang])
            ext = {"python": "py", "c": "c", "cpp": "cpp", "java": "java"}[lang]
            st.download_button("Download corrected code", fix["source"], f"corrected.{ext}")
        elif fix:
            st.warning("No verified correction could be produced for this code. "
                       + fix.get("why_not", "")
                       + " Add test cases, or paste an Anthropic API key in the sidebar to let an "
                         "LLM propose a fix that FactGuard AI then verifies.")

        a, b, c, d = st.columns(4)
        a.metric("Tests passed", f"{result['tests_passed']}/{result['tests_total']}")
        strength = result.get("strength")
        b.metric("Test strength",
                 f"{round(100 * strength['score'])}%" if strength and strength.get("score")
                 is not None else "n/a",
                 help="Share of small deliberate changes to the code that the tests notice.")
        cov = result["coverage"]
        c.metric("Branches executed",
                 f"{cov['branch_percent']}%" if cov.get("available") else "n/a",
                 help="Python only. It shows what ran, not how good the tests are.")
        d.metric("Findings", len([f for f in result["findings"]
                                  if f["severity"] in (ERROR, WARNING)]))

        tab1, tab2, tab3, tab4 = st.tabs(["Findings", "Tests", "Repair", "Report"])
        with tab1:
            shown = [f for f in result["findings"] if f["severity"] != "info"]
            if not shown:
                st.write("No findings.")
            for f in shown:
                icon = "🔴" if f["severity"] == ERROR else "🟡"
                where = f"line {f['line']}" if f["line"] else "whole program"
                with st.expander(f"{icon} {f['label']} - {where}", expanded=f["severity"] == ERROR):
                    st.write(f["message"])
                    if f.get("explanation"):
                        st.info("Why: " + f["explanation"])
                    for note in f.get("notes", []):
                        st.caption(note)
                    st.caption(f"Evidence: {f['evidence']}  ·  Paper term: {f['paper_term']}")
        with tab2:
            if result["template"]:
                st.write(f"Requirement template used: **{result['template']}**")
            for note in result["assumptions"]:
                st.caption("Assumption: " + note)
            for gap in result.get("edge_gaps", []):
                st.warning("Edge-case gap: " + gap)
            if strength and strength.get("survivors"):
                with st.expander(f"Small changes the tests did NOT notice "
                                 f"({len(strength['survivors'])})"):
                    for description in strength["survivors"]:
                        st.write("• " + description)
            if result["run"] and result["run"].get("ok"):
                st.caption("Executed in: " + result["run"]["sandbox"])
                rows = [{"test": c_["id"], "kind": c_["kind"], "status": c_["status"],
                         "input": json.dumps(c_["args"]),
                         "expected": "-" if c_.get("probe") else json.dumps(c_["expected"]),
                         "actual": json.dumps(c_["actual"]) if c_["actual"] is not None else
                         (c_["exception"] or {}).get("type", "")}
                        for c_ in result["run"]["cases"]]
                show_table(rows)
            if cov.get("available"):
                st.write(f"Executed {cov['covered_branches']} of {cov['num_branches']} branches.")
                for note in cov["missing_notes"]:
                    st.write("• " + note["message"])
        with tab3:
            repair = result["repair"]
            if repair is None:
                st.write("No defects, so no repair was needed (or repair is switched off).")
            elif repair["accepted"]:
                st.success(f"Repair accepted ({repair['strategy']}): {repair['description']}")
                st.code(repair["diff"], language="diff")
                st.code(repair["source"], language=HIGHLIGHT[lang])
                st.write("**Re-checks on the repaired code**")
                for check in repair["verification"]["checks"]:
                    st.write(("✅ " if check["passed"] else "❌ ") + check["name"]
                             + (f" - {check['detail']}" if check["detail"] else ""))
                st.caption("Your original code was not changed.")
            else:
                st.warning("No candidate repair passed every check, so none is offered. "
                           + repair.get("why_not", ""))
            if repair and repair["tried"]:
                with st.expander(f"Candidates tried ({len(repair['tried'])})"):
                    show_table(repair["tried"])
        with tab4:
            markdown = to_markdown(result, req, src)
            st.markdown(markdown)
            d1, d2 = st.columns(2)
            d1.download_button("Download report (Markdown)", markdown, "FactGuard_report.md")
            d2.download_button("Download report (JSON)", to_json(result), "FactGuard_report.json")
