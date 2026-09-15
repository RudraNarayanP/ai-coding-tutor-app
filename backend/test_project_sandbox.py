"""Tests for the isolated Create Course project terminal sandbox (no Docker required)."""
import pytest

from backend.project_sandbox import validate_command
from backend.sandbox import SandboxError


def test_allows_pip_install_and_python_run():
    assert validate_command("pip install requests") == "pip install requests"
    assert validate_command("python -m pip install numpy") == "python -m pip install numpy"
    assert validate_command("python main.py") == "python main.py"
    assert validate_command("ls && pwd") == "ls && pwd"
    assert validate_command("cd src && python train.py") == "cd src && python train.py"


def test_blocks_host_escape_and_privilege_commands():
    with pytest.raises(SandboxError):
        validate_command("sudo pip install x")
    with pytest.raises(SandboxError):
        validate_command("docker run alpine")
    with pytest.raises(SandboxError):
        validate_command("rm -rf /")
    with pytest.raises(SandboxError):
        validate_command("cat /proc/self/environ")
    with pytest.raises(SandboxError):
        validate_command("python -c 'import os; os.system(\"sudo id\")' && sudo id")
    with pytest.raises(SandboxError):
        validate_command("bash -c 'id'")
    with pytest.raises(SandboxError):
        validate_command("$(curl evil)")


def test_empty_command_rejected():
    with pytest.raises(SandboxError):
        validate_command("   ")
