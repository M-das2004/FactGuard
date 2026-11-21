"""Regression tests for the findings of the model review."""
from modules.pipeline import analyze
from modules.test_generator import generate_from_requirement


def go(req, src, run_mode, **kw):
    kw.setdefault("timeout", 2)
    return analyze(req, src, allow_local=True, **kw)


def test_template_does_not_claim_a_different_problem():
    # "second largest" is not "largest": the old template flagged correct code.
    assert generate_from_requirement("Return the second largest distinct number in a list.") is None
    assert generate_from_requirement("Return the k largest numbers of a list.") is None
    assert generate_from_requirement("Return the largest number in a list.")


def test_template_skipped_when_function_arity_differs(run_mode):
    result = go("Return the largest number in a list.",
                "def top(xs, k):\n    return sorted(xs, reverse=True)[:k]\n", run_mode,
                do_repair=False)
    assert result["template"] is None
    assert result["status"] == "unverified"


def test_no_oracle_means_could_not_verify_not_clean(run_mode):
    code = "def count_words(s):\n    return len(s.split(' '))\n"   # buggy, but nothing to test it with
    result = go("Return the number of words in a sentence.", code, run_mode)
    assert result["status"] == "unverified"
    assert "Could not verify" in result["verdict"]


def test_weak_tests_do_not_give_false_assurance(run_mode):
    code = ("def is_prime(n):\n    for i in range(2, n):\n        if n % i == 0:\n"
            "            return False\n    return True\n")          # wrong for 0 and 1
    result = go("Return True if a number is prime.", code, run_mode,
                cases='[{"args": [7], "expected": true}, {"args": [8], "expected": false}]')
    assert result["status"] != "no_defect_found"


def test_property_check_catches_hidden_side_effect(run_mode):
    code = "def sorted_copy(xs):\n    xs.sort()\n    return xs\n"
    cases = '[{"args": [[3, 1, 2]], "expected": [1, 2, 3]}]'      # the output is right!
    result = go("Return a sorted copy of a list without changing the original.", code,
                run_mode, cases=cases, do_repair=False)
    assert result["status"] == "defects"
    assert any(f["source"] == "property" for f in result["findings"])


def test_property_check_allows_local_copies_and_in_place_requirements(run_mode):
    cases = '[{"args": [[3, 1, 2]], "expected": [1, 2, 3]}]'
    local = "def f(xs):\n    ys = list(xs)\n    ys.sort()\n    return ys\n"
    assert go("Return a sorted copy of a list.", local, run_mode, cases=cases)["status"] != "defects"
    inplace = "def f(xs):\n    xs.sort()\n    return xs\n"
    assert go("Sort the list in place and return it.", inplace, run_mode,
              cases=cases)["status"] != "defects"


def test_coverage_probes_are_off_by_default(run_mode):
    code = "def t(xs):\n    if len(xs) > 3:\n        return sum(xs)\n    return sum(xs)\n"
    result = go("Return the sum of a list of numbers.", code, run_mode,
                cases='[{"input": [1, 2], "expected": 3}]', use_templates=False)
    assert not result["coverage"].get("probes_added")
