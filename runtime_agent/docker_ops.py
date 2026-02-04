import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class CmdResult:
    code: int
    out: str
    err: str


def run(cmd: List[str], timeout_sec: int = 60, stdin: Optional[str] = None) -> CmdResult:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            input=stdin,
            timeout=timeout_sec,
            shell=False,
            check=False,
        )
        return CmdResult(code=p.returncode, out=p.stdout or "", err=p.stderr or "")
    except FileNotFoundError as e:
        # docker 二进制不存在/不在 PATH
        return CmdResult(code=127, out="", err=str(e))
    except Exception as e:
        # 兜底：避免抛异常导致 API 直接 500（无 detail）
        return CmdResult(code=1, out="", err=str(e))


def docker(*args: str, timeout_sec: int = 120, stdin: Optional[str] = None) -> CmdResult:
    docker_bin = os.getenv("RUNTIME_DOCKER_BIN", "docker")
    return run([docker_bin, *args], timeout_sec=timeout_sec, stdin=stdin)


def docker_bin_name() -> str:
    """
    Return the runtime container engine binary name (docker/podman).
    """
    return (os.getenv("RUNTIME_DOCKER_BIN", "docker") or "docker").strip()


def is_podman() -> bool:
    b = docker_bin_name().lower()
    return "podman" in b


def container_name(user_id: str, app_id: str) -> str:
    return f"rt-u-{user_id}-{app_id}"


