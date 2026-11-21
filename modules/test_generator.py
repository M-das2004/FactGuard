"""Test Generator: requirement-aware test templates and coverage-guided probes.

Two sources of tests:

1. Curated templates. When the requirement matches a known task type, a
   trusted reference oracle supplies expected outputs (normal, edge and
   boundary cases). This is the "specification-aware" part. Unknown
   requirements produce no template tests: the user's own cases are used.
2. Coverage-guided probes. For every branch the tests missed, inputs are
   proposed from the condition that controls it. Probes have NO expected
   value (we cannot know the right answer), so they only look for crashes
   and for new coverage.
"""
import re

from .ast_analyzer import find_branch_conditions

_Q = r"['\"‘’“”]?"


def _contains_letter(match):
    letter = match.group(1)
    sample = [f"{letter}pple", f"ban{letter}n{letter}", f"c{letter}t", "dog", f"my{letter}",
              f"x{letter}"]
    expect = lambda words: [w for w in words if letter in w]  # noqa: E731
    inputs = [
        ("normal", sample), ("edge", []), ("edge", ["dog", "fish"]),
        ("boundary", [letter]), ("boundary", ["zzz" + letter]),
        ("boundary", [letter + "zzz"]), ("boundary", ["zz" + letter + "zz"]),
        ("assumption", [letter.upper() + "bc"]),
    ]
    cases = []
    for kind, words in inputs:
        note = ""
        if kind == "assumption":
            note = "Assumes matching is case-sensitive."
        cases.append({"kind": kind, "args": [words], "expected": expect(words), "note": note})
    return cases, ["Matching is case-sensitive (an uppercase-letter test is marked as an assumption)."]


def _sum_list(_):
    return _plain(lambda xs: sum(xs), [([1, 2, 3], "normal"), ([], "edge"), ([5], "boundary"),
                                       ([-1, 1], "boundary"), ([10, -3, 4], "normal")])


def _max_list(_):
    return _plain(lambda xs: max(xs), [([3, 1, 2], "normal"), ([7], "boundary"),
                                       ([-5, -2, -9], "edge"), ([2, 2, 2], "boundary"),
                                       ([1, 9, 4, 9], "normal")],
                  ["The list is never empty."])


def _even_numbers(_):
    return _plain(lambda xs: [x for x in xs if x % 2 == 0],
                  [([1, 2, 3, 4], "normal"), ([], "edge"), ([1, 3], "edge"), ([0], "boundary"),
                   ([-2, -1], "boundary"), ([2, 4, 6], "normal")])


def _reverse_string(_):
    return _plain(lambda s: s[::-1], [("abc", "normal"), ("", "edge"), ("a", "boundary"),
                                      ("hello world", "normal")])


def _palindrome(_):
    return _plain(lambda s: s == s[::-1], [("level", "normal"), ("abc", "normal"),
                                           ("", "edge"), ("a", "boundary"), ("ab", "boundary"),
                                           ("abca", "boundary")],
                  ["Comparison is case-sensitive and does not ignore spaces."])


def _factorial(_):
    def fact(n):
        out = 1
        for i in range(2, n + 1):
            out *= i
        return out
    return _plain(fact, [(0, "boundary"), (1, "boundary"), (5, "normal"), (3, "normal"),
                         (7, "normal")])


def _count_vowels(_):
    return _plain(lambda s: sum(1 for ch in s if ch in "aeiou"),
                  [("hello", "normal"), ("", "edge"), ("xyz", "edge"), ("aeiou", "boundary")],
                  ["Only lowercase a, e, i, o, u count as vowels."])


def _plain(oracle, inputs, assumptions=None):
    cases = [{"kind": kind, "args": [value], "expected": oracle(value), "note": ""}
             for value, kind in inputs]
    return cases, assumptions or []


# (name, regular expression on the lower-cased requirement, builder)
TEMPLATES = [
    ("filter words containing a letter",
     re.compile(r"contain\w*\s+(?:the\s+)?(?:letter|character|char|substring)\s+" + _Q
                + r"([a-z]+)", re.I), _contains_letter),
    ("sum of a list", re.compile(r"\bsum\b.*\b(list|numbers|elements|integers)\b"), _sum_list),
    ("maximum of a list", re.compile(r"\b(maximum|largest|max)\b.*\blist\b"), _max_list),
    ("even numbers in a list", re.compile(r"\beven numbers\b"), _even_numbers),
    ("reverse a string", re.compile(r"\breverse\b.*\bstring\b"), _reverse_string),
    ("palindrome check", re.compile(r"\bpalindrome\b"), _palindrome),
    ("factorial", re.compile(r"\bfactorial\b"), _factorial),
    ("count vowels", re.compile(r"\bcount\b.*\bvowels?\b"), _count_vowels),
]


# Words that make a template the WRONG oracle even though its keywords match, e.g.
# "second largest number in a list" is not "largest number in a list". Found by the
# evaluation: without this, correct code was reported as defective.
_EXCLUDE = re.compile(r"\b(second|third|kth|k-th|nth|top|k|n)\s+(largest|smallest|biggest|"
                      r"highest|lowest|elements?|numbers?|items?)\b|\bsecond\b|\bdistinct\b|"
                      r"\bunique\b|\brunning\b|\bcumulative\b|\bsorted\b|\bdescending\b")


def generate_from_requirement(requirement):
    """Return {"template", "cases", "assumptions"} or None if nothing matches."""
    text = (requirement or "").lower()
    if _EXCLUDE.search(text):
        return None
    for name, pattern, builder in TEMPLATES:
        match = pattern.search(text)
        if match:
            cases, assumptions = builder(match)
            for number, case in enumerate(cases, 1):
                case["id"] = f"tpl-{number}"
                case["kwargs"] = {}
            return {"template": name, "cases": cases, "assumptions": assumptions}
    return None


def merge_cases(*groups):
    """Join case lists and drop duplicates (same args and kwargs)."""
    seen, merged = set(), []
    for group in groups:
        for case in group:
            key = repr((case.get("args"), case.get("kwargs", {})))
            if key not in seen:
                seen.add(key)
                merged.append(case)
    return merged


def _candidates(base, condition):
    """Values near a comparison constant, matching the type of the base value."""
    const, name_len = condition["const"], condition.get("via_len")
    if name_len and isinstance(base, (list, str)) and isinstance(const, int):
        filler = base[:1] if base else ([0] if isinstance(base, list) else "a")
        if isinstance(base, str) and not base:
            filler = "a"
        sizes = {max(0, const - 1), const, const + 1, 0}
        return [filler * size if isinstance(base, str) else list(filler) * size
                for size in sorted(sizes)]
    if isinstance(base, bool):
        return [not base]
    if isinstance(base, (int, float)) and isinstance(const, (int, float)) \
            and not isinstance(const, bool):
        step = 1 if isinstance(base, int) else 0.5
        return [const - step, const, const + step]
    if isinstance(base, str) and isinstance(const, str):
        return [const, "", const + "x"]
    return []


def suggest_probe_cases(tree, function_name, params, base_cases, missing_branches,
                        limit=12):
    """Propose crash-only probe inputs for branches that tests never reached."""
    if not base_cases or not params:
        return []
    base = base_cases[0]
    probes, seen = [], set()
    for origin, _target in missing_branches:
        conditions = find_branch_conditions(tree, origin)
        for condition in conditions:
            name = condition["name"]
            if name in params:
                position = params.index(name)
                if position >= len(base["args"]):
                    continue
                for value in _candidates(base["args"][position], condition):
                    args = list(base["args"])
                    args[position] = value
                    key = repr(args)
                    if key not in seen:
                        seen.add(key)
                        probes.append({"id": f"probe-{len(probes) + 1}", "kind": "probe",
                                       "probe": True, "args": args, "kwargs": {},
                                       "target_line": origin})
        # Loops: try an empty and a longer version of each list/str argument.
        if any(c["op"] == "Loop" for c in conditions):
            for position, value in enumerate(base["args"]):
                if isinstance(value, (list, str)):
                    for variant in ([] if isinstance(value, list) else "", value * 2):
                        args = list(base["args"])
                        args[position] = variant
                        key = repr(args)
                        if key not in seen:
                            seen.add(key)
                            probes.append({"id": f"probe-{len(probes) + 1}", "kind": "probe",
                                           "probe": True, "args": args, "kwargs": {},
                                           "target_line": origin})
    return probes[:limit]


def hidden_overlap(template_cases, hidden):
    """Share of a template's test inputs that also occur in the hidden tests (0..1).
    Used only by the evaluation audit: a high value means the template and the ground
    truth were written from the same idea, so results on that task are not independent."""
    if not template_cases:
        return 0.0
    seen = {repr(case["args"]) for case in hidden}
    return sum(1 for case in template_cases if repr(case["args"]) in seen) / len(template_cases)
