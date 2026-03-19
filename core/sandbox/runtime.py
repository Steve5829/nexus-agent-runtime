import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence


@dataclass
class SandboxLimits:
    cpu_seconds: int = 2
    memory_mb: int = 128
    file_size_mb: int = 8
    max_fds: int = 32


@dataclass
class SandboxResult:
    command: Sequence[str]
    returncode: int
    stdout: str
    stderr: str


class SandboxRuntime:
    """
    Thin Python wrapper around the C launcher.

    On Linux, the compiled launcher can apply resource limits and seccomp before
    transferring control to the payload. On other platforms we fall back to
    direct execution so the rest of the repository remains runnable.
    """

    def __init__(self, launcher: Optional[Path] = None):
        self.launcher = launcher or Path(__file__).with_name("sandbox_kernel")

    def build_command(self, payload: Sequence[str]) -> Sequence[str]:
        if not payload:
            raise ValueError("Sandbox payload cannot be empty.")

        if platform.system() == "Linux" and self.launcher.exists():
            return [str(self.launcher)] + list(payload)

        return list(payload)

    def run(
        self,
        payload: Sequence[str],
        timeout: float = 5.0,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> SandboxResult:
        command = self.build_command(payload)
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        completed = subprocess.run(
            command,
            capture_output=True,
            cwd=cwd,
            env=merged_env,
            text=True,
            timeout=timeout,
        )
        return SandboxResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
