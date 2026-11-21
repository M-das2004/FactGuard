"""Python tasks whose requirements match NO built-in template.

These exist because the model review found that the first 37 tasks mostly
exercised the templates. Here the system has no requirement oracle at all: it can
rely only on the compiler/static checks, the tests it is given, the test-strength
check and the template-free property check.

Written by the same author as the rest of the starter set, so the bugs are still a
hand-made catalogue (not independent). See dataset/README_EXTERNAL.md for how the
team can add independently written tasks.
"""
from .builders import task as _t

TASKS = []


def add(*args, **kwargs):
    TASKS.append(_t(*args, **kwargs))


# --- logic faults in simple algorithms ---------------------------------------
R = "Return the second largest distinct number in a list."
H = [([[3, 1, 2]], 2), ([[5, 5, 4]], 4), ([[1, 2, 2, 3, 3]], 2), ([[10, 9]], 9)]
add("P01", "python", "second_largest", "faulty", "logic", R,
    "def second_largest(xs):\n    return sorted(xs)[-2]\n", "second_largest", H)
add("P02", "python", "second_largest", "correct", "-", R,
    "def second_largest(xs):\n    return sorted(set(xs))[-2]\n", "second_largest", H)

R = "Count how many times a character appears in a string."
H = [(["banana", "a"], 3), (["", "x"], 0), (["hello", "l"], 2), (["abc", "z"], 0)]
add("P03", "python", "count_char", "faulty", "logic", R,
    "def count_char(s, c):\n    return 1 if c in s else 0\n", "count_char", H)
add("P04", "python", "count_char", "correct", "-", R,
    "def count_char(s, c):\n    return s.count(c)\n", "count_char", H)

R = ("Return 'Fizz' for multiples of 3, 'Buzz' for multiples of 5, 'FizzBuzz' for multiples "
     "of both, otherwise the number as a string.")
H = [([3], "Fizz"), ([5], "Buzz"), ([15], "FizzBuzz"), ([7], "7"), ([30], "FizzBuzz"),
     ([1], "1")]
add("P05", "python", "fizzbuzz", "faulty", "logic", R,
    'def fizz(n):\n    if n % 3 == 0:\n        return "Fizz"\n    if n % 5 == 0:\n'
    '        return "Buzz"\n    if n % 15 == 0:\n        return "FizzBuzz"\n    return str(n)\n',
    "fizz", H)
add("P06", "python", "fizzbuzz", "correct", "-", R,
    'def fizz(n):\n    if n % 15 == 0:\n        return "FizzBuzz"\n    if n % 3 == 0:\n'
    '        return "Fizz"\n    if n % 5 == 0:\n        return "Buzz"\n    return str(n)\n',
    "fizz", H)

R = "Convert a temperature from Celsius to Fahrenheit."
H = [([0], 32.0), ([100], 212.0), ([-40], -40.0), ([37], 98.6)]
add("P07", "python", "celsius", "faulty", "logic", R,
    "def c_to_f(c):\n    return c * 9 / 5\n", "c_to_f", H)
add("P08", "python", "celsius", "correct", "-", R,
    "def c_to_f(c):\n    return c * 9 / 5 + 32\n", "c_to_f", H)

R = "Merge two sorted lists into one sorted list."
H = [([[1, 5], [2, 3]], [1, 2, 3, 5]), ([[], []], []), ([[2], [1, 3]], [1, 2, 3])]
add("P09", "python", "merge_sorted", "faulty", "logic", R,
    "def merge(a, b):\n    return a + b\n", "merge", H)
add("P10", "python", "merge_sorted", "correct", "-", R,
    "def merge(a, b):\n    return sorted(a + b)\n", "merge", H)

R = ("Remove duplicates from a list, keeping the first occurrence of each item in its "
     "original order.")
H = [([[3, 1, 3, 2]], [3, 1, 2]), ([[]], []), ([[1, 1, 1]], [1]), ([[5, 4, 5, 4, 3]], [5, 4, 3])]
add("P11", "python", "dedupe", "faulty", "logic", R,
    "def dedupe(xs):\n    return list(set(xs))\n", "dedupe", H)
add("P12", "python", "dedupe", "correct", "-", R,
    "def dedupe(xs):\n    return list(dict.fromkeys(xs))\n", "dedupe", H)

R = "Return the greatest common divisor of two positive integers."
H = [([12, 18], 6), ([7, 13], 1), ([10, 5], 5), ([9, 9], 9), ([14, 21], 7)]
add("P13", "python", "gcd", "faulty", "logic", R,
    "def gcd(a, b):\n    return min(a, b)\n", "gcd", H)
add("P14", "python", "gcd", "correct", "-", R,
    "def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return a\n", "gcd", H)

R = "Capitalize the first letter of every word in a sentence."
H = [(["hello world"], "Hello World"), ([""], ""), (["a b c"], "A B C"), (["python"], "Python")]
add("P15", "python", "capitalize_words", "faulty", "logic", R,
    "def cap_words(s):\n    return s.capitalize()\n", "cap_words", H)
add("P16", "python", "capitalize_words", "correct", "-", R,
    'def cap_words(s):\n    return " ".join(w.capitalize() for w in s.split(" "))\n',
    "cap_words", H)

R = "Return the index of a target in a sorted list, or -1 if it is missing."
H = [([[1, 3, 5, 7], 5], 2), ([[1, 3, 5, 7], 7], 3), ([[1, 3, 5, 7], 2], -1), ([[], 1], -1),
     ([[4], 4], 0), ([[1, 3, 5, 7], 1], 0)]
add("P17", "python", "binary_search", "faulty", "logic", R,
    "def bsearch(xs, t):\n    lo, hi = 0, len(xs) - 1\n    while lo < hi:\n"
    "        mid = (lo + hi) // 2\n        if xs[mid] == t:\n            return mid\n"
    "        if xs[mid] < t:\n            lo = mid + 1\n        else:\n            hi = mid - 1\n"
    "    return -1\n", "bsearch", H)
add("P18", "python", "binary_search", "correct", "-", R,
    "def bsearch(xs, t):\n    lo, hi = 0, len(xs) - 1\n    while lo <= hi:\n"
    "        mid = (lo + hi) // 2\n        if xs[mid] == t:\n            return mid\n"
    "        if xs[mid] < t:\n            lo = mid + 1\n        else:\n            hi = mid - 1\n"
    "    return -1\n", "bsearch", H)

R = "Return True if a year is a leap year."
H = [([2000], True), ([1900], False), ([2024], True), ([2023], False), ([2100], False)]
add("P19", "python", "leap_year", "faulty", "logic", R,
    "def leap(y):\n    return y % 4 == 0\n", "leap", H)
add("P20", "python", "leap_year", "correct", "-", R,
    "def leap(y):\n    return (y % 4 == 0 and y % 100 != 0) or y % 400 == 0\n", "leap", H)

R = "Return the average of a list of numbers, or 0 for an empty list."
H = [([[1, 2, 3]], 2.0), ([[]], 0), ([[5]], 5.0), ([[1, 2]], 1.5)]
add("P21", "python", "average", "faulty", "structure", R,
    "def average(xs):\n    return sum(xs) / len(xs)\n", "average", H)
add("P22", "python", "average", "correct", "-", R,
    "def average(xs):\n    if not xs:\n        return 0\n    return sum(xs) / len(xs)\n",
    "average", H)

R = "Return the n-th Fibonacci number, where fib(0) is 0 and fib(1) is 1."
H = [([0], 0), ([1], 1), ([2], 1), ([10], 55), ([7], 13)]
add("P23", "python", "fibonacci", "faulty", "logic", R,
    "def fib(n):\n    a, b = 1, 1\n    for _ in range(n):\n        a, b = b, a + b\n"
    "    return a\n", "fib", H)
add("P24", "python", "fibonacci", "correct", "-", R,
    "def fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n"
    "    return a\n", "fib", H)

R = "Remove all vowels (a, e, i, o, u, in either case) from a string."
H = [(["hello"], "hll"), (["AEIOU"], ""), (["Apple"], "ppl"), ([""], "")]
add("P25", "python", "strip_vowels", "faulty", "logic", R,
    'def strip_vowels(s):\n    return "".join(ch for ch in s if ch not in "aeiou")\n',
    "strip_vowels", H)
add("P26", "python", "strip_vowels", "correct", "-", R,
    'def strip_vowels(s):\n    return "".join(ch for ch in s if ch.lower() not in "aeiou")\n',
    "strip_vowels", H)

R = "Limit a number x so that it lies between lo and hi."
H = [([5, 0, 10], 5), ([-3, 0, 10], 0), ([15, 0, 10], 10), ([0, 0, 10], 0)]
add("P27", "python", "clamp", "faulty", "logic", R,
    "def clamp(x, lo, hi):\n    return min(lo, max(x, hi))\n", "clamp", H)
add("P28", "python", "clamp", "correct", "-", R,
    "def clamp(x, lo, hi):\n    return max(lo, min(x, hi))\n", "clamp", H)

R = "Return the k largest numbers of a list in descending order."
H = [([[3, 1, 2], 2], [3, 2]), ([[5], 1], [5]), ([[1, 2, 3], 0], []), ([[4, 4, 1], 2], [4, 4])]
add("P29", "python", "top_k", "faulty", "logic", R,
    "def top_k(xs, k):\n    return sorted(xs)[:k]\n", "top_k", H)
add("P30", "python", "top_k", "correct", "-", R,
    "def top_k(xs, k):\n    return sorted(xs, reverse=True)[:k]\n", "top_k", H)

R = "Check whether two strings are anagrams of each other."
H = [(["listen", "silent"], True), (["abc", "abd"], False), (["", ""], True), (["a", "b"], False)]
add("P31", "python", "anagram", "faulty", "logic", R,
    "def is_anagram(a, b):\n    return len(a) == len(b)\n", "is_anagram", H)
add("P32", "python", "anagram", "correct", "-", R,
    "def is_anagram(a, b):\n    return sorted(a) == sorted(b)\n", "is_anagram", H)

R = "Return the running total of a list of numbers."
H = [([[1, 2, 3]], [1, 3, 6]), ([[]], []), ([[5]], [5]), ([[2, -1, 4]], [2, 1, 5])]
add("P33", "python", "running_total", "faulty", "logic", R,
    "def running(xs):\n    return [sum(xs)] * len(xs)\n", "running", H)
add("P34", "python", "running_total", "correct", "-", R,
    "def running(xs):\n    out, total = [], 0\n    for x in xs:\n        total += x\n"
    "        out.append(total)\n    return out\n", "running", H)

# --- surface faults inside a template-free family ------------------------------
R = "Return a new list with every number doubled."
H = [([[1, 2, 3]], [2, 4, 6]), ([[]], []), ([[0]], [0]), ([[-1, 5]], [-2, 10])]
add("P35", "python", "double_each", "faulty", "logic", R,
    "def double_each(xs):\n    return [x + 2 for x in xs]\n", "double_each", H)
add("P36", "python", "double_each", "faulty", "syntax", R,
    "def double_each(xs)\n    return [x * 2 for x in xs]\n", "double_each", H)
add("P37", "python", "double_each", "faulty", "naming", R,
    "def double_each(xs):\n    return [x * 2 for x in xss]\n", "double_each", H)
add("P38", "python", "double_each", "faulty", "structure", R,
    "def double_each(xs):\n    out = []\n    for i in range(len(xs) + 1):\n"
    "        out.append(xs[i] * 2)\n    return out\n", "double_each", H)
add("P39", "python", "double_each", "faulty", "resource", R,
    "def double_each(xs):\n    while len(xs) >= 0:\n        pass\n    return xs\n",
    "double_each", H)
add("P40", "python", "double_each", "correct", "-", R,
    "def double_each(xs):\n    return [x * 2 for x in xs]\n", "double_each", H)

R = "Return the square root of a number rounded up to the next whole number."
H = [([16], 4), ([17], 5), ([1], 1), ([0], 0), ([2], 2)]
add("P41", "python", "ceil_sqrt", "faulty", "api", R,
    "import math\n\ndef ceil_sqrt(n):\n    return math.celi(math.sqrt(n))\n", "ceil_sqrt", H)
add("P42", "python", "ceil_sqrt", "correct", "-", R,
    "import math\n\ndef ceil_sqrt(n):\n    return math.ceil(math.sqrt(n))\n", "ceil_sqrt", H)

R = "Count the distinct words in a list of words."
H = [([["a", "b", "a"]], 2), ([[]], 0), ([["x"]], 1), ([["q", "q", "q"]], 1)]
add("P43", "python", "distinct_words", "faulty", "api", R,
    "from collections import Counterr\n\ndef distinct(words):\n    return len(Counterr(words))\n",
    "distinct", H)
add("P44", "python", "distinct_words", "correct", "-", R,
    "def distinct(words):\n    return len(set(words))\n", "distinct", H)

# --- side effect: invisible to output tests, caught by the property check -----
R = "Return a sorted copy of a list without changing the original."
H = [([[3, 1, 2]], [1, 2, 3]), ([[]], []), ([[2, 1]], [1, 2]), ([[5, 4, 3, 1]], [1, 3, 4, 5])]
add("P45", "python", "sorted_copy", "faulty", "side_effect", R,
    "def sorted_copy(xs):\n    xs.sort()\n    return xs\n", "sorted_copy", H,
    hidden_property="args_unchanged")
add("P46", "python", "sorted_copy", "correct", "-", R,
    "def sorted_copy(xs):\n    return sorted(xs)\n", "sorted_copy", H,
    hidden_property="args_unchanged")
# Correct code that mutates a LOCAL copy: must not be flagged.
add("P47", "python", "sorted_copy", "correct", "-", R,
    "def sorted_copy(xs):\n    ys = list(xs)\n    ys.sort()\n    return ys\n",
    "sorted_copy", H, hidden_property="args_unchanged")
