from fastapi import Depends, FastAPI

from runtime_agent.auth import require_runtime_token
from runtime_agent.deploy_ops import deploy_container, stop_container
from runtime_agent.deploy_registry import heartbeat, start_heartbeat_loop, stop_heartbeat_loop
from runtime_agent.docker_ops import container_name, docker
from runtime_agent.logging_setup import setup_logging
from runtime_agent.models import AppStatusResponse, DeployAppRequest, StopAppRequest

setup_logging("fun-ai-studio-runtime")

app = FastAPI(title="fun-ai-studio-runtime-agent")


@app.get("/internal")
def internal_root():
    return {"ok": True}


@app.get("/internal/health")
def health():
    return {"ok": True}


@app.on_event("startup")
def on_startup():
    # heartbeat loop (every DEPLOY_HEARTBEAT_SECONDS, default 60s)
    try:
        start_heartbeat_loop()
    except Exception:
        pass

    # best-effort heartbeat once on startup
    try:
        heartbeat()
    except Exception:
        pass


@app.on_event("shutdown")
def on_shutdown():
    try:
        stop_heartbeat_loop()
    except Exception:
        pass


@app.post("/agent/apps/deploy", dependencies=[Depends(require_runtime_token)])
def deploy(req: DeployAppRequest):
    name = deploy_container(req.appId, req.image, req.containerPort)
    # refresh heartbeat
    try:
        heartbeat()
    except Exception:
        pass
    return {"appId": req.appId, "containerName": name, "status": "DEPLOYED"}


@app.post("/agent/apps/stop", dependencies=[Depends(require_runtime_token)])
def stop(req: StopAppRequest):
    stop_container(req.appId)
    return {"appId": req.appId, "status": "STOPPED"}


@app.get("/agent/apps/status", dependencies=[Depends(require_runtime_token)], response_model=AppStatusResponse)
def status(appId: str):
    name = container_name(appId)
    inspect = docker("inspect", name, timeout_sec=10)
    if inspect.code != 0:
        return AppStatusResponse(appId=appId, containerName=name, exists=False, running=False)
    # naive: if inspect ok, assume exists; check running via ps
    ps = docker("ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}", timeout_sec=10)
    running = ps.code == 0 and (name in (ps.out or ""))
    return AppStatusResponse(appId=appId, containerName=name, exists=True, running=running)


