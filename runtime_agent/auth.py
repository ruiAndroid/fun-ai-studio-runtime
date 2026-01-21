from typing import Optional

from fastapi import Header, HTTPException

from runtime_agent import settings


def require_runtime_token(x_runtime_token: Optional[str] = Header(default=None, alias="X-Runtime-Token")) -> None:
    expected = settings.RUNTIME_AGENT_TOKEN
    if not expected or expected == "CHANGE_ME":
        raise HTTPException(status_code=500, detail="runtime agent token not configured")
    if x_runtime_token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


