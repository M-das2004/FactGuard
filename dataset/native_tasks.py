"""C, C++ and Java tasks. Same rules as the other task files: hand-written by the
project author (so a seeded bug catalogue, not independent data), labels verified
against hidden tests in tests/test_dataset.py.

Compile-time faults (undeclared name, hallucinated function or method, missing
include, missing semicolon, wrong type, missing return) and run-time faults
(out-of-range reads, divide by zero, integer overflow, infinite loops, deep
recursion) are included next to plain logic bugs.
"""
from .builders import task as _t

TASKS = []


def add(*args, **kwargs):
    TASKS.append(_t(*args, **kwargs))


SUM = "Return the sum of a list of numbers."
H_SUM = [([[1, 2, 3]], 6), ([[]], 0), ([[5]], 5), ([[-1, 1]], 0), ([[10, -3, 4]], 11)]
MAX = "Return the largest number in a list."
H_MAX = [([[3, 1, 2]], 3), ([[-5, -2, -9]], -2), ([[7]], 7), ([[1, 9, 4, 9]], 9)]
VOW = "Count the vowels in a string."
H_VOW = [(["hello"], 2), ([""], 0), (["aeiou"], 5), (["xyz"], 0), (["education"], 5)]
PAL = "Check whether a string is a palindrome."
H_PAL = [(["level"], True), (["abc"], False), ([""], True), (["a"], True), (["abca"], False)]
FACT = "Compute the factorial of a number."
H_FACT = [([0], 1), ([1], 1), ([5], 120), ([3], 6), ([7], 5040)]
ABS = "Return the absolute value of an integer."
H_ABS = [([-3], 3), ([4], 4), ([0], 0), ([-100], 100)]
GCD = "Return the greatest common divisor of two positive integers."
H_GCD = [([12, 18], 6), ([7, 13], 1), ([10, 5], 5), ([9, 9], 9)]
LEN = "Return the length of a string."
H_LEN = [(["abc"], 3), ([""], 0), (["hello world"], 11)]
AVG = "Return the integer average of a list of numbers, or 0 for an empty list."
H_AVG = [([[1, 2, 3]], 2), ([[]], 0), ([[4, 6]], 5), ([[7]], 7)]
SQR = "Return the square of an integer."
H_SQR = [([3], 9), ([-4], 16), ([0], 0), ([46341], 2147488281)]
CONT = "Find all words containing the letter 'a' from a list of words."
H_CONT = [([["apple", "banana", "cat", "dog"]], ["apple", "banana", "cat"]), ([[]], []),
          ([["xyz"]], []), ([["zzza"]], ["zzza"]), ([["bat", "tab"]], ["bat", "tab"])]
ROOT = "Return the square root of a number."
H_ROOT = [([16], 4.0), ([2], 1.4142135623730951), ([0], 0.0)]

# ------------------------------------------------------------------------- C
add("C01", "c", "c_sum", "faulty", "logic", SUM,
    "int total(const int *xs, int n) {\n    int s = 0;\n    for (int i = 1; i < n; i++) s += xs[i];\n    return s;\n}\n",
    "total", H_SUM)
add("C02", "c", "c_sum", "correct", "-", SUM,
    "int total(const int *xs, int n) {\n    int s = 0;\n    for (int i = 0; i < n; i++) s += xs[i];\n    return s;\n}\n",
    "total", H_SUM)
add("C03", "c", "c_sum", "faulty", "structure", SUM,
    "int total(const int *xs, int n) {\n    int s = 0;\n    for (int i = 0; i <= n; i++) s += xs[i];\n    return s;\n}\n",
    "total", H_SUM)
add("C04", "c", "c_sum", "faulty", "naming", SUM,
    "int total(const int *xs, int n) {\n    int s = 0;\n    for (int i = 0; i < n; i++) s += xs[i];\n    return ss;\n}\n",
    "total", H_SUM)
add("C05", "c", "c_sum", "faulty", "syntax", SUM,
    "int total(const int *xs, int n) {\n    int s = 0;\n    for (int i = 0; i < n; i++) s += xs[i]\n    return s;\n}\n",
    "total", H_SUM)
add("C06", "c", "c_sum", "faulty", "resource", SUM,
    "int total(const int *xs, int n) {\n    int s = 0, i = 0;\n    while (i < n) { s += xs[i]; }\n    return s;\n}\n",
    "total", H_SUM)
add("C07", "c", "c_max", "faulty", "logic", MAX,
    "int biggest(const int *xs, int n) {\n    int best = 0;\n    for (int i = 0; i < n; i++) if (xs[i] > best) best = xs[i];\n    return best;\n}\n",
    "biggest", H_MAX)
add("C08", "c", "c_max", "correct", "-", MAX,
    "int biggest(const int *xs, int n) {\n    int best = xs[0];\n    for (int i = 1; i < n; i++) if (xs[i] > best) best = xs[i];\n    return best;\n}\n",
    "biggest", H_MAX)
add("C09", "c", "c_vowels", "faulty", "logic", VOW,
    "int vowels(const char *s) {\n    int c = 0;\n    for (; *s; s++) if (*s=='a'||*s=='e'||*s=='i'||*s=='o') c++;\n    return c;\n}\n",
    "vowels", H_VOW)
add("C10", "c", "c_vowels", "correct", "-", VOW,
    "int vowels(const char *s) {\n    int c = 0;\n    for (; *s; s++) if (*s=='a'||*s=='e'||*s=='i'||*s=='o'||*s=='u') c++;\n    return c;\n}\n",
    "vowels", H_VOW)
add("C11", "c", "c_factorial", "faulty", "logic", FACT,
    "int fact(int n) {\n    int r = 1;\n    for (int i = 1; i < n; i++) r *= i;\n    return r;\n}\n",
    "fact", H_FACT)
add("C12", "c", "c_factorial", "correct", "-", FACT,
    "int fact(int n) {\n    int r = 1;\n    for (int i = 2; i <= n; i++) r *= i;\n    return r;\n}\n",
    "fact", H_FACT)
add("C13", "c", "c_strlen", "faulty", "api", LEN,
    "#include <string.h>\n\nint len(const char *s) {\n    return (int) strlenn(s);\n}\n",
    "len", H_LEN)
add("C14", "c", "c_strlen", "faulty", "api", LEN,
    "int len(const char *s) {\n    return (int) strlen(s);\n}\n", "len", H_LEN)
add("C15", "c", "c_strlen", "correct", "-", LEN,
    "#include <string.h>\n\nint len(const char *s) {\n    return (int) strlen(s);\n}\n",
    "len", H_LEN)
add("C16", "c", "c_abs", "faulty", "logic", ABS,
    "int absval(int x) {\n    return x > 0 ? x : x;\n}\n", "absval", H_ABS)
add("C17", "c", "c_abs", "correct", "-", ABS,
    "int absval(int x) {\n    return x >= 0 ? x : -x;\n}\n", "absval", H_ABS)
add("C18", "c", "c_gcd", "faulty", "logic", GCD,
    "int gcd(int a, int b) {\n    return a < b ? a : b;\n}\n", "gcd", H_GCD)
add("C19", "c", "c_gcd", "correct", "-", GCD,
    "int gcd(int a, int b) {\n    while (b) { int t = a % b; a = b; b = t; }\n    return a;\n}\n",
    "gcd", H_GCD)
add("C20", "c", "c_average", "faulty", "structure", AVG,
    "int average(const int *xs, int n) {\n    int s = 0;\n    for (int i = 0; i < n; i++) s += xs[i];\n    return s / n;\n}\n",
    "average", H_AVG)
add("C21", "c", "c_average", "correct", "-", AVG,
    "int average(const int *xs, int n) {\n    if (n == 0) return 0;\n    int s = 0;\n    for (int i = 0; i < n; i++) s += xs[i];\n    return s / n;\n}\n",
    "average", H_AVG)

# ----------------------------------------------------------------------- C++
add("X01", "cpp", "cpp_sum", "faulty", "logic", SUM,
    "#include <vector>\n\nint total(std::vector<int> xs) {\n    int s = 0;\n    for (size_t i = 1; i < xs.size(); i++) s += xs[i];\n    return s;\n}\n",
    "total", H_SUM)
add("X02", "cpp", "cpp_sum", "correct", "-", SUM,
    "#include <vector>\n\nint total(std::vector<int> xs) {\n    int s = 0;\n    for (int x : xs) s += x;\n    return s;\n}\n",
    "total", H_SUM)
add("X03", "cpp", "cpp_sum", "faulty", "structure", SUM,
    "#include <vector>\n\nint total(std::vector<int> xs) {\n    int s = 0;\n    for (size_t i = 0; i <= xs.size(); i++) s += xs.at(i);\n    return s;\n}\n",
    "total", H_SUM)
add("X04", "cpp", "cpp_sum", "faulty", "naming", SUM,
    "#include <vector>\n\nint total(std::vector<int> xs) {\n    int s = 0;\n    for (int x : xs) s += x;\n    return ss;\n}\n",
    "total", H_SUM)
add("X05", "cpp", "cpp_sum", "faulty", "api", SUM,
    "#include <vector>\n\nint total(std::vector<int> xs) {\n    int s = 0;\n    for (size_t i = 0; i < xs.length(); i++) s += xs[i];\n    return s;\n}\n",
    "total", H_SUM)
add("X06", "cpp", "cpp_sum", "faulty", "syntax", SUM,
    "#include <vector>\n\nint total(std::vector<int> xs) {\n    int s = 0\n    for (int x : xs) s += x;\n    return s;\n}\n",
    "total", H_SUM)
add("X07", "cpp", "cpp_contains", "faulty", "logic", CONT,
    "#include <string>\n#include <vector>\n\nstd::vector<std::string> findWords(std::vector<std::string> words) {\n    std::vector<std::string> out;\n    for (auto &w : words)\n        if (!w.empty() && w[0] == 'a') out.push_back(w);\n    return out;\n}\n",
    "findWords", H_CONT)
add("X08", "cpp", "cpp_contains", "correct", "-", CONT,
    "#include <string>\n#include <vector>\n\nstd::vector<std::string> findWords(std::vector<std::string> words) {\n    std::vector<std::string> out;\n    for (auto &w : words)\n        if (w.find('a') != std::string::npos) out.push_back(w);\n    return out;\n}\n",
    "findWords", H_CONT)
add("X09", "cpp", "cpp_palindrome", "faulty", "structure", PAL,
    "#include <string>\n\nbool isPal(std::string s) {\n    return s[0] == s[s.size() - 1];\n}\n",
    "isPal", H_PAL)
add("X10", "cpp", "cpp_palindrome", "correct", "-", PAL,
    "#include <string>\n#include <algorithm>\n\nbool isPal(std::string s) {\n    std::string r = s;\n    std::reverse(r.begin(), r.end());\n    return r == s;\n}\n",
    "isPal", H_PAL)
add("X11", "cpp", "cpp_vowels", "faulty", "logic", VOW,
    "#include <string>\n\nint vowels(std::string s) {\n    int c = 0;\n    for (char ch : s) if (std::string(\"aeio\").find(ch) != std::string::npos) c++;\n    return c;\n}\n",
    "vowels", H_VOW)
add("X12", "cpp", "cpp_vowels", "correct", "-", VOW,
    "#include <string>\n\nint vowels(std::string s) {\n    int c = 0;\n    for (char ch : s) if (std::string(\"aeiou\").find(ch) != std::string::npos) c++;\n    return c;\n}\n",
    "vowels", H_VOW)
add("X13", "cpp", "cpp_max", "faulty", "logic", MAX,
    "#include <vector>\n\nint biggest(std::vector<int> xs) {\n    int best = 0;\n    for (int x : xs) if (x > best) best = x;\n    return best;\n}\n",
    "biggest", H_MAX)
add("X14", "cpp", "cpp_max", "correct", "-", MAX,
    "#include <vector>\n\nint biggest(std::vector<int> xs) {\n    int best = xs[0];\n    for (int x : xs) if (x > best) best = x;\n    return best;\n}\n",
    "biggest", H_MAX)
add("X15", "cpp", "cpp_square", "faulty", "structure", SQR,
    "long long square(int n) {\n    int r = n * n;\n    return r;\n}\n", "square", H_SQR)
add("X16", "cpp", "cpp_square", "correct", "-", SQR,
    "long long square(int n) {\n    long long r = n;\n    return r * r;\n}\n", "square", H_SQR)
add("X17", "cpp", "cpp_factorial", "faulty", "resource", FACT,
    "long long fact(int n) {\n    return n * fact(n - 1);\n}\n", "fact", H_FACT)
add("X18", "cpp", "cpp_factorial", "correct", "-", FACT,
    "long long fact(int n) {\n    return n <= 1 ? 1 : n * fact(n - 1);\n}\n", "fact", H_FACT)

# ---------------------------------------------------------------------- Java
add("J01", "java", "java_sum", "faulty", "logic", SUM,
    "public class Solution {\n    public static int total(int[] xs) {\n        int s = 0;\n        for (int i = 1; i < xs.length; i++) s += xs[i];\n        return s;\n    }\n}\n",
    "total", H_SUM)
add("J02", "java", "java_sum", "correct", "-", SUM,
    "public class Solution {\n    public static int total(int[] xs) {\n        int s = 0;\n        for (int x : xs) s += x;\n        return s;\n    }\n}\n",
    "total", H_SUM)
add("J03", "java", "java_sum", "faulty", "structure", SUM,
    "public class Solution {\n    public static int total(int[] xs) {\n        int s = 0;\n        for (int i = 0; i <= xs.length; i++) s += xs[i];\n        return s;\n    }\n}\n",
    "total", H_SUM)
add("J04", "java", "java_sum", "faulty", "naming", SUM,
    "public class Solution {\n    public static int total(int[] xs) {\n        int s = 0;\n        for (int x : xs) s += x;\n        return ss;\n    }\n}\n",
    "total", H_SUM)
add("J05", "java", "java_sum", "faulty", "data", SUM,
    "public class Solution {\n    public static int total(int[] xs) {\n        double s = 0;\n        for (int x : xs) s += x;\n        return s;\n    }\n}\n",
    "total", H_SUM)
add("J06", "java", "java_sum", "faulty", "syntax", SUM,
    "public class Solution {\n    public static int total(int[] xs) {\n        int s = 0;\n        for (int x : xs) s += x\n        return s;\n    }\n}\n",
    "total", H_SUM)
add("J07", "java", "java_root", "faulty", "api", ROOT,
    "public class Solution {\n    public static double root(double n) {\n        return Math.sqroot(n);\n    }\n}\n",
    "root", H_ROOT)
add("J08", "java", "java_root", "correct", "-", ROOT,
    "public class Solution {\n    public static double root(double n) {\n        return Math.sqrt(n);\n    }\n}\n",
    "root", H_ROOT)
add("J09", "java", "java_contains", "faulty", "logic", CONT,
    'import java.util.*;\n\npublic class Solution {\n    public static List<String> findWords(List<String> words) {\n        List<String> out = new ArrayList<>();\n        for (String w : words) if (w.startsWith("a")) out.add(w);\n        return out;\n    }\n}\n',
    "findWords", H_CONT)
add("J10", "java", "java_contains", "correct", "-", CONT,
    'import java.util.*;\n\npublic class Solution {\n    public static List<String> findWords(List<String> words) {\n        List<String> out = new ArrayList<>();\n        for (String w : words) if (w.contains("a")) out.add(w);\n        return out;\n    }\n}\n',
    "findWords", H_CONT)
add("J11", "java", "java_palindrome", "faulty", "structure", PAL,
    "public class Solution {\n    public static boolean isPal(String s) {\n        return s.charAt(0) == s.charAt(s.length() - 1);\n    }\n}\n",
    "isPal", H_PAL)
add("J12", "java", "java_palindrome", "correct", "-", PAL,
    "public class Solution {\n    public static boolean isPal(String s) {\n        return new StringBuilder(s).reverse().toString().equals(s);\n    }\n}\n",
    "isPal", H_PAL)
add("J13", "java", "java_vowels", "faulty", "logic", VOW,
    'public class Solution {\n    public static int vowels(String s) {\n        int c = 0;\n        for (char ch : s.toCharArray()) if ("aeio".indexOf(ch) >= 0) c++;\n        return c;\n    }\n}\n',
    "vowels", H_VOW)
add("J14", "java", "java_vowels", "correct", "-", VOW,
    'public class Solution {\n    public static int vowels(String s) {\n        int c = 0;\n        for (char ch : s.toCharArray()) if ("aeiou".indexOf(ch) >= 0) c++;\n        return c;\n    }\n}\n',
    "vowels", H_VOW)
add("J15", "java", "java_max", "faulty", "logic", MAX,
    "public class Solution {\n    public static int biggest(int[] xs) {\n        int best = 0;\n        for (int x : xs) if (x > best) best = x;\n        return best;\n    }\n}\n",
    "biggest", H_MAX)
add("J16", "java", "java_max", "correct", "-", MAX,
    "public class Solution {\n    public static int biggest(int[] xs) {\n        int best = xs[0];\n        for (int x : xs) if (x > best) best = x;\n        return best;\n    }\n}\n",
    "biggest", H_MAX)
add("J17", "java", "java_factorial", "faulty", "structure", FACT,
    "public class Solution {\n    public static int fact(int n) {\n        if (n > 1) return n * fact(n - 1);\n    }\n}\n",
    "fact", H_FACT)
add("J18", "java", "java_factorial", "faulty", "resource", FACT,
    "public class Solution {\n    public static int fact(int n) {\n        return n * fact(n - 1);\n    }\n}\n",
    "fact", H_FACT)
add("J19", "java", "java_factorial", "correct", "-", FACT,
    "public class Solution {\n    public static int fact(int n) {\n        return n <= 1 ? 1 : n * fact(n - 1);\n    }\n}\n",
    "fact", H_FACT)
add("J20", "java", "java_length", "faulty", "structure", LEN,
    'public class Solution {\n    public static int len(String s) {\n        String t = s.isEmpty() ? null : s;\n        return t.length();\n    }\n}\n',
    "len", H_LEN)
add("J21", "java", "java_length", "correct", "-", LEN,
    "public class Solution {\n    public static int len(String s) {\n        return s.length();\n    }\n}\n",
    "len", H_LEN)
