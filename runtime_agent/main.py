from fastapi import Depends, FastAPI, HTTPException

from runtime_agent.auth import require_runtime_token
from runtime_agent.deploy_ops import deploy_container, stop_container, remove_app_images, drop_app_db_best_effort
from runtime_agent.deploy_registry import heartbeat, start_heartbeat_loop, stop_heartbeat_loop
from runtime_agent.docker_ops import container_name, docker
from runtime_agent.logging_setup import setup_logging
from runtime_agent.models import AppStatusResponse, DeployAppRequest, StopAppRequest, DeleteAppRequest
from runtime_agent import settings

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
    name = deploy_container(req.userId, req.appId, req.image, req.containerPort, base_path=req.basePath)
    # refresh heartbeat
    try:
        heartbeat()
    except Exception:
        pass
    base = (settings.RUNTIME_NODE_GATEWAY_BASE_URL or "").rstrip("/")
    preview = None
    if base:
        p = (req.basePath or "").strip()
        if not p:
            p = f"/apps/{req.appId}"
        if not p.startswith("/"):
            p = "/" + p
        preview = base + p + "/"
    return {"appId": req.appId, "containerName": name, "status": "DEPLOYED", "previewUrl": preview}


@app.post("/agent/apps/stop", dependencies=[Depends(require_runtime_token)])
def stop(req: StopAppRequest):
    stop_container(req.userId, req.appId)
    if settings.RUNTIME_CLEANUP_IMAGES_ON_STOP:
        try:
            remove_app_images(req.userId, req.appId)
        except Exception:
            pass
    return {"appId": req.appId, "status": "STOPPED"}


@app.post("/agent/apps/delete", dependencies=[Depends(require_runtime_token)])
def delete(req: DeleteAppRequest):
    # remove container first (idempotent)
    stop_container(req.userId, req.appId)
    img = remove_app_images(req.userId, req.appId)
    db = drop_app_db_best_effort(req.userId, req.appId)
    return {"appId": req.appId, "status": "DELETED", "images": img, "mongo": db}


@app.get("/agent/apps/status", dependencies=[Depends(require_runtime_token)], response_model=AppStatusResponse)
def status(userId: str, appId: str):
    name = container_name(userId, appId)
    inspect = docker("inspect", name, timeout_sec=10)
    if inspect.code != 0:
        # docker 不可用/daemon 不可达/权限问题：明确返回可读错误，避免"Internal Server Error"
        err = (inspect.err or inspect.out or "").lower()
        if inspect.code == 127 or "no such file" in err or "not found" in err:
            raise HTTPException(status_code=500, detail="docker binary not found (install docker or set RUNTIME_DOCKER_BIN)")
        if "cannot connect to the docker daemon" in err or "is the docker daemon running" in err:
            raise HTTPException(status_code=500, detail="cannot connect to docker daemon (is docker running?)")
        if "permission denied" in err:
            raise HTTPException(status_code=500, detail="permission denied to access docker (check /var/run/docker.sock permissions)")
        return AppStatusResponse(appId=appId, containerName=name, exists=False, running=False)
    # naive: if inspect ok, assume exists; check running via ps
    ps = docker("ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}", timeout_sec=10)
    running = ps.code == 0 and (name in (ps.out or ""))

    img = docker("inspect", "-f", "{{.Config.Image}}", name, timeout_sec=10)
    # 端口优先从 traefik label 读取；若没有则返回 None
    label_key = f"traefik.http.services.rt-svc-{appId}.loadbalancer.server.port"
    port = docker("inspect", "-f", f"{{{{(index .Config.Labels \"{label_key}\")}}}}", name, timeout_sec=10)
    image_val = img.out.strip() if img.code == 0 else None
    port_val = None
    if port.code == 0:
        p = port.out.strip()
        try:
            port_val = int(p) if p else None
        except Exception:
            port_val = None
    return AppStatusResponse(appId=appId, containerName=name, exists=True, running=running, image=image_val, port=port_val)


