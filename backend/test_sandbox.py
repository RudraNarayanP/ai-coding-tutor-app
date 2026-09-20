import asyncio
import json
import subprocess

import pytest

from backend.sandbox import DockerSandbox, SandboxError


sandbox = DockerSandbox()


def run(payload: dict) -> dict:
    return asyncio.run(sandbox.run(payload))


def test_normal_code_and_deterministic_tests():
    result = run({"code": "print(2 + 2)\n", "tests": [{"name": "sum", "expected_stdout": "4\n"}]})
    assert result["passed"] is True
    assert result["tests"][0]["error"] is None


def test_syntax_and_runtime_errors_are_structured():
    syntax = run({"code": "if True print('x')", "tests": [{"name": "syntax"}]})
    runtime = run({"code": "raise ValueError('bad input')", "tests": [{"name": "runtime"}]})
    assert syntax["passed"] is False and "SyntaxError" in syntax["tests"][0]["error"]
    assert runtime["passed"] is False and "ValueError" in runtime["tests"][0]["error"]


def test_network_and_host_paths_are_unavailable():
    code = """import os, socket
try:
    socket.create_connection(('example.com', 80), 1)
    print('network-open')
except Exception:
    print('network-blocked')
try:
    open('/host/etc/passwd')
    print('host-open')
except Exception:
    print('host-blocked')
print('env=' + str(os.environ.get('PATCHWORK_HOST_SECRET')))
"""
    result = run({"code": code, "tests": [{"name": "isolation", "expected_stdout": "network-blocked\nhost-blocked\nenv=None\n"}]})
    assert result["passed"] is True


def test_infinite_loop_is_terminated():
    result = run({"code": "while True: pass", "tests": [{"name": "timeout"}]})
    assert result["passed"] is False
    assert result.get("error") == "container_failure" or "timed out" in result.get("stderr", "").lower()


def test_process_spawning_hits_pid_limit():
    code = """import subprocess, sys
children = []
try:
    for _ in range(100):
        children.append(subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)']))
    print('spawn-open')
except OSError:
    print('spawn-blocked')
finally:
    for child in children:
        child.kill()
"""
    result = run({"code": code, "tests": [{"name": "pid limit", "expected_stdout": "spawn-blocked\n"}]})
    assert result["passed"] is True


def test_excessive_output_is_rejected():
    result = run({"code": "print('x' * 70000)", "tests": [{"name": "output"}]})
    assert result["passed"] is False
    assert "64 KiB" in (result["stderr"] + str(result["tests"]))


def test_oversized_code_is_rejected():
    with pytest.raises(SandboxError, match="64 KiB"):
        run({"code": "#" * (64 * 1024 + 1), "tests": [{"name": "size"}]})


def test_container_is_removed_after_execution():
    run({"code": "print('done')", "tests": [{"name": "cleanup"}]})
    containers = subprocess.run(["docker", "ps", "-a", "--filter", "name=patchwork-run-", "--format", "{{.Names}}"], capture_output=True, text=True, check=True)
    assert "patchwork-run-" not in containers.stdout


def test_compiled_languages_get_a_longer_execution_budget():
    """javac/g++ compile inside the same window the program then runs in.

    A trivial Java submission measured 11.6-15.8s against the container's
    0.5 CPU / 128 MB limits, so the old single 10s budget randomly reported a
    correct answer as "Student execution timed out" - and since a lesson miss
    now costs a heart, that flake punished the learner for the toolchain.
    """
    from backend.sandbox import SandboxLimits, sandbox as real_sandbox

    limits = SandboxLimits()
    assert limits.compiled_timeout_seconds > limits.timeout_seconds
    assert real_sandbox._budget({"language": "java"}) == limits.compiled_timeout_seconds
    assert real_sandbox._budget({"language": "CPP"}) == limits.compiled_timeout_seconds
    # Interpreted languages must keep the short cap: an infinite loop still has
    # to be cut off quickly.
    assert real_sandbox._budget({"language": "python"}) == limits.timeout_seconds
    assert real_sandbox._budget({"language": "javascript"}) == limits.timeout_seconds
    assert real_sandbox._budget({}) == limits.timeout_seconds
