"""The complete evaluation set: base tasks + template-free Python + C/C++/Java + any
externally written tasks found in dataset/external/*.json.

Given tests (review F3): every task gets the SAME mechanical rule, so test
availability no longer correlates with template availability and nobody can pick
tests that happen to catch or miss the bug:

    given = the first GIVEN_K hidden cases   (condition "tests")
    given = nothing                          (condition "no_tests")

Systems only ever see: requirement, code, function, language and `given`.
"""
import glob
import json
import os

from . import extra_python, native_tasks
from .builders import task as _t
from .tasks import TASKS as BASE

GIVEN_K = 2

# Problem family of each of the first 37 tasks (the review found most of them were
# faulty/correct twins of about ten base problems, so results are reported per family).
BASE_FAMILY = {
    **{t: "contains_letter" for t in ("T01", "T02", "T03", "T04")},
    **{t: "sum_list" for t in ("T05", "T06", "T07", "T20", "T22", "T24")},
    "T08": "max_list", "T09": "max_list", "T10": "even_numbers", "T11": "even_numbers",
    "T12": "reverse_string", "T13": "reverse_string", "T14": "palindrome", "T15": "palindrome",
    "T16": "factorial", "T17": "factorial", "T23": "factorial",
    "T18": "count_vowels", "T19": "count_vowels", "T21": "sqrt", "T37": "sqrt",
    "T25": "last_element", "T26": "circle_area", "T27": "circle_area",
    "T28": "count_words", "T29": "count_words", "T30": "is_prime", "T31": "is_prime",
    "T32": "absolute", "T33": "absolute", "T34": "square", "T35": "smaller", "T36": "shout",
}


def _base_tasks():
    out = []
    for item in BASE:
        out.append({
            "id": item["id"], "language": "python", "family": BASE_FAMILY[item["id"]],
            "label": item["label"], "fault": item["fault"], "requirement": item["requirement"],
            "code": item["code"], "function": item["function"], "hidden": item["hidden"],
            "hidden_property": None, "origin": "base37"})
    return out


def _external_tasks():
    """Tasks written by someone else. See dataset/README_EXTERNAL.md for the format."""
    out = []
    pattern = os.path.join(os.path.dirname(os.path.abspath(__file__)), "external", "*.json")
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as handle:
            for item in json.load(handle):
                hidden = [(c["args"], c["expected"]) for c in item["hidden"]]
                task = _t(item["id"], item.get("language", "python"), item["family"],
                          item["label"], item.get("fault", "-"), item["requirement"],
                          item["code"], item["function"], hidden,
                          item.get("hidden_property"), origin="external:" + item.get("author", "?"))
                out.append(task)
    return out


def _with_given(task, k=GIVEN_K):
    origin = task["origin"]
    if origin == "extra" and task["language"] != "python":
        origin = "native"
    return dict(task, origin=origin, given=[dict(c) for c in task["hidden"][:k]])


def all_tasks(include_external=True):
    tasks = _base_tasks() + extra_python.TASKS + native_tasks.TASKS
    if include_external:
        tasks += _external_tasks()
    return [_with_given(t) for t in tasks]


ALL_TASKS = all_tasks()
