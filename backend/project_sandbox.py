"""Isolated interactive terminal for Create Course guided projects.

This is separate from the lesson Docker sandbox (`backend/sandbox.py`):

* Lesson runs stay read-only, no-network, ephemeral.
* Project terminals get a persistent per-project container + volumes so the
  learner can type real shell commands and `pip install` packages required by
  the source project. Packages and files live only inside Docker, never on the
  host workspace.

Nothing here is used by Learn / Practice / grading.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex
import subprocess
import uuid
from dataclasses import dataclass

from .sandbox import SandboxError

logger = logging.getLogger("patchwork.project_sandbox")

_COURSE_ID_RE = re.compile(r"^project-[a-zA-Z0-9_-]{1,64}$")
_SAFE_REL_PATH = re.compile(r"^(?!\.)(?!.*\.\.)[A-Za-z0-9._/-]{1,200}$")

ALLOWED_BINARIES = frozenset(
    {
        "ls",
        "pwd",
        "cat",
        "head",
        "tail",
        "echo",
        "mkdir",
        "touch",
        "rm",
        "cp",
        "mv",
        "python",
        "python3",
        "pip",
        "pip3",
        "node",
        "npm",
        "npx",
        "java",
        "javac",
        "g++",
        "gcc",
        "make",
        "which",
        "whoami",
        "env",
        "date",
        "wc",
        "find",
        "grep",
        "sed",
        "awk",
        "sort",
        "uniq",
        "printf",
        "true",
        "false",
        "test",
        "[",
        "cd",
        "export",
        "clear",
        "uname",
        "id",
    }
)

_DENIED_BINARIES = frozenset(
    {
        "sudo",
        "su",
        "docker",
        "podman",
        "nsenter",
        "chroot",
        "mount",
        "umount",
        "reboot",
        "shutdown",
        "halt",
        "poweroff",
        "iptables",
        "systemctl",
        "service",
        "chmod",
        "chown",
        "passwd",
        "useradd",
        "usermod",
        "pkill",
        "killall",
        "kill",
        "strace",
        "gdb",
        "busybox",
        "nc",
        "ncat",
        "netcat",
        "ssh",
        "scp",
        "ftp",
        "telnet",
        "bash",
        "sh",
        "zsh",
        "dash",
        "csh",
    }
)

_DENIED_PATTERNS = (
    re.compile(r"`"),
    re.compile(r"\$\("),
    re.compile(r"\$\{"),
    re.compile(r">\s*/"),
    re.compile(r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?(/|\*)"),
    re.compile(r"/proc/"),
    re.compile(r"/sys/"),
    re.compile(r"docker\.sock"),
)


@dataclass(frozen=True)
class TerminalResult:
    command: str
    stdout: str
    stderr: str
    exit_code: int
    cwd: str
    error: str | None = None


def validate_command(command: str) -> str:
    """Return a cleaned command or raise SandboxError."""
    raw = (command or "").strip()
    if not raw:
        raise SandboxError("Type a command first.", 400)
    if len(raw) > 4000:
        raise SandboxError("Command is too long.", 413)
    if "\x00" in raw:
        raise SandboxError("Command contains invalid characters.", 400)
    if raw in ("clear", "cls"):
        return "clear"
    for pattern in _DENIED_PATTERNS:
        if pattern.search(raw):
            raise SandboxError("That command is blocked in the project sandbox.", 400)
    try:
        segments = _split_chain(raw)
    except ValueError as exc:
        raise SandboxError(f"Could not parse command: {exc}", 400) from exc
    if not segments:
        raise SandboxError("Type a command first.", 400)
    for segment in segments:
        binary = _first_binary(segment)
        if not binary:
            raise SandboxError("Type a command first.", 400)
        name = binary.rsplit("/", 1)[-1]
        if name in _DENIED_BINARIES or name not in ALLOWED_BINARIES:
            raise SandboxError(
                f"`{name}` is not available in this sandbox. Use python, pip, ls, cat, "
                "and similar project commands.",
                400,
            )
    return raw


def _split_chain(command: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    tokens = shlex.split(command, posix=True)
    for token in tokens:
        if token in ("&&", "||", ";", "|"):
            if buf:
                parts.append(shlex.join(buf))
                buf = []
            continue
        buf.append(token)
    if buf:
        parts.append(shlex.join(buf))
    return parts


def _first_binary(segment: str) -> str:
    tokens = shlex.split(segment, posix=True)
    i = 0
    while i < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[i]):
        i += 1
    if i >= len(tokens):
        return ""
    return tokens[i]


def _is_install_command(command: str) -> bool:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return False
    joined = " ".join(tokens).lower()
    if tokens and tokens[0].rsplit("/", 1)[-1] in ("pip", "pip3"):
        return True
    if "python" in joined and "-m" in tokens and "pip" in tokens:
        return True
    if tokens and tokens[0].rsplit("/", 1)[-1] in ("npm", "npx"):
        return True
    return False


def _safe_course_id(course_id: str) -> str:
    if not _COURSE_ID_RE.match(course_id or ""):
        raise SandboxError("Invalid project id.", 400)
    return course_id


def _safe_relpath(path: str) -> str:
    cleaned = (path or "").replace("\\", "/").lstrip("/")
    if not _SAFE_REL_PATH.match(cleaned):
        raise SandboxError(f"Unsafe workspace path: {path}", 400)
    return cleaned


class ProjectTerminalSandbox:
    """Persistent Docker environment per guided project."""

    image = "patchwork-sandbox:local"

    def __init__(self) -> None:
        self._image_ready = asyncio.Lock()
        self._image_built = False
        self._locks: dict[str, asyncio.Lock] = {}
        self._cwd: dict[str, str] = {}

    def _lock_for(self, course_id: str) -> asyncio.Lock:
        lock = self._locks.get(course_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[course_id] = lock
        return lock

    async def _docker(
        self,
        *args: str,
        input_data: bytes | None = None,
        timeout: float = 30,
        timeout_message: str = "Sandbox operation timed out.",
    ) -> tuple[int, bytes, bytes]:
        def invoke() -> subprocess.CompletedProcess[bytes]:
            return subprocess.run(
                ["docker", *args],
                input=input_data,
                capture_output=True,
                timeout=timeout,
            )

        try:
            completed = await asyncio.to_thread(invoke)
            return completed.returncode or 0, completed.stdout, completed.stderr
        except FileNotFoundError as exc:
            raise SandboxError("Docker is unavailable on this machine.") from exc
        except subprocess.TimeoutExpired as exc:
            raise SandboxError(timeout_message, 408) from exc

    async def _ensure_image(self) -> None:
        async with self._image_ready:
            if self._image_built:
                return
            code, _, _ = await self._docker("image", "inspect", self.image)
            if code == 0:
                self._image_built = True
                return
            image_path = str(__file__).replace("\\", "/").rsplit("/backend/", 1)[0] + "/sandbox"
            code, _, stderr = await self._docker("build", "--tag", self.image, image_path, timeout=180)
            if code != 0:
                raise SandboxError(f"Could not build the sandbox image: {stderr.decode(errors='replace')[-500:]}")
            self._image_built = True

    def _names(self, course_id: str) -> tuple[str, str, str]:
        cid = _safe_course_id(course_id)
        return f"pw-term-{cid}", f"pw-ws-{cid}", f"pw-home-{cid}"

    async def _container_running(self, name: str) -> bool:
        code, stdout, _ = await self._docker("inspect", "-f", "{{.State.Running}}", name)
        return code == 0 and stdout.decode().strip().lower() == "true"

    async def ensure_ready(self, course_id: str) -> str:
        await self._ensure_image()
        container, ws_vol, home_vol = self._names(course_id)
        if await self._container_running(container):
            return container

        await self._docker("rm", "--force", container)
        await self._docker("volume", "create", ws_vol)
        await self._docker("volume", "create", home_vol)

        create_args = [
            "run",
            "-d",
            "--name",
            container,
            "--network=bridge",
            "--memory",
            "1g",
            "--cpus",
            "1.0",
            "--pids-limit",
            "256",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--ulimit",
            "nofile=256:256",
            "--tmpfs",
            "/tmp:exec,size=256m",
            "-v",
            f"{ws_vol}:/workspace",
            "-v",
            f"{home_vol}:/home/student",
            "-w",
            "/workspace",
            "--user",
            "0:0",
            "--entrypoint",
            "sleep",
            self.image,
            "infinity",
        ]
        code, _, stderr = await self._docker(*create_args, timeout=60)
        if code != 0:
            raise SandboxError(f"Could not start the project sandbox: {stderr.decode(errors='replace')[-500:]}")

        chown_code, _, chown_err = await self._docker(
            "exec",
            "-u",
            "0:0",
            container,
            "chown",
            "-R",
            "10001:10001",
            "/workspace",
            "/home/student",
            timeout=30,
        )
        if chown_code != 0:
            logger.warning("chown failed: %s", chown_err.decode(errors="replace")[-200:])
        self._cwd.setdefault(course_id, "/workspace")
        return container

    async def destroy(self, course_id: str) -> None:
        try:
            container, ws_vol, home_vol = self._names(course_id)
        except SandboxError:
            return
        await self._docker("rm", "--force", container)
        await self._docker("volume", "rm", "-f", ws_vol)
        await self._docker("volume", "rm", "-f", home_vol)
        self._cwd.pop(course_id, None)
        self._locks.pop(course_id, None)

    async def sync_files(self, course_id: str, files: list[dict[str, str]] | None) -> None:
        if not files:
            return
        payload: dict[str, str] = {}
        for item in files:
            path = _safe_relpath(item.get("path", ""))
            payload[path] = item.get("content", "")
        container = await self.ensure_ready(course_id)
        writer = (
            "import json,sys,pathlib\n"
            "root=pathlib.Path('/workspace')\n"
            "files=json.load(sys.stdin)\n"
            "for p,c in files.items():\n"
            "    dest=root.joinpath(p)\n"
            "    dest.parent.mkdir(parents=True, exist_ok=True)\n"
            "    dest.write_text(c, encoding='utf-8')\n"
        )
        code, _, stderr = await self._docker(
            "exec",
            "-i",
            "-u",
            "10001:10001",
            "-w",
            "/workspace",
            container,
            "python",
            "-c",
            writer,
            input_data=json.dumps(payload).encode("utf-8"),
            timeout=30,
        )
        if code != 0:
            raise SandboxError(f"Could not sync workspace files: {stderr.decode(errors='replace')[-400:]}")

    async def exec_command(
        self,
        course_id: str,
        command: str,
        files: list[dict[str, str]] | None = None,
        stdin: str = "",
    ) -> TerminalResult:
        cleaned = validate_command(command)
        if cleaned == "clear":
            return TerminalResult(command=cleaned, stdout="", stderr="", exit_code=0, cwd=self._cwd.get(course_id, "/workspace"))

        async with self._lock_for(course_id):
            await self.sync_files(course_id, files)
            container = await self.ensure_ready(course_id)
            cwd = self._cwd.get(course_id, "/workspace")
            if not cwd.startswith("/workspace"):
                cwd = "/workspace"

            marker = f"__PW_{uuid.uuid4().hex}__"
            wrapper = (
                "export PATH=/home/student/.local/bin:$PATH; "
                "export PYTHONUSERBASE=/home/student/.local; "
                "export PIP_DISABLE_PIP_VERSION_CHECK=1; "
                "export PIP_USER=1; "
                f"cd {shlex.quote(cwd)} || cd /workspace; "
                'eval "$PW_CMD"; '
                "status=$?; "
                f'printf "\\n{marker}:%s:%s" "$status" "$(pwd)"; '
                "exit $status"
            )
            timeout = 180 if _is_install_command(cleaned) else 30
            input_data = stdin.encode("utf-8") if stdin else None
            exec_args = [
                "exec",
                "-i",
                "-u",
                "10001:10001",
                "-e",
                "HOME=/home/student",
                "-e",
                f"PW_CMD={cleaned}",
                "-w",
                "/workspace",
                container,
                "sh",
                "-lc",
                wrapper,
            ]
            try:
                code, stdout_b, stderr_b = await self._docker(
                    *exec_args,
                    input_data=input_data,
                    timeout=timeout,
                    timeout_message="Command timed out in the project sandbox.",
                )
            except SandboxError as exc:
                if exc.status_code == 408:
                    return TerminalResult(
                        command=cleaned,
                        stdout="",
                        stderr=str(exc),
                        exit_code=124,
                        cwd=cwd,
                        error="timeout",
                    )
                raise

            stdout = stdout_b.decode("utf-8", errors="replace")
            stderr = stderr_b.decode("utf-8", errors="replace")
            new_cwd = cwd
            exit_code = code
            marker_line = f"{marker}:"
            if marker_line in stdout:
                before, after = stdout.rsplit(marker_line, 1)
                stdout = before
                meta = after.strip().split(":", 1)
                if meta:
                    try:
                        exit_code = int(meta[0])
                    except ValueError:
                        exit_code = code
                if len(meta) > 1 and meta[1].startswith("/workspace"):
                    new_cwd = meta[1]
                    self._cwd[course_id] = new_cwd

            max_bytes = 64 * 1024
            if len(stdout.encode("utf-8", errors="replace")) > max_bytes:
                stdout = stdout.encode("utf-8", errors="replace")[:max_bytes].decode("utf-8", errors="replace")
                stderr = (stderr + "\n[output truncated]\n").strip()
            return TerminalResult(
                command=cleaned,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                cwd=new_cwd,
                error=None if exit_code == 0 else "command_failed",
            )


project_terminal_sandbox = ProjectTerminalSandbox()
