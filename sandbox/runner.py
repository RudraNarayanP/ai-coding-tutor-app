"""Sandbox runner executed inside the Docker container or local environment.

Supports Python, Java, C++, SQL, JavaScript, and TypeScript test execution:
- Python: Uses exec() and unittest / stdout runner.
- Java: Compiles student code with javac, runs test harnesses or stdout matching.
- C++: Compiles student code with g++ -std=c++20, runs binary test harnesses or stdout matching.
- SQL: Executes queries against seeded SQLite database, returns result tables & asserts output/state.
- JavaScript: Runs student code with Node.js, executes test assertions.
- TypeScript: Runs student TypeScript code with Node.js (--experimental-strip-types).
"""

import contextlib
import io
import json
import os
import re
import sqlite3
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


def run_python_preview(code: str) -> dict:
    """Execute student code and return stdout/stderr without running tests."""
    ns: dict = {"__name__": "__main__"}
    stdout, stderr, error = exec_student_code(code, ns)
    if error is None and not stdout.strip():
        var_lines: list[str] = []
        for name, val in sorted(ns.items()):
            if name.startswith("_") or name == "__builtins__":
                continue
            if callable(val):
                continue
            try:
                var_lines.append(f"{name} = {repr(val)}")
            except Exception:  # noqa: BLE001
                var_lines.append(f"{name} = <{type(val).__name__}>")
        if var_lines:
            stdout = "\n".join(var_lines)
    return {
        "name": "preview",
        "passed": error is None,
        "error": error,
        "stdout": stdout,
        "stderr": stderr,
        "execution_time_ms": 0,
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
# SQL Runner (SQLite In-Memory with Seeded Fixtures)
# ---------------------------------------------------------------------------

def seed_sqlite_database(conn: sqlite3.Connection) -> None:
    """Populates standard Patchwork seed datasets into the SQLite database."""
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            email TEXT NOT NULL,
            created_at TEXT NOT NULL,
            role TEXT NOT NULL
        );

        INSERT INTO users (id, username, email, created_at, role) VALUES
            (1, 'alice_dev', 'alice@example.com', '2024-01-10', 'admin'),
            (2, 'bob_coder', 'bob@example.com', '2024-01-15', 'developer'),
            (3, 'charlie_data', 'charlie@example.com', '2024-02-01', 'analyst'),
            (4, 'diana_ai', 'diana@example.com', '2024-02-10', 'developer');

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            country TEXT NOT NULL
        );

        INSERT INTO customers (id, name, email, country) VALUES
            (1, 'Alice Smith', 'alice@smith.org', 'USA'),
            (2, 'Bob Jones', 'bob@jones.ca', 'Canada'),
            (3, 'Carol Danvers', 'carol@marvel.com', 'USA'),
            (4, 'David Beckham', 'david@england.uk', 'UK');

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL
        );

        INSERT INTO products (id, name, category, price, stock) VALUES
            (1, 'Laptop Pro', 'Electronics', 1299.99, 15),
            (2, 'Mechanical Keyboard', 'Electronics', 99.50, 45),
            (3, 'Ergonomic Chair', 'Furniture', 299.00, 10),
            (4, 'Coffee Mug', 'Kitchen', 12.99, 100),
            (5, 'Monitor 27-inch', 'Electronics', 350.00, 8);

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            order_date TEXT NOT NULL,
            total_amount REAL NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        INSERT INTO orders (id, customer_id, product_id, quantity, order_date, total_amount) VALUES
            (101, 1, 1, 1, '2024-03-01', 1299.99),
            (102, 1, 2, 2, '2024-03-02', 199.00),
            (103, 2, 3, 1, '2024-03-02', 299.00),
            (104, 3, 4, 4, '2024-03-05', 51.96),
            (105, 1, 4, 1, '2024-03-06', 12.99),
            (106, 2, 2, 1, '2024-03-07', 99.50);

        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            department TEXT NOT NULL,
            salary REAL NOT NULL
        );

        INSERT INTO employees (id, first_name, last_name, department, salary) VALUES
            (1, 'John', 'Doe', 'Engineering', 95000.00),
            (2, 'Jane', 'Smith', 'Engineering', 105000.00),
            (3, 'Sam', 'Wilson', 'Marketing', 65000.00),
            (4, 'Sarah', 'Connor', 'Security', 88000.00),
            (5, 'Mike', 'Ross', 'Legal', 92000.00);

        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL
        );

        INSERT INTO courses (id, title, category, price) VALUES
            (1, 'Python Fundamentals', 'Programming', 0.00),
            (2, 'SQL & Databases', 'Data', 0.00),
            (3, 'C++ Performance', 'Systems', 0.00),
            (4, 'TypeScript Architecture', 'Web', 0.00);

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );

        INSERT INTO transactions (id, user_id, amount, status, timestamp) VALUES
            (1, 1, 50.00, 'completed', '2024-03-01 10:00:00'),
            (2, 2, 120.00, 'completed', '2024-03-01 11:30:00'),
            (3, 1, 15.50, 'pending', '2024-03-02 09:15:00'),
            (4, 3, 200.00, 'failed', '2024-03-02 14:20:00');
    """)
    conn.commit()


def format_sql_result_table(columns: list[str], rows: list[tuple]) -> str:
    """Formats SQL columns and rows into a clean ASCII table."""
    if not columns:
        return ""
    col_widths = [len(str(c)) for c in columns]
    for row in rows:
        for idx, val in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(str(val if val is not None else "NULL")))

    header = " │ ".join(str(col).ljust(col_widths[i]) for i, col in enumerate(columns))
    divider = "─┼─".join("─" * col_widths[i] for i in range(len(columns)))

    formatted_rows = []
    for row in rows:
        row_str = " │ ".join(
            str(val if val is not None else "NULL").ljust(col_widths[i])
            for i, val in enumerate(row)
        )
        formatted_rows.append(f"│ {row_str} │")

    top_border = "┌─" + "─┬─".join("─" * col_widths[i] for i in range(len(columns))) + "─┐"
    mid_border = "├─" + divider + "─┤"
    bot_border = "└─" + "─┴─".join("─" * col_widths[i] for i in range(len(columns))) + "─┘"

    table_lines = [top_border, f"│ {header} │", mid_border] + formatted_rows + [bot_border]
    return "\n".join(table_lines)


def run_sql_tests(code: str, tests: list[dict]) -> list[dict]:
    results = []

    for test in tests or [{"name": "sql_execution"}]:
        started = time.perf_counter()
        conn = sqlite3.connect(":memory:")
        try:
            seed_sqlite_database(conn)
            cursor = conn.cursor()

            # Execute student query/queries
            statements = [s.strip() for s in code.split(";") if s.strip()]
            columns = []
            rows = []
            last_exec_err = None

            for stmt in statements:
                try:
                    cursor.execute(stmt)
                    if cursor.description:
                        columns = [col[0] for col in cursor.description]
                        rows = cursor.fetchall()
                except Exception as exc:
                    last_exec_err = str(exc)
                    break

            conn.commit()

            table_output = format_sql_result_table(columns, rows) if columns else ""
            elapsed = round((time.perf_counter() - started) * 1000)

            if last_exec_err:
                results.append({
                    "name": test["name"],
                    "passed": False,
                    "error": f"SQL Error: {last_exec_err}",
                    "execution_time_ms": elapsed,
                    "stdout": "",
                    "stderr": last_exec_err,
                })
                conn.close()
                continue

            test_code = test.get("test_code") or test.get("unittest_code")
            expected_stdout = test.get("expected_stdout")
            passed = True
            error_msg = None

            if test_code:
                # Run assertion SQL or Python check
                try:
                    if test_code.strip().lower().startswith("select"):
                        cursor.execute(test_code)
                        res = cursor.fetchall()
                        passed = bool(res and res[0][0])
                        if not passed:
                            error_msg = "Test SQL check failed."
                    else:
                        ns = {"conn": conn, "cursor": cursor, "rows": rows, "columns": columns, "assert": assert_fn}
                        exec(compile(test_code, "test_check.py", "exec"), ns, ns)
                except Exception as exc:
                    passed = False
                    error_msg = f"Check failed: {exc}"
            elif expected_stdout is not None:
                passed = (table_output.strip() == expected_stdout.strip())
                if not passed:
                    error_msg = f"Expected result table:\n{expected_stdout}\n\nGot:\n{table_output}"

            results.append({
                "name": test["name"],
                "passed": passed,
                "error": error_msg,
                "execution_time_ms": elapsed,
                "stdout": table_output,
                "stderr": "",
            })

        except Exception as exc:
            elapsed = round((time.perf_counter() - started) * 1000)
            results.append({
                "name": test["name"],
                "passed": False,
                "error": f"Database error: {exc}",
                "execution_time_ms": elapsed,
                "stdout": "",
                "stderr": str(exc),
            })
        finally:
            conn.close()

    return results


def assert_fn(cond: bool, msg: str = "Assertion failed"):
    if not cond:
        raise AssertionError(msg)


# ---------------------------------------------------------------------------
# JavaScript & TypeScript Runner (Node.js)
# ---------------------------------------------------------------------------

def run_js_ts_tests(language: str, code: str, tests: list[dict]) -> list[dict]:
    results = []
    is_ts = language.lower() in ("typescript", "ts")

    with tempfile.TemporaryDirectory(prefix=f"patchwork_{language}_") as tmpdir:
        ext = ".ts" if is_ts else ".js"
        student_file = os.path.join(tmpdir, f"solution{ext}")
        with open(student_file, "w", encoding="utf-8") as f:
            f.write(code)

        for test in tests or [{"name": "js_ts_execution"}]:
            started = time.perf_counter()
            test_body = test.get("test_code") or test.get("unittest_code")
            runner_file = os.path.join(tmpdir, f"test_{test['name']}{ext}")

            if test_body:
                full_test_src = f"""
const solution = require('./solution${ext}');
try {{
    {test_body}
    console.log("TEST_PASSED");
}} catch (err) {{
    console.error(err && err.message ? err.message : String(err));
    process.exit(1);
}}
"""
                # Handle ES module vs CommonJS export fallback
                if "export " in code or "import " in code:
                    full_test_src = f"""
import * as solution from './solution${ext}';
import { assert_fn } from 'node:assert';
try {{
    {test_body}
    console.log("TEST_PASSED");
}} catch (err) {{
    console.error(err && err.message ? err.message : String(err));
    process.exit(1);
}}
"""
            else:
                full_test_src = code

            with open(runner_file, "w", encoding="utf-8") as f:
                f.write(full_test_src)

            cmd = ["node"]
            if is_ts:
                cmd.append("--experimental-strip-types")
            cmd.append(runner_file)

            try:
                exec_res = subprocess.run(
                    cmd,
                    cwd=tmpdir,
                    input=test.get("stdin", ""),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                elapsed = round((time.perf_counter() - started) * 1000)

                if test_body:
                    passed = (exec_res.returncode == 0)
                    error_msg = None if passed else (exec_res.stderr.strip() or "Test failed")
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
                    passed = (expected is None or exec_res.stdout == expected)
                    error_msg = None if passed else f"Expected output {expected!r}, got {exec_res.stdout!r}"
                    results.append({
                        "name": test["name"],
                        "passed": passed,
                        "error": error_msg,
                        "execution_time_ms": elapsed,
                        "stdout": exec_res.stdout,
                        "stderr": exec_res.stderr,
                    })
            except subprocess.TimeoutExpired:
                elapsed = round((time.perf_counter() - started) * 1000)
                results.append({
                    "name": test["name"],
                    "passed": False,
                    "error": "Execution timed out (5s limit)",
                    "execution_time_ms": elapsed,
                    "stdout": "",
                    "stderr": "TimeoutExpired",
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
    elif lang in ("sql", "sqlite"):
        return run_sql_tests(code, tests)
    elif lang in ("javascript", "js", "typescript", "ts"):
        return run_js_ts_tests(lang, code, tests)
    else:
        return run_python_tests(code, tests)


def main() -> None:
    try:
        request = json.load(sys.stdin)
        language = request.get("language", "python")
        code = request["code"]
        tests = request.get("tests", [])
        mode = request.get("mode", "test")
        if mode == "preview":
            lang = language.lower().strip()
            if lang in ("python", "py", ""):
                preview = run_python_preview(code)
            else:
                preview = {
                    "name": "preview",
                    "passed": False,
                    "error": f"Preview run is not supported for {language}.",
                    "stdout": "",
                    "stderr": "",
                    "execution_time_ms": 0,
                }
            print(json.dumps({
                "passed": preview["passed"],
                "tests": [preview],
                "stdout": preview.get("stdout", ""),
                "stderr": preview.get("stderr", ""),
                "error": preview.get("error"),
            }))
            return
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
