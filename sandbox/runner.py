"""Sandbox runner executed inside the Docker container.

Supports two test modes, dispatched by the presence of the ``unittest_code`` key
in each test descriptor:

stdout mode (legacy)
    The student's code is exec'd; its stdout is compared against ``expected_stdout``.

unittest mode (Exercism-style)
    The student's code is exec'd into a shared namespace, then each test method body
    is assembled into a ``unittest.TestCase`` subclass and run individually.  This
    lets every test method report independently while sharing a single execution of
    the student's module-level code.
"""

import contextlib
import io
import json
import sys
import textwrap
import time
import traceback
import unittest

MAX_OUTPUT_BYTES = 64 * 1024


# ---------------------------------------------------------------------------
# Output limiting
# ---------------------------------------------------------------------------

class LimitedWriter(io.TextIOBase):
    def __init__(self) -> None:
        self.buffer = io.StringIO()
        self.size = 0

    def write(self, value: str) -> int:
        encoded_size = len(value.encode("utf-8", errors="replace"))
        if self.size + encoded_size > MAX_OUTPUT_BYTES:
            raise OutputLimitExceeded
        self.size += encoded_size
        return self.buffer.write(value)

    def getvalue(self) -> str:
        return self.buffer.getvalue()


class OutputLimitExceeded(Exception):
    pass


@contextlib.contextmanager
def redirect_stdin(stream: io.TextIOBase):
    original = sys.stdin
    sys.stdin = stream
    try:
        yield
    finally:
        sys.stdin = original


# ---------------------------------------------------------------------------
# Shared student-code execution
# ---------------------------------------------------------------------------

def exec_student_code(code: str, namespace: dict) -> tuple[str, str, str | None]:
    """Execute student code once into *namespace*.

    Returns (stdout_str, stderr_str, error_str | None).
    error_str is None on clean execution, otherwise a short error description.
    """
    stdout_cap = LimitedWriter()
    stderr_cap = LimitedWriter()
    error = None
    try:
        with (contextlib.redirect_stdout(stdout_cap),
              contextlib.redirect_stderr(stderr_cap),
              redirect_stdin(io.StringIO(""))):
            exec(compile(code, "student_code.py", "exec"), namespace, namespace)  # noqa: S102
    except OutputLimitExceeded:
        error = "Output exceeded the 64 KiB limit."
    except SyntaxError as exc:
        error = f"SyntaxError: {exc.msg} (line {exc.lineno})"
    except BaseException as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    return stdout_cap.getvalue(), stderr_cap.getvalue(), error


# ---------------------------------------------------------------------------
# stdout mode
# ---------------------------------------------------------------------------

def run_stdout_test(code: str, test: dict) -> dict:
    """Run one stdout-matching test."""
    stdout_cap = LimitedWriter()
    stderr_cap = LimitedWriter()
    started = time.perf_counter()
    namespace: dict = {"__name__": "__main__"}
    input_text = test.get("stdin", "")
    try:
        with (contextlib.redirect_stdout(stdout_cap),
              contextlib.redirect_stderr(stderr_cap),
              redirect_stdin(io.StringIO(input_text))):
            exec(compile(code, "student_code.py", "exec"), namespace, namespace)  # noqa: S102
        actual = stdout_cap.getvalue()
        expected = test.get("expected_stdout")
        passed = expected is None or actual == expected
        error = None if passed else f"Expected output {expected!r}, got {actual!r}"
    except OutputLimitExceeded:
        actual = stdout_cap.getvalue()
        error = "Output exceeded the 64 KiB limit."
        passed = False
    except SyntaxError as exc:
        actual = stdout_cap.getvalue()
        error = f"SyntaxError: {exc.msg} (line {exc.lineno})"
        passed = False
    except BaseException as exc:  # noqa: BLE001
        actual = stdout_cap.getvalue()
        error = f"{type(exc).__name__}: {exc}"
        passed = False
    elapsed = round((time.perf_counter() - started) * 1000)
    return {
        "name": test["name"],
        "passed": passed,
        "error": error,
        "execution_time_ms": elapsed,
        "stdout": actual,
        "stderr": stderr_cap.getvalue(),
    }


# ---------------------------------------------------------------------------
# unittest mode
# ---------------------------------------------------------------------------

def run_unittest_test(student_code: str, student_ns: dict, exec_error: str | None, test: dict) -> dict:
    """Run one unittest method body against the pre-executed student namespace.

    *student_ns* is the namespace produced by running the student's code once.
    *exec_error* is non-None if the student code itself raised an exception.
    """
    started = time.perf_counter()
    name = test["name"]

    # If the student code failed to execute, every test in this lesson fails.
    if exec_error is not None:
        elapsed = round((time.perf_counter() - started) * 1000)
        return {
            "name": name,
            "passed": False,
            "error": exec_error,
            "execution_time_ms": elapsed,
            "stdout": "",
            "stderr": "",
        }

    method_body = test["unittest_code"]

    # Handle curriculum files that include the full method definition vs just the body
    # If the unittest_code starts with "def", extract just the body
    dedented = textwrap.dedent(method_body).strip()
    if dedented.startswith("def "):
        # Extract the body by removing the function definition line and dedenting
        lines = dedented.split("\n")
        # Find the first line that's not the def line (after the colon)
        body_lines = []
        in_def = True
        for line in lines:
            if in_def:
                if ":" in line:
                    in_def = False
                continue
            body_lines.append(line)
        # Dedent the extracted body to remove the original indentation
        method_body = textwrap.dedent("\n".join(body_lines)).strip()
    
    # Build a TestCase class dynamically.  We indent the method body by 8 spaces
    # so it sits inside the class/method correctly regardless of the source indentation.
    indented_body = textwrap.indent(method_body, "        ")
    class_src = (
        "import unittest\n"
        "from copy import deepcopy\n"
        f"class _StudentTest(unittest.TestCase):\n"
        f"    def {name}(self):\n"
        f"{indented_body}\n"
    )

    # The test class lives in a namespace that includes everything the student defined.
    test_ns: dict = dict(student_ns)
    try:
        exec(compile(class_src, f"test_{name}.py", "exec"), test_ns, test_ns)  # noqa: S102
    except Exception as exc:  # noqa: BLE001
        elapsed = round((time.perf_counter() - started) * 1000)
        return {
            "name": name,
            "passed": False,
            "error": f"Test compilation error: {type(exc).__name__}: {exc}",
            "execution_time_ms": elapsed,
            "stdout": "",
            "stderr": "",
        }

    test_class = test_ns["_StudentTest"]
    suite = unittest.TestLoader().loadTestsFromName(name, test_class)

    stdout_cap = LimitedWriter()
    stderr_cap = LimitedWriter()
    passed = False
    error_msg = None
    try:
        with (contextlib.redirect_stdout(stdout_cap),
              contextlib.redirect_stderr(stderr_cap)):
            runner = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0)
            result = runner.run(suite)
        passed = result.wasSuccessful()
        if not passed:
            failures = result.failures + result.errors
            if failures:
                # Extract just the assertion message, not the full traceback
                raw = failures[0][1]
                # Try to get the last AssertionError line
                lines = raw.strip().splitlines()
                # Find the actual assertion message (last non-empty line)
                msg_lines = [l for l in lines if l.strip() and not l.startswith(" ")]
                error_msg = lines[-1].strip() if lines else raw[:500]
    except OutputLimitExceeded:
        error_msg = "Output exceeded the 64 KiB limit."
    except Exception as exc:  # noqa: BLE001
        error_msg = f"{type(exc).__name__}: {exc}"

    elapsed = round((time.perf_counter() - started) * 1000)
    return {
        "name": name,
        "passed": passed,
        "error": error_msg,
        "execution_time_ms": elapsed,
        "stdout": stdout_cap.getvalue(),
        "stderr": stderr_cap.getvalue(),
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def run_test(code: str, test: dict) -> dict:
    """Dispatch to the appropriate test runner based on test type."""
    if test.get("unittest_code") is not None:
        # Caller must supply a pre-executed namespace; this path is used
        # when called directly (not via run_all_tests).
        ns: dict = {"__name__": "__main__"}
        _, _, exec_error = exec_student_code(code, ns)
        return run_unittest_test(code, ns, exec_error, test)
    return run_stdout_test(code, test)


def run_all_tests(code: str, tests: list[dict]) -> list[dict]:
    """Run all tests, executing student code only once for unittest-mode lessons."""
    if not tests:
        return []

    has_unittest = any(t.get("unittest_code") is not None for t in tests)
    has_stdout = any(t.get("unittest_code") is None for t in tests)

    if has_unittest and has_stdout:
        # Mixed-mode lesson: run each test independently
        return [run_test(code, t) for t in tests]

    if has_unittest:
        # Execute student code once, share namespace across all tests
        ns: dict = {"__name__": "__main__"}
        _, _, exec_error = exec_student_code(code, ns)
        return [run_unittest_test(code, ns, exec_error, t) for t in tests]

    # All stdout mode: each test reruns the code (existing behaviour)
    return [run_stdout_test(code, t) for t in tests]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        request = json.load(sys.stdin)
        code = request["code"]
        tests = request["tests"]
        results = run_all_tests(code, tests)
        all_stdout = "\n".join(r["stdout"] for r in results if r["stdout"])
        all_stderr = "\n".join(r["stderr"] for r in results if r["stderr"])
        print(json.dumps({
            "passed": bool(results) and all(r["passed"] for r in results),
            "tests": results,
            "stdout": all_stdout[:MAX_OUTPUT_BYTES],
            "stderr": all_stderr[:MAX_OUTPUT_BYTES],
        }))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "passed": False,
            "tests": [],
            "stdout": "",
            "stderr": f"Sandbox runner failure: {type(exc).__name__}: {exc}",
        }))
        sys.exit(2)


if __name__ == "__main__":
    main()
