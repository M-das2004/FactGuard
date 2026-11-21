"""Ground-truth labels are checked by running every task against its hidden tests."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from dataset.all_tasks import ALL_TASKS, GIVEN_K
from dataset.validate import hidden_outcome, is_correct_outcome
from modules.execution_engine import missing_tools
from run_experiment import SYSTEMS, VISIBLE


def test_ids_unique_and_languages_present():
    ids = [t["id"] for t in ALL_TASKS]
    assert len(ids) == len(set(ids))
    assert {t["language"] for t in ALL_TASKS} == {"python", "c", "cpp", "java"}
    labels = [t["label"] for t in ALL_TASKS]
    assert labels.count("faulty") >= 60 and labels.count("correct") >= 50
    assert len({t["family"] for t in ALL_TASKS}) >= 40


def test_given_tests_follow_the_mechanical_rule():
    for task in ALL_TASKS:
        assert task["given"] == task["hidden"][:GIVEN_K]


def test_systems_never_see_hidden_information():
    assert not {"hidden", "label", "fault", "hidden_property", "family", "id"} & set(VISIBLE)
    assert set(SYSTEMS) >= {"A_checks_only", "B_given_tests", "C_full"}


def test_labels_match_hidden_tests(run_mode):
    needed = {t["language"] for t in ALL_TASKS if t["language"] != "python"}
    if any(missing_tools(lang) for lang in needed):
        pytest.skip("C/C++/Java compilers are not installed on this computer")
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(
            lambda t: hidden_outcome(t), ALL_TASKS))
    wrong = [(t["id"], t["label"], o) for t, o in zip(ALL_TASKS, outcomes)
             if (t["label"] == "correct") != is_correct_outcome(o)]
    assert not wrong, f"label does not match behaviour: {wrong}"
    assert not [t["id"] for t, o in zip(ALL_TASKS, outcomes)
                if o in ("unsupported", "sandbox-error")]
