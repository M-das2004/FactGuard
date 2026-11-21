"""Run the evaluation and write results/ (JSON, CSV and a Markdown summary).

    python run_experiment.py                 # all tasks (a few minutes per language)
    python run_experiment.py --languages python
    python run_experiment.py --limit 20 --fresh

What is compared (same tasks, same requirements, same labels, no LLM anywhere):
  A  checks only          compiler / static / API checks, no tests at all
  B  + given tests        A plus the tests the user supplied (no templates)
  C  FactGuard full       B plus requirement templates, template-free property
                          check, test-strength check and verified repair
  C- no templates         C without requirement templates (ablation)
  C+ probes               C with coverage-guided probes (Python ablation; the
                          review found they add nothing, so they are off in C)

Two conditions per task (review F3: tests and templates were confounded):
  tests      the first 2 hidden cases are "given" (mechanical, bug-blind rule)
  no_tests   nothing is given

Outcome of one analysis:  defects | no_defect_found | uncertain (unverified,
weak_evidence, review or incomplete).  On faulty code, no_defect_found is FALSE
ASSURANCE - the failure the review found in T30.  On correct code, defects is a
FALSE ALARM and uncertain is an abstention.

Confidence intervals resample whole problem FAMILIES (a faulty task and its
correct twin are not independent), so they are wider than naive ones.
"""
import argparse
import csv
import json
import math
import os
import random
import shutil
import time
from concurrent.futures import ThreadPoolExecutor

from dataset.all_tasks import ALL_TASKS, GIVEN_K
from dataset.validate import hidden_outcome
from modules.pipeline import analyze
from modules.test_generator import generate_from_requirement, hidden_overlap

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
CACHE = os.path.join(OUT, "cache")
VISIBLE = ("requirement", "code", "function", "language", "given")  # what a system may see
UNCERTAIN = {"unverified", "weak_evidence", "review", "incomplete"}

SYSTEMS = {
    "A_checks_only": dict(use_templates=False, use_coverage_guided=False, do_repair=False,
                          measure_strength=False, given=False),
    "B_given_tests": dict(use_templates=False, use_coverage_guided=False, do_repair=False,
                          measure_strength=False, given=True),
    "C_full": dict(use_templates=True, use_coverage_guided=False, do_repair=True,
                   measure_strength=True, given=True),
    "C_no_templates": dict(use_templates=False, use_coverage_guided=False, do_repair=True,
                           measure_strength=True, given=True),
    "C_plus_probes": dict(use_templates=True, use_coverage_guided=True, do_repair=True,
                          measure_strength=True, given=True, python_only=True),
}


# ---------------------------------------------------------------- one analysis
def outcome_of(status):
    if status == "defects":
        return "defects"
    if status == "no_defect_found":
        return "no_defect_found"
    return "uncertain"


def run_one(task, system, condition):
    """Run one system on one task. Only VISIBLE fields are read - never `hidden`."""
    visible = {k: task[k] for k in VISIBLE}
    cfg = SYSTEMS[system]
    given = visible["given"] if (cfg["given"] and condition == "tests") else None
    result = analyze(visible["requirement"], visible["code"], language=visible["language"],
                     function_name=visible["function"], cases=given or None, timeout=2,
                     allow_local=True, use_templates=cfg["use_templates"],
                     use_coverage_guided=cfg["use_coverage_guided"], do_repair=cfg["do_repair"],
                     measure_strength=cfg["measure_strength"])
    status = result.get("status") or "incomplete"
    found = [f for f in result.get("findings", []) if f["severity"] == "error"]
    strength = result.get("strength") or {}
    record = {"status": status, "outcome": outcome_of(status),
              "labels": sorted({f["label"] for f in found}),
              "strength": strength.get("score"), "repair": None}
    repair = result.get("repair")
    if repair:
        record["repair"] = {"accepted": repair["accepted"], "strategy": repair["strategy"],
                            "why_not": "" if repair["accepted"] else repair.get("why_not", ""),
                            "source": repair["source"]}
    return record


def run_task(task, languages):
    path = os.path.join(CACHE, f"{task['id']}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    row = {"id": task["id"], "language": task["language"], "family": task["family"],
           "label": task["label"], "fault": task["fault"], "origin": task["origin"],
           "in_template": generate_from_requirement(task["requirement"]) is not None,
           "runs": {}}
    for system, cfg in SYSTEMS.items():
        if cfg.get("python_only") and task["language"] != "python":
            continue
        for condition in ("tests", "no_tests"):
            if system == "A_checks_only" and condition == "no_tests":
                continue  # A never sees tests, so one run serves both conditions
            if system == "B_given_tests" and condition == "no_tests":
                continue  # B without tests is identical to A
            if system == "C_plus_probes" and condition == "no_tests":
                continue
            record = run_one(task, system, condition)
            if record["repair"] and record["repair"]["accepted"]:
                verdict = hidden_outcome(task, source=record["repair"]["source"])
                record["repair"]["hidden_outcome"] = verdict
                record["repair"]["hidden_pass"] = verdict == "all-pass"
            if record["repair"]:
                record["repair"].pop("source", None)
            row["runs"][f"{system}|{condition}"] = record
    row["runs"]["B_given_tests|no_tests"] = row["runs"]["A_checks_only|tests"]
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(row, handle)
    return row


# -------------------------------------------------------------------- statistics
def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def cluster_ci(rows, stat, iterations=1500, seed=11):
    """Percentile interval of `stat(rows)` when whole families are resampled."""
    groups = {}
    for row in rows:
        groups.setdefault(row["family"], []).append(row)
    families = list(groups)
    if len(families) < 2:
        return (None, None)
    rng = random.Random(seed)
    values = []
    for _ in range(iterations):
        sample = []
        for _ in families:
            sample += groups[rng.choice(families)]
        value = stat(sample)
        if value is not None:
            values.append(value)
    if not values:
        return (None, None)
    values.sort()
    return (values[int(0.025 * len(values))], values[int(0.975 * len(values)) - 1])


def rate(rows, label, predicate):
    pool = [r for r in rows if r["label"] == label]
    return sum(1 for r in pool if predicate(r)) / len(pool) if pool else None


def metrics(rows, key):
    """Everything we report for one (system, condition) on a set of task rows."""
    rows = [r for r in rows if key in r["runs"]]
    out = lambda r: r["runs"][key]["outcome"]  # noqa: E731
    faulty = [r for r in rows if r["label"] == "faulty"]
    correct = [r for r in rows if r["label"] == "correct"]
    tp = sum(1 for r in faulty if out(r) == "defects")
    fp = sum(1 for r in correct if out(r) == "defects")
    recall_stat = lambda s: rate(s, "faulty", lambda r: out(r) == "defects")  # noqa: E731
    fp_stat = lambda s: rate(s, "correct", lambda r: out(r) == "defects")  # noqa: E731
    fa_stat = lambda s: rate(s, "faulty", lambda r: out(r) == "no_defect_found")  # noqa: E731
    return {
        "n_faulty": len(faulty), "n_correct": len(correct),
        "recall": recall_stat(rows), "recall_wilson": wilson(tp, len(faulty)),
        "recall_cluster_ci": cluster_ci(rows, recall_stat),
        "precision": tp / (tp + fp) if tp + fp else None,
        "false_alarm_rate": fp_stat(rows), "false_alarm_ci": cluster_ci(rows, fp_stat),
        "false_assurance_rate": fa_stat(rows), "false_assurance_ci": cluster_ci(rows, fa_stat),
        "faulty_uncertain": rate(rows, "faulty", lambda r: out(r) == "uncertain"),
        "correct_uncertain": rate(rows, "correct", lambda r: out(r) == "uncertain"),
        "correct_verified_clean": rate(rows, "correct", lambda r: out(r) == "no_defect_found"),
        "families": len({r["family"] for r in rows}),
    }


def paired_difference(rows, key_a, key_b, iterations=1500, seed=5):
    """recall(key_a) - recall(key_b) on the same faulty tasks, family-clustered."""
    faulty = [r for r in rows if r["label"] == "faulty" and key_a in r["runs"]
              and key_b in r["runs"]]
    if not faulty:
        return None

    def stat(sample):
        if not sample:
            return None
        a = sum(1 for r in sample if r["runs"][key_a]["outcome"] == "defects")
        b = sum(1 for r in sample if r["runs"][key_b]["outcome"] == "defects")
        return (a - b) / len(sample)

    low, high = cluster_ci(faulty, stat, iterations, seed)
    return {"difference": stat(faulty), "ci": (low, high), "n_faulty": len(faulty)}


# ------------------------------------------------------------------ audit & repair
def audit(tasks, rows):
    """Review F6/F2: leakage and template/hidden-test overlap."""
    leak_free = all(set(VISIBLE).isdisjoint({"hidden", "label", "fault", "hidden_property"})
                    for _ in [0])
    overlaps = []
    for task in tasks:
        template = generate_from_requirement(task["requirement"])
        if template and task["language"] == "python":
            overlaps.append(hidden_overlap(template["cases"], task["hidden"]))
    matched = sum(1 for t in tasks if generate_from_requirement(t["requirement"]))
    return {
        "systems_see_only": list(VISIBLE),
        "hidden_or_label_visible_to_systems": not leak_free,
        "template_match_rate": matched / len(tasks),
        "template_tasks_python": len(overlaps),
        "mean_template_case_overlap_with_hidden": (sum(overlaps) / len(overlaps)
                                                   if overlaps else None),
    }


def repair_report(rows, key="C_full|tests"):
    detected = [r for r in rows if r["label"] == "faulty" and key in r["runs"]
                and r["runs"][key]["outcome"] == "defects"]
    attempted = [r for r in detected if r["runs"][key]["repair"]]
    accepted = [r for r in attempted if r["runs"][key]["repair"]["accepted"]]
    right = [r for r in accepted if r["runs"][key]["repair"].get("hidden_pass")]
    strategies = {}
    for r in accepted:
        name = r["runs"][key]["repair"]["strategy"] or "?"
        kind = "rule" if name.startswith("rule") else ("mutation" if "mutation" in name else "other")
        entry = strategies.setdefault(kind, {"accepted": 0, "right": 0})
        entry["accepted"] += 1
        entry["right"] += bool(r["runs"][key]["repair"].get("hidden_pass"))
    unrepaired = {}
    for r in attempted:
        repair = r["runs"][key]["repair"]
        if not repair["accepted"]:
            why = repair["why_not"]
            reason = ("no candidate could be generated" if why.startswith("no candidate")
                      else "candidates were tried but all failed a check")
            unrepaired.setdefault(reason, []).append(r["id"])
    wrong_ids = [r["id"] for r in accepted if not r["runs"][key]["repair"].get("hidden_pass")]
    bad_on_correct = [r["id"] for r in rows if r["label"] == "correct" and key in r["runs"]
                      and r["runs"][key]["repair"] and r["runs"][key]["repair"]["accepted"]]
    return {"detected_faulty": len(detected), "accepted": len(accepted),
            "accepted_and_passes_hidden": len(right), "accepted_but_wrong": wrong_ids,
            "success_rate_of_detected": len(right) / len(detected) if detected else None,
            "by_strategy": strategies, "not_repaired": unrepaired,
            "repairs_accepted_on_correct_code": bad_on_correct}


# --------------------------------------------------------------------- reporting
def pct(value):
    return "n/a" if value is None else f"{100 * value:.0f}%"


def ci_text(value, ci):
    if value is None:
        return "n/a"
    if not ci or ci[0] is None:
        return pct(value)
    return f"{pct(value)} ({pct(ci[0])}-{pct(ci[1])})"


def table(title, rows, columns):
    """columns: list of (heading, key). One line per system, for one subset."""
    lines = [f"### {title}", "",
             "| System | Faulty caught | False assurance (said clean) | Faulty uncertain | "
             "False alarms on correct | Correct verified clean | n faulty / correct |",
             "|---|---|---|---|---|---|---|"]
    for heading, key in columns:
        m = metrics(rows, key)
        if not m["n_faulty"] and not m["n_correct"]:
            continue
        lines.append(f"| {heading} | {ci_text(m['recall'], m['recall_cluster_ci'])} | "
                     f"{ci_text(m['false_assurance_rate'], m['false_assurance_ci'])} | "
                     f"{pct(m['faulty_uncertain'])} | "
                     f"{ci_text(m['false_alarm_rate'], m['false_alarm_ci'])} | "
                     f"{pct(m['correct_verified_clean'])} | {m['n_faulty']} / {m['n_correct']} |")
    return lines + [""]


def write_outputs(rows, tasks, seconds):
    os.makedirs(OUT, exist_ok=True)
    systems = [("A  checks only", "A_checks_only|tests"),
               ("B  + given tests", "B_given_tests|tests"),
               ("C- no templates", "C_no_templates|tests"),
               ("C  FactGuard full", "C_full|tests"),
               ("C+ probes (Python)", "C_plus_probes|tests")]
    no_tests = [("A  checks only", "A_checks_only|tests"),
                ("C- no templates", "C_no_templates|no_tests"),
                ("C  FactGuard full", "C_full|no_tests")]
    langs = {"python": "Python", "c": "C", "cpp": "C++", "java": "Java"}
    lines = ["# FactGuard AI - experiment results", "",
             f"Execution: local; {len(rows)} tasks ({sum(r['label'] == 'faulty' for r in rows)} "
             f"faulty, {sum(r['label'] == 'correct' for r in rows)} correct) in "
             f"{len({r['family'] for r in rows})} problem families; run time {seconds:.0f} s.", "",
             "## How to read this", "",
             "- **Faulty caught** = the system reported a confirmed defect on faulty code.",
             "- **False assurance** = the system said *no defect found* on faulty code. This is the "
             "dangerous failure; *uncertain* (could not verify, weak tests) is the honest alternative.",
             "- **False alarms** = a defect reported on correct code.",
             "- Intervals in brackets resample whole problem families, so they are wider than "
             "naive ones and reflect that a faulty task and its correct twin are not independent.",
             "- All tasks were written by one author (who also wrote the templates and repair rules). "
             "The numbers show how the system behaves on a seeded bug catalogue. They do not show "
             "how it would do on code it has never seen, and must not be compared with the SDHD "
             "paper's F1 scores. See dataset/README_EXTERNAL.md.", ""]
    lines += table(f"All tasks, tests given (first {GIVEN_K} hidden cases)", rows, systems)
    lines += table("All tasks, NO tests given", rows, no_tests)
    for origin, title in (("base37", "Original 37 tasks"), ("extra", "New template-free Python tasks"),
                          ("native", "C, C++ and Java tasks"), ("external", "Independently written tasks")):
        subset = [r for r in rows if r["origin"].startswith(origin)]
        if subset:
            lines += table(f"{title} - tests given", subset, systems[:4])
    lines += table("Tasks whose requirement matches a built-in template - no tests given",
                   [r for r in rows if r["in_template"]], no_tests)
    lines += table("Tasks with NO template - no tests given",
                   [r for r in rows if not r["in_template"]], no_tests)
    for code, name in langs.items():
        subset = [r for r in rows if r["language"] == code]
        if subset:
            lines += table(f"{name} - tests given", subset, systems[:4])

    lines += ["## Does the full system beat 'given tests only'? (paired, family-clustered)", ""]
    for title, subset in (("All faulty tasks", rows),
                          ("Tasks with no template", [r for r in rows if not r["in_template"]])):
        for cond_key, cond in (("C_full|tests", "tests given"), ("C_full|no_tests", "no tests")):
            diff = paired_difference(subset, cond_key, "B_given_tests|" + cond_key.split("|")[1])
            if diff:
                low, high = diff["ci"]
                lines.append(f"- {title}, {cond}: C minus B = {100 * diff['difference']:+.0f} points "
                             f"of recall (95% interval {100 * low:+.0f} to {100 * high:+.0f}; "
                             f"{diff['n_faulty']} faulty tasks)")
    lines.append("")

    rep = repair_report(rows)
    lines += ["## Repair (full system, tests given)", "",
              f"- Faulty tasks detected: {rep['detected_faulty']}",
              f"- Repairs accepted by FactGuard's own checks: {rep['accepted']}",
              f"- ...and also passing the hidden tests: {rep['accepted_and_passes_hidden']}",
              f"- Accepted but failing the hidden tests: {', '.join(rep['accepted_but_wrong']) or 'none'}",
              f"- Repair success (of detected faulty): {pct(rep['success_rate_of_detected'])}",
              f"- Repairs accepted on code that was actually correct: "
              f"{', '.join(rep['repairs_accepted_on_correct_code']) or 'none'}",
              "- By method (rules were written for known idioms; mutation search is generic): " +
              (", ".join(f"{k}: {v['right']}/{v['accepted']} right" for k, v in
                         rep["by_strategy"].items()) or "none")]
    for reason, ids in rep["not_repaired"].items():
        lines.append(f"- Not repaired - {reason}: {len(ids)} ({', '.join(ids)})")
    lines.append("")

    lines += ["## Tasks where the full system gave FALSE ASSURANCE (tests given)", ""]
    fa = [r for r in rows if r["label"] == "faulty"
          and r["runs"]["C_full|tests"]["outcome"] == "no_defect_found"]
    lines += [f"- {r['id']} ({r['language']}, {r['fault']}, family {r['family']})" for r in fa] \
        or ["- none"]
    lines += ["", "## False alarms (full system, tests given)", ""]
    fp = [r for r in rows if r["label"] == "correct"
          and r["runs"]["C_full|tests"]["outcome"] == "defects"]
    lines += [f"- {r['id']}: {r['runs']['C_full|tests']['labels']}" for r in fp] or ["- none"]

    audit_info = audit(tasks, rows)
    lines += ["", "## Audit", "",
              f"- Systems read only: {', '.join(audit_info['systems_see_only'])}. Hidden tests, labels and "
              f"fault types are never passed to them: {not audit_info['hidden_or_label_visible_to_systems']}.",
              f"- Requirements matching a built-in template: {pct(audit_info['template_match_rate'])} of tasks "
              "(this is NOT the rate on real-world requirements; run measure_template_match.py on "
              "prompts from a public benchmark to estimate that).",
              f"- Template/hidden-test overlap on {audit_info['template_tasks_python']} Python template "
              f"tasks: on average {pct(audit_info['mean_template_case_overlap_with_hidden'])} of the "
              "template's test inputs also appear in the hidden tests, so template-task results are "
              "not independent evidence."]
    with open(os.path.join(OUT, "summary.md"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    keys = [f"{s}|{c}" for s in SYSTEMS for c in ("tests", "no_tests")]
    with open(os.path.join(OUT, "per_task.csv"), "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["task", "language", "family", "label", "fault", "origin", "in_template"] + keys)
        for r in rows:
            writer.writerow([r["id"], r["language"], r["family"], r["label"], r["fault"], r["origin"],
                             r["in_template"]] + [r["runs"].get(k, {}).get("outcome", "") for k in keys])
    summary = {"mode": "local", "n_tasks": len(rows), "audit": audit_info, "repair": rep,
               "metrics": {k: metrics(rows, k) for k in keys if any(k in r["runs"] for r in rows)}}
    with open(os.path.join(OUT, "results.json"), "w", encoding="utf-8") as handle:
        json.dump({"summary": summary, "tasks": rows}, handle, indent=1, default=str)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="only the first N tasks")
    parser.add_argument("--languages", default="python,c,cpp,java")
    parser.add_argument("--fresh", action="store_true", help="ignore cached per-task results")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    languages = set(args.languages.split(","))
    tasks = [t for t in ALL_TASKS if t["language"] in languages]
    tasks = tasks[:args.limit] if args.limit else tasks
    if args.fresh:
        shutil.rmtree(CACHE, ignore_errors=True)
    print(f"Execution: local; tasks: {len(tasks)}; workers: {args.workers}", flush=True)
    started, done = time.time(), 0
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(lambda t: run_task(t, languages), tasks):
            rows.append(row)
            done += 1
            if done % 10 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)} done ({time.time() - started:.0f}s)", flush=True)
    write_outputs(rows, tasks, time.time() - started)
    print("Wrote results/summary.md, results.json, per_task.csv", flush=True)


if __name__ == "__main__":
    main()
