import asyncio
import json
import subprocess
import time
import uuid
from dataclasses import dataclass


class SandboxError(Exception):
    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SandboxLimits:
    timeout_seconds: float = 10
    memory: str = "128m"
    cpus: str = "0.5"
    pids: str = "32"
    max_output_bytes: int = 64 * 1024
    max_code_bytes: int = 64 * 1024


class DockerSandbox:
    image = "patchwork-sandbox:local"

    def __init__(self, limits: SandboxLimits | None = None) -> None:
        self.limits = limits or SandboxLimits()
        self._image_ready = asyncio.Lock()

    async def _docker(self, *args: str, input_data: bytes | None = None, timeout: float = 30, timeout_message: str = "Docker operation timed out.") -> tuple[int, bytes, bytes]:
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
            code, _, _ = await self._docker("image", "inspect", self.image)
            if code == 0:
                return
            image_path = str(__file__).replace("\\", "/").rsplit("/backend/", 1)[0] + "/sandbox"
            code, _, stderr = await self._docker("build", "--tag", self.image, image_path, timeout=120)
            if code != 0:
                raise SandboxError(f"Could not build the sandbox image: {stderr.decode(errors='replace')[-500:]}")

    async def run(self, payload: dict) -> dict:
        code_bytes = payload["code"].encode("utf-8")
        if len(code_bytes) > self.limits.max_code_bytes:
            raise SandboxError("Submitted code exceeds the 64 KiB limit.", 413)
        await self._ensure_image()
        container = f"patchwork-run-{uuid.uuid4().hex}"
        create_args = [
            "create", "--name", container, "--network=none", "--read-only",
            "--tmpfs", "/tmp:exec,size=64m", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--user", "10001:10001",
            "--memory", self.limits.memory, "--cpus", self.limits.cpus,
            "--pids-limit", self.limits.pids, "--ulimit", "nofile=64:64",
            "--ulimit", "fsize=65536:65536", "--entrypoint", "python", self.image,
            "-c", "import time; time.sleep(60)",
        ]
        try:
            code, _, stderr = await self._docker(*create_args)
            if code != 0:
                raise SandboxError(f"Could not create the sandbox container: {stderr.decode(errors='replace')[-500:]}")
            started = time.perf_counter()
            code, _, stderr = await self._docker("start", container, timeout=30)
            if code != 0:
                raise SandboxError(f"Could not start the sandbox container: {stderr.decode(errors='replace')[-500:]}")
            try:
                code, stdout, stderr = await self._docker("exec", "--interactive", container, "python", "-I", "/sandbox/runner.py", input_data=json.dumps(payload).encode(), timeout=self.limits.timeout_seconds, timeout_message="Student execution timed out.")
            except SandboxError as exc:
                if exc.status_code == 408:
                    return {"passed": False, "tests": [], "stdout": "", "stderr": str(exc), "execution_time_ms": round((time.perf_counter() - started) * 1000), "error": "timeout"}
                raise
            elapsed = round((time.perf_counter() - started) * 1000)
            if len(stdout) > self.limits.max_output_bytes:
                return {"passed": False, "tests": [], "stdout": "", "stderr": "Sandbox output exceeded the 64 KiB limit.", "execution_time_ms": elapsed, "error": "excessive_output"}
            if code != 0:
                return {"passed": False, "tests": [], "stdout": "", "stderr": stderr.decode(errors="replace")[-self.limits.max_output_bytes:], "execution_time_ms": elapsed, "error": "container_failure"}
            try:
                result = json.loads(stdout.decode("utf-8"))
            except json.JSONDecodeError:
                return {"passed": False, "tests": [], "stdout": "", "stderr": "Sandbox returned an invalid result.", "execution_time_ms": elapsed, "error": "invalid_sandbox_result"}
            result["execution_time_ms"] = elapsed
            return result
        except SandboxError:
            raise
        finally:
            await self._docker("rm", "--force", container)


sandbox = DockerSandbox()
