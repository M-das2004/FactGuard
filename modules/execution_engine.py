"""Execution Engine: run candidate code and tests in a local subprocess.

Code runs in a plain subprocess with resource limits (CPU time, file size and,
for Python, memory on Linux/macOS). This is NOT a security sandbox: use it only
for trusted sample programs or code you wrote yourself. The caller must pass
allow_local=True, otherwise nothing is executed.

Languages: Python runs through sandbox/runner.py. C, C++ and Java run through
sandbox/native_runner.py, which also compiles the code. Compiling and running
untrusted C/C++/Java is more dangerous than running Python, so limit it to code
you wrote yourself.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:  # not available on Windows
    import resource
except ImportError:
    resource = None

SANDBOX_DIR = Path(__file__).resolve().parent.parent / "sandbox"
RUNNER_SOURCE = SANDBOX_DIR / "runner.py"
NATIVE_RUNNER_SOURCE = SANDBOX_DIR / "native_runner.py"
MAX_CAPTURE = 20000
NATIVE = ("c", "cpp", "java")
TOOLS = {"c": ("gcc",), "cpp": ("g++",), "java": ("javac", "java")}


class SandboxUnavailable(RuntimeError):
    """Local execution was not allowed by the caller."""


def missing_tools(language):
    """Compilers a language needs that are not installed on this machine."""
    return [tool for tool in TOOLS.get(language, ()) if not shutil.which(tool)]


def _limits(budget, native=False):
    """Resource limits (Linux/macOS only; Windows has none).

    Native toolchains need a large address space (the JVM and AddressSanitizer
    reserve a lot of virtual memory), so only CPU time and file size are capped there.
    """
    if os.name != "posix" or resource is None:
        return None

    def apply():
        os.setsid()
        resource.setrlimit(resource.RLIMIT_CPU, (int(budget) + 2, int(budget) + 2))
        if not native:
            resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
    return apply


def _budget(timeout, n_cases, native=False):
    """Whole-run time budget: one per-case timeout for every case, plus headroom
    (native code also needs time to compile)."""
    return timeout * (n_cases + 1) + (150 if native else 5)


def _run_local(workdir, budget, language):
    native = language in NATIVE
    runner = "native_runner.py" if native else "runner.py"
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}  # no secrets
    if os.name == "nt":  # Python on Windows needs these to start
        for name in ("SYSTEMROOT", "TEMP", "TMP"):
            if name in os.environ:
                env[name] = os.environ[name]
    try:
        done = subprocess.run(
            [sys.executable, "-I", os.path.join(workdir, runner),
             os.path.join(workdir, "payload.json"), os.path.join(workdir, "result.json")],
            capture_output=True, text=True, timeout=budget + 10,
            cwd=workdir, env=env, preexec_fn=_limits(budget, native))
        return done.returncode, done.stdout[:MAX_CAPTURE], done.stderr[:MAX_CAPTURE]
    except subprocess.TimeoutExpired:
        return -9, "", "wall-clock timeout: process was stopped"


def run_in_sandbox(source, function, cases, *, timeout=5, allow_local=False, language="python", stop_on_fail=False):
    """Execute `cases` against `function` defined in `source`.

    Returns the runner's result dictionary extended with:
      "sandbox"  - always "local (NOT isolated)"
      "ok"       - False when the runner itself failed
      "runner_error" - message when ok is False
    C, C++ and Java results also carry "compile_ok", "diagnostics" and "unsupported".
    `stop_on_fail=True` (native only) stops at the first failing test, which makes
    repair checking and mutation scoring much faster.
    """
    native = language in NATIVE
    if not allow_local:
        raise SandboxUnavailable(
            "Local execution is not allowed. Enable it to run code on this "
            "computer (trusted sample programs only).")
    if native:
        missing = missing_tools(language)
        if missing:
            return {"ok": False, "sandbox": "local (NOT isolated)", "cases": [],
                    "coverage": None, "import_error": None, "stdout": "",
                    "runner_error": ("Missing on this computer: " + ", ".join(missing)
                                     + ". Install it to check " + language + " code.")}

    workdir = tempfile.mkdtemp(prefix="FactGuard_")
    try:
        shutil.copy(NATIVE_RUNNER_SOURCE if native else RUNNER_SOURCE,
                    os.path.join(workdir, "native_runner.py" if native else "runner.py"))
        payload = {"source": source, "function": function, "cases": cases,
                   "timeout": timeout}
        if native:
            payload.update(language=language, stop_on_fail=stop_on_fail)
        with open(os.path.join(workdir, "payload.json"), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

        budget = _budget(timeout, len(cases), native)
        code, out, err = _run_local(workdir, budget, language)
        label = "local (NOT isolated)"

        result_path = os.path.join(workdir, "result.json")
        if os.path.exists(result_path):
            with open(result_path, encoding="utf-8") as fh:
                result = json.load(fh)
            result.update({"ok": True, "sandbox": label})
            return result
        return {"ok": False, "sandbox": label, "cases": [], "coverage": None,
                "import_error": None, "stdout": out,
                "runner_error": (err or f"runner exited with code {code}").strip()}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)  # always clean up
