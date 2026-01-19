import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CmdResult:
    code: int
    out: str
    err: str


def run(cmd: list[str], timeout_sec: int = 60) -> CmdResult:
    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        shell=False,
        check=False,
    )
    return CmdResult(code=p.returncode, out=p.stdout or "", err=p.stderr or "")


def docker(*args: str, timeout_sec: int = 120) -> CmdResult:
    return run(["docker", *args], timeout_sec=timeout_sec)


def container_name(app_id: str) -> str:
    return f"rt-app-{app_id}"


