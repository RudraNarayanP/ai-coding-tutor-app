"""Sandbox runner executed inside the Docker container or local environment.

Supports Python, Java, and C++ test execution:
- Python: Uses exec() and unittest / stdout runner.
- Java: Compiles student code with javac, runs test harnesses or stdout matching.
- C++: Compiles student code with g++ -std=c++20, runs binary test harnesses or stdout matching.
"""

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time

MAX_OUTPUT_BYTES = 64 * 1024


# ---------------------------------------------------------------------------
# Output limiting for Python
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
# Python Runner
# ---------------------------------------------------------------------------

def exec_student_code(code: str, namespace: dict) -> tuple[str, str, str | None]:
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


def run_python_stdout_test(code: str, test: dict) -> dict:
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


def run_python_unittest_test(student_code: str, student_ns: dict, exec_error: str | None, test: dict) -> dict:
    import unittest
    started = time.perf_counter()
    name = test["name"]

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

    method_body = test.get("unittest_code") or test.get("test_code") or ""
    dedented = textwrap.dedent(method_body).strip()
    if dedented.startswith("def "):
        lines = dedented.split("\n")
        body_lines = []
        in_def = True
        for line in lines:
            if in_def:
                if ":" in line:
                    in_def = False
                continue
            body_lines.append(line)
        method_body = textwrap.dedent("\n".join(body_lines)).strip()
    
    indented_body = textwrap.indent(method_body, "        ")
    class_src = (
        "import unittest\n"
        "from copy import deepcopy\n"
        f"class _StudentTest(unittest.TestCase):\n"
        f"    def {name}(self):\n"
        f"{indented_body}\n"
    )

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
                raw = failures[0][1]
                lines = raw.strip().splitlines()
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


def run_python_tests(code: str, tests: list[dict]) -> list[dict]:
    if not tests:
        return []
    has_unittest = any(t.get("unittest_code") is not None or t.get("test_code") is not None for t in tests)
    has_stdout = any(t.get("unittest_code") is None and t.get("test_code") is None for t in tests)

    if has_unittest and has_stdout:
        ns: dict = {"__name__": "__main__"}
        _, _, exec_error = exec_student_code(code, ns)
        return [
            run_python_unittest_test(code, ns, exec_error, t)
            if (t.get("unittest_code") or t.get("test_code"))
            else run_python_stdout_test(code, t)
            for t in tests
        ]

    if has_unittest:
        ns: dict = {"__name__": "__main__"}
        _, _, exec_error = exec_student_code(code, ns)
        return [run_python_unittest_test(code, ns, exec_error, t) for t in tests]

    return [run_python_stdout_test(code, t) for t in tests]


# ---------------------------------------------------------------------------
# Java Runner
# ---------------------------------------------------------------------------

def extract_java_class_name(code: str) -> str:
    match = re.search(r"public\s+class\s+([A-Za-z0-9_]+)", code)
    if match:
        return match.group(1)
    match_any = re.search(r"class\s+([A-Za-z0-9_]+)", code)
    if match_any:
        return match_any.group(1)
    return "Solution"


def run_java_tests(code: str, tests: list[dict]) -> list[dict]:
    results = []
    class_name = extract_java_class_name(code)

    with tempfile.TemporaryDirectory(prefix="patchwork_java_") as tmpdir:
        student_file = os.path.join(tmpdir, f"{class_name}.java")
        with open(student_file, "w", encoding="utf-8") as f:
            f.write(code)

        compile_res = subprocess.run(
            ["javac", student_file],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if compile_res.returncode != 0:
            err = compile_res.stderr.strip() or "Java Compilation Error"
            return [
                {
                    "name": t["name"],
                    "passed": False,
                    "error": f"Compilation Error: {err[:500]}",
                    "execution_time_ms": 0,
                    "stdout": "",
                    "stderr": err,
                }
                for t in tests
            ]

        for test in tests:
            started = time.perf_counter()
            test_body = test.get("test_code") or test.get("unittest_code")
            if test_body:
                runner_code = f"""
public class TestRunner_{test['name']} {{
    public static void main(String[] args) {{
        try {{
            {test_body}
            System.out.println("TEST_PASSED");
        }} catch (Throwable e) {{
            System.err.println(e.getMessage() != null ? e.getMessage() : e.toString());
            System.exit(1);
        }}
    }}
}}
"""
                runner_file = os.path.join(tmpdir, f"TestRunner_{test['name']}.java")
                with open(runner_file, "w", encoding="utf-8") as f:
                    f.write(runner_code)

                comp_test = subprocess.run(
                    ["javac", runner_file],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if comp_test.returncode != 0:
                    elapsed = round((time.perf_counter() - started) * 1000)
                    results.append({
                        "name": test["name"],
                        "passed": False,
                        "error": f"Test Compilation Error: {comp_test.stderr[:300]}",
                        "execution_time_ms": elapsed,
                        "stdout": "",
                        "stderr": comp_test.stderr,
                    })
                    continue

                exec_res = subprocess.run(
                    ["java", f"TestRunner_{test['name']}"],
                    cwd=tmpdir,
                    input=test.get("stdin", ""),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                elapsed = round((time.perf_counter() - started) * 1000)
                passed = exec_res.returncode == 0
                error_msg = None if passed else (exec_res.stderr.strip() or "Test execution failed")
                results.append({
                    "name": test["name"],
                    "passed": passed,
                    "error": error_msg,
                    "execution_time_ms": elapsed,
                    "stdout": exec_res.stdout,
                    "stderr": exec_res.stderr,
                })
            else:
                exec_res = subprocess.run(
                    ["java", class_name],
                    cwd=tmpdir,
                    input=test.get("stdin", ""),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                elapsed = round((time.perf_counter() - started) * 1000)
                expected = test.get("expected_stdout")
                passed = expected is None or exec_res.stdout == expected
                error_msg = None if passed else f"Expected output {expected!r}, got {exec_res.stdout!r}"
                results.append({
                    "name": test["name"],
                    "passed": passed,
                    "error": error_msg,
                    "execution_time_ms": elapsed,
                    "stdout": exec_res.stdout,
                    "stderr": exec_res.stderr,
                })

    return results


# ---------------------------------------------------------------------------
# C++ Runner
# ---------------------------------------------------------------------------

def run_cpp_tests(code: str, tests: list[dict]) -> list[dict]:
    results = []

    with tempfile.TemporaryDirectory(prefix="patchwork_cpp_") as tmpdir:
        for test in tests:
            started = time.perf_counter()
            test_body = test.get("test_code") or test.get("unittest_code")
            source_file = os.path.join(tmpdir, f"test_{test['name']}.cpp")
            exe_file = os.path.join(tmpdir, f"test_{test['name']}")

            if test_body:
                full_code = f"""
#include <iostream>
#include <string>
#include <vector>
#include <map>
#include <set>
#include <algorithm>
#include <cassert>
#include <cmath>
#include <stdexcept>

{code}

int main() {{
    try {{
        {test_body}
        return 0;
    }} catch (const std::exception& e) {{
        std::cerr << "Exception: " << e.what() << std::endl;
        return 1;
    }} catch (...) {{
        std::cerr << "Unknown exception occurred." << std::endl;
        return 1;
    }}
}}
"""
            else:
                full_code = code

            with open(source_file, "w", encoding="utf-8") as f:
                f.write(full_code)

            comp_res = subprocess.run(
                ["g++", "-std=c++20", "-O0", source_file, "-o", exe_file],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if comp_res.returncode != 0:
                elapsed = round((time.perf_counter() - started) * 1000)
                err = comp_res.stderr.strip() or "C++ Compilation Error"
                results.append({
                    "name": test["name"],
                    "passed": False,
                    "error": f"Compilation Error: {err[:500]}",
                    "execution_time_ms": elapsed,
                    "stdout": "",
                    "stderr": err,
                })
                continue

            exec_res = subprocess.run(
                [exe_file],
                cwd=tmpdir,
                input=test.get("stdin", ""),
                capture_output=True,
                text=True,
                timeout=5,
            )
            elapsed = round((time.perf_counter() - started) * 1000)

            if test_body:
                passed = exec_res.returncode == 0
                error_msg = None if passed else (exec_res.stderr.strip() or "Assertion failed")
                results.append({
                    "name": test["name"],
                    "passed": passed,
                    "error": error_msg,
                    "execution_time_ms": elapsed,
                    "stdout": exec_res.stdout,
                    "stderr": exec_res.stderr,
                })
            else:
                expected = test.get("expected_stdout")
                passed = expected is None or exec_res.stdout == expected
                error_msg = None if passed else f"Expected output {expected!r}, got {exec_res.stdout!r}"
                results.append({
                    "name": test["name"],
                    "passed": passed,
                    "error": error_msg,
                    "execution_time_ms": elapsed,
                    "stdout": exec_res.stdout,
                    "stderr": exec_res.stderr,
                })

    return results


# ---------------------------------------------------------------------------
# Dispatcher & Entry point
# ---------------------------------------------------------------------------

def run_all_tests(language: str, code: str, tests: list[dict]) -> list[dict]:
    lang = (language or "python").lower().strip()
    if lang == "java":
        return run_java_tests(code, tests)
    elif lang in ("cpp", "c++"):
        return run_cpp_tests(code, tests)
    else:
        return run_python_tests(code, tests)


def main() -> None:
    try:
        request = json.load(sys.stdin)
        language = request.get("language", "python")
        code = request["code"]
        tests = request["tests"]
        results = run_all_tests(language, code, tests)
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
