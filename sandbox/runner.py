"""Sandbox runner: executes candidate code against test cases.

This file is standalone (it imports nothing from FactGuard AI) because it is
copied into a temporary working folder and run as a separate process. Usage:

    python runner.py payload.json result.json

payload.json  {"source", "function", "cases", "timeout", "output_type"}
result.json   per-case outcomes plus branch coverage measured with Coverage.py.
"""
import copy
import io
import json
import math
import os
import signal
import sys
import threading
import time
import traceback
import importlib.util

MAX_OUTPUT_CHARS = 10000
MAX_VALUE_CHARS = 2000


class _Timeout(BaseException):
    """Raised by the alarm; BaseException so `except Exception` cannot hide it."""


def _on_alarm(signum, frame):
    raise _Timeout()


class _BoundedBuffer(io.StringIO):
    """stdout/stderr capture that stops growing at MAX_OUTPUT_CHARS."""

    def write(self, text):
        room = MAX_OUTPUT_CHARS - self.tell()
        if room > 0:
            super().write(text[:room])
        return len(text)


def _normalize(value):
    """Turn a result into JSON-friendly data so tuples/lists compare equal."""
    def default(obj):
        if isinstance(obj, (set, frozenset)):
            try:
                return sorted(obj)
            except TypeError:
                return sorted(repr(x) for x in obj)
        return repr(obj)
    try:
        return json.loads(json.dumps(value, default=default))
    except (TypeError, ValueError):
        return repr(value)


def _equal(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
        except (TypeError, ValueError):
            return False
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    return a == b


def _short(value):
    text = json.dumps(value, default=repr) if not isinstance(value, str) else value
    return text if len(text) <= MAX_VALUE_CHARS else text[:MAX_VALUE_CHARS] + "..."


def _exception_info(exc, candidate_path):
    line = None
    for frame in traceback.extract_tb(exc.__traceback__):
        if frame.filename == candidate_path:
            line = frame.lineno
    return {"type": type(exc).__name__, "message": str(exc)[:500], "line": line}


# Linux/macOS use a real alarm signal. Windows has no
# SIGALRM, so there the code runs in a worker thread and a timeout is raised inside
# it. That stops pure-Python loops but not a call stuck inside C code; the engine's
# wall-clock limit still kills the whole process in that case.
HAVE_ALARM = hasattr(signal, "setitimer") and not os.environ.get("FactGuard_THREAD_TIMEOUT")


def _run_with_alarm(seconds, func, *args, **kwargs):
    if HAVE_ALARM:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        try:
            return func(*args, **kwargs)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)

    import ctypes
    box = {}

    def target():
        try:
            box["value"] = func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - handed back to the caller
            box["exc"] = exc

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_ulong(worker.ident), ctypes.py_object(_Timeout))
        worker.join(1)
        raise _Timeout()
    if "exc" in box:
        raise box["exc"]
    return box.get("value")


def main():
    payload_path, result_path = sys.argv[1], sys.argv[2]
    with open(payload_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    workdir = os.path.dirname(os.path.abspath(payload_path))
    candidate_path = os.path.join(workdir, "candidate.py")
    with open(candidate_path, "w", encoding="utf-8") as handle:
        handle.write(payload["source"])

    timeout = float(payload.get("timeout", 5))
    result = {"import_error": None, "cases": [], "coverage": None,
              "stdout": "", "python": sys.version.split()[0]}
    if HAVE_ALARM:
        signal.signal(signal.SIGALRM, _on_alarm)

    import coverage
    cov = coverage.Coverage(branch=True, data_file=None, include=[candidate_path])
    out = _BoundedBuffer()
    started = time.time()
    real_out, real_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = out
    cov.start()
    module = None
    try:
        try:
            spec = importlib.util.spec_from_file_location("candidate", candidate_path)
            module = importlib.util.module_from_spec(spec)
            _run_with_alarm(timeout, spec.loader.exec_module, module)
        except _Timeout:
            result["import_error"] = {"type": "Timeout",
                                      "message": "module-level code timed out", "line": None}
            module = None
        except BaseException as exc:  # noqa: BLE001 - report every failure
            result["import_error"] = _exception_info(exc, candidate_path)
            module = None

        function = getattr(module, payload["function"], None) if module else None
        for case in payload.get("cases", []):
            entry = {"id": case.get("id"), "kind": case.get("kind", "given"),
                     "probe": bool(case.get("probe")), "args": case.get("args", []),
                     "expected": case.get("expected"), "status": "error",
                     "actual": None, "actual_type": None, "exception": None}
            if function is None or not callable(function):
                entry["exception"] = result["import_error"] or {
                    "type": "NameError",
                    "message": f"function '{payload['function']}' is not defined",
                    "line": None}
                result["cases"].append(entry)
                continue
            try:
                call_args = copy.deepcopy(case.get("args", []))
                snapshot = _normalize(call_args)
                value = _run_with_alarm(
                    timeout, function, *call_args, **copy.deepcopy(case.get("kwargs", {})))
                entry["actual_type"] = type(value).__name__
                entry["actual"] = _normalize(value)
                entry["mutated_args"] = _normalize(call_args) != snapshot
                if entry["probe"]:
                    entry["status"] = "ok"
                elif _equal(entry["actual"], _normalize(case.get("expected"))):
                    entry["status"] = "pass"
                else:
                    entry["status"] = "fail"
            except _Timeout:
                entry["status"] = "timeout"
                entry["exception"] = {"type": "Timeout",
                                      "message": f"no result after {timeout} s", "line": None}
            except BaseException as exc:  # noqa: BLE001
                entry["status"] = "error"
                entry["exception"] = _exception_info(exc, candidate_path)
            result["cases"].append(entry)
    finally:
        cov.stop()
        sys.stdout, sys.stderr = real_out, real_err

    result["elapsed"] = round(time.time() - started, 3)
    result["stdout"] = out.getvalue()

    try:
        report_path = os.path.join(workdir, "coverage.json")
        cov.json_report(outfile=report_path, pretty_print=False)
        with open(report_path, encoding="utf-8") as handle:
            files = json.load(handle).get("files", {})
        data = next(iter(files.values()), None)
        if data:
            summary = data["summary"]
            result["coverage"] = {
                "num_statements": summary.get("num_statements", 0),
                "covered_lines": summary.get("covered_lines", 0),
                "num_branches": summary.get("num_branches", 0),
                "covered_branches": summary.get("covered_branches", 0),
                "missing_lines": data.get("missing_lines", []),
                "missing_branches": data.get("missing_branches", []),
            }
    except Exception as exc:  # noqa: BLE001
        result["coverage_error"] = str(exc)

    with open(result_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle)


if __name__ == "__main__":
    main()
