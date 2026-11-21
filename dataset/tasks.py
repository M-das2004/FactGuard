"""Starter evaluation dataset for FactGuard AI.

IMPORTANT - read before quoting results:
  * Every task here was written by hand for this project. It is a small starter
    set (not a published benchmark) meant to exercise the pipeline.
  * "label" is the ground truth: "faulty" or "correct". It is checked
    automatically: faulty code must fail at least one hidden test (or not run),
    correct code must pass all hidden tests (see tests/test_dataset.py).
  * "given" are the test cases a user might supply. "hidden" tests are used only
    to judge repairs and to validate labels; no system sees them.
  * Some requirements match a built-in FactGuard template. Those tasks are
    in-distribution for the system (the same author wrote both), so results on
    them are NOT independent evidence. The experiment reports them separately.
"""


def _t(task_id, label, fault, requirement, code, function, given, hidden):
    return {
        "id": task_id, "label": label, "fault": fault, "requirement": requirement,
        "code": code, "function": function,
        "given": [{"args": a, "expected": e} for a, e in given],
        "hidden": [{"args": a, "expected": e} for a, e in hidden],
    }


R_A = "Find all words containing the letter 'a' from a list of words."
R_E = "Find all words containing the letter 'e' from a list of words."
R_O = "Find all words containing the letter 'o' from a list of words."
R_SUM = "Return the sum of a list of numbers."
R_MAX = "Return the largest number in a list."
R_EVEN = "Return the even numbers from a list."
R_REV = "Reverse a string."
R_PAL = "Check whether a string is a palindrome."
R_FACT = "Compute the factorial of a number."
R_VOW = "Count the vowels in a string."

HID_A = [([["apple", "banana", "cat", "dog"]], ["apple", "banana", "cat"]),
         ([[]], []), ([["xyz"]], []), ([["zzza"]], ["zzza"]), ([["azz"]], ["azz"])]
HID_E = [([["tree", "sky", "end"]], ["tree", "end"]), ([[]], []), ([["xyz"]], []),
         ([["zze"]], ["zze"]), ([["ezz"]], ["ezz"])]
HID_O = [([["dog", "cat", "oak"]], ["dog", "oak"]), ([[]], []), ([["xyz"]], []),
         ([["zzo"]], ["zzo"])]
HID_SUM = [([[1, 2, 3]], 6), ([[]], 0), ([[5]], 5), ([[-1, 1]], 0), ([[10, -3, 4]], 11)]
HID_MAX = [([[3, 1, 2]], 3), ([[7]], 7), ([[-5, -2, -9]], -2), ([[1, 9, 4, 9]], 9)]
HID_EVEN = [([[1, 2, 3, 4]], [2, 4]), ([[]], []), ([[1, 3]], []), ([[0]], [0]),
            ([[-2, -1]], [-2])]
HID_REV = [(["abc"], "cba"), ([""], ""), (["a"], "a"), (["hello world"], "dlrow olleh")]
HID_PAL = [(["level"], True), (["abc"], False), ([""], True), (["a"], True),
           (["abca"], False), (["ab"], False)]
HID_FACT = [([0], 1), ([1], 1), ([5], 120), ([3], 6), ([7], 5040)]
HID_VOW = [(["hello"], 2), ([""], 0), (["xyz"], 0), (["aeiou"], 5), (["education"], 5)]

TASKS = [
    # ---- requirement-template tasks (in-distribution for FactGuard) --------
    _t("T01", "faulty", "logic", R_A,
       'def find_words(words):\n    return [w for w in words if w.startswith("a")]\n',
       "find_words", [], HID_A),
    _t("T02", "correct", "-", R_A,
       'def find_words(words):\n    return [w for w in words if "a" in w]\n',
       "find_words", [], HID_A),
    _t("T03", "faulty", "logic", R_E,
       'def find_words(words):\n    return [w for w in words if w.endswith("e")]\n',
       "find_words", [], HID_E),
    _t("T04", "correct", "-", R_O,
       'def find_words(words):\n    return [w for w in words if w.count("o") > 0]\n',
       "find_words", [], HID_O),
    _t("T05", "faulty", "logic", R_SUM,
       "def total(xs):\n    s = 0\n    for i in range(1, len(xs)):\n        s += xs[i]\n    return s\n",
       "total", [], HID_SUM),
    _t("T06", "correct", "-", R_SUM,
       "def total(xs):\n    s = 0\n    for x in xs:\n        s += x\n    return s\n",
       "total", [], HID_SUM),
    _t("T07", "faulty", "logic", R_SUM,
       "def total(xs):\n    return len(xs)\n", "total", [], HID_SUM),
    _t("T08", "faulty", "logic", R_MAX,
       "def biggest(xs):\n    return min(xs)\n", "biggest", [], HID_MAX),
    _t("T09", "correct", "-", R_MAX,
       "def biggest(xs):\n    best = xs[0]\n    for x in xs:\n        if x > best:\n            best = x\n    return best\n",
       "biggest", [], HID_MAX),
    _t("T10", "faulty", "logic", R_EVEN,
       "def evens(xs):\n    return [x for x in xs if x % 2 == 1]\n", "evens", [], HID_EVEN),
    _t("T11", "correct", "-", R_EVEN,
       "def evens(xs):\n    return [x for x in xs if x % 2 == 0]\n", "evens", [], HID_EVEN),
    _t("T12", "faulty", "logic", R_REV,
       "def rev(s):\n    return s[::-1][1:]\n", "rev", [], HID_REV),
    _t("T13", "correct", "-", R_REV,
       "def rev(s):\n    return ''.join(reversed(s))\n", "rev", [], HID_REV),
    _t("T14", "faulty", "logic+crash", R_PAL,
       "def is_pal(s):\n    return s[0] == s[-1]\n", "is_pal", [], HID_PAL),
    _t("T15", "correct", "-", R_PAL,
       "def is_pal(s):\n    return s == s[::-1]\n", "is_pal", [], HID_PAL),
    _t("T16", "faulty", "logic", R_FACT,
       "def fact(n):\n    out = 1\n    for i in range(1, n):\n        out *= i\n    return out\n",
       "fact", [], HID_FACT),
    _t("T17", "correct", "-", R_FACT,
       "def fact(n):\n    return 1 if n <= 1 else n * fact(n - 1)\n", "fact", [], HID_FACT),
    _t("T18", "faulty", "logic", R_VOW,
       "def vowels(s):\n    return sum(1 for ch in s if ch in 'aeio')\n", "vowels", [], HID_VOW),
    _t("T19", "correct", "-", R_VOW,
       "def vowels(s):\n    return sum(1 for ch in s if ch in 'aeiou')\n", "vowels", [], HID_VOW),

    # ---- static / API / crash faults (requirement may or may not match) ----
    _t("T20", "faulty", "naming", R_SUM,
       "def total(xs):\n    s = 0\n    for x in xs:\n        s += x\n    return ss\n",
       "total", [], HID_SUM),
    _t("T21", "faulty", "api", "Return the square root of a number.",
       "import math\n\ndef root(n):\n    return math.sqroot(n)\n", "root",
       [([16], 4.0)], [([16], 4.0), ([2], 1.4142135623730951), ([0], 0.0)]),
    _t("T22", "faulty", "syntax", R_SUM,
       "def total(xs)\n    return sum(xs)\n", "total", [], HID_SUM),
    _t("T23", "faulty", "api", "Return the factorial of a number.",
       "from math import factorial2\n\ndef fact(n):\n    return factorial2(n)\n", "fact",
       [([5], 120)], HID_FACT),
    _t("T24", "faulty", "resource", R_SUM,
       "def total(xs):\n    while True:\n        pass\n", "total", [], HID_SUM),
    _t("T25", "faulty", "structure", "Return the last element of a list.",
       "def last(xs):\n    return xs[len(xs)]\n", "last",
       [([[1, 2, 3]], 3)], [([[1, 2, 3]], 3), ([[9]], 9), ([["a", "b"]], "b")]),

    # ---- tasks without a template: the system relies on given tests --------
    _t("T26", "faulty", "logic", "Return the area of a circle given its radius.",
       "def area(r):\n    return 3.14 * r * r\n", "area",
       [([5], 78.53981633974483)],
       [([5], 78.53981633974483), ([1], 3.141592653589793), ([0], 0.0)]),
    _t("T27", "correct", "-", "Return the area of a circle given its radius.",
       "import math\n\ndef area(r):\n    return math.pi * r * r\n", "area",
       [([5], 78.53981633974483)],
       [([5], 78.53981633974483), ([1], 3.141592653589793), ([0], 0.0)]),
    _t("T28", "faulty", "logic", "Return the number of words in a sentence.",
       "def count_words(s):\n    return len(s.split(' '))\n", "count_words", [],
       [(["hello world"], 2), ([""], 0), (["a  b"], 2), (["one"], 1)]),
    _t("T29", "correct", "-", "Return the number of words in a sentence.",
       "def count_words(s):\n    return len(s.split())\n", "count_words", [],
       [(["hello world"], 2), ([""], 0), (["a  b"], 2), (["one"], 1)]),
    _t("T30", "faulty", "logic", "Return True if a number is prime.",
       "def is_prime(n):\n    for i in range(2, n):\n        if n % i == 0:\n            return False\n    return True\n",
       "is_prime", [([7], True), ([8], False)],
       [([7], True), ([8], False), ([1], False), ([0], False), ([2], True), ([9], False)]),
    _t("T31", "correct", "-", "Return True if a number is prime.",
       "def is_prime(n):\n    if n < 2:\n        return False\n    for i in range(2, int(n ** 0.5) + 1):\n        if n % i == 0:\n            return False\n    return True\n",
       "is_prime", [([7], True), ([8], False)],
       [([7], True), ([8], False), ([1], False), ([0], False), ([2], True), ([9], False)]),
    _t("T32", "faulty", "logic", "Return the absolute value of a number.",
       "def absval(x):\n    return x if x > 0 else x\n", "absval",
       [([-3], 3)], [([-3], 3), ([4], 4), ([0], 0)]),
    _t("T33", "correct", "-", "Return the absolute value of a number.",
       "def absval(x):\n    return x if x >= 0 else -x\n", "absval",
       [([-3], 3)], [([-3], 3), ([4], 4), ([0], 0)]),
    _t("T34", "correct", "-", "Return the square of a number.",
       "def square(x):\n    return x * x\n", "square", [([3], 9)],
       [([3], 9), ([0], 0), ([-2], 4)]),
    _t("T35", "correct", "-", "Return the smaller of two numbers.",
       "def smaller(a, b):\n    return a if a < b else b\n", "smaller",
       [([1, 2], 1)], [([1, 2], 1), ([5, 3], 3), ([2, 2], 2)]),
    _t("T36", "correct", "-", "Return every word in uppercase.",
       "def shout(words):\n    return [w.upper() for w in words]\n", "shout",
       [([["a", "b"]], ["A", "B"])], [([["a", "b"]], ["A", "B"]), ([[]], [])]),
    _t("T37", "correct", "-", "Return the square root of a number.",
       "import math\n\ndef root(n):\n    return math.sqrt(n)\n", "root",
       [([16], 4.0)], [([16], 4.0), ([2], 1.4142135623730951), ([0], 0.0)]),
]
