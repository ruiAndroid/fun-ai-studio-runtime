import logging
import os
import shutil
import threading
import time
from typing import Optional
import requests

from runtime_agent import settings
from runtime_agent.docker_ops import docker

log = logging.getLogger(__name__)

_hb_stop: Optional[threading.Event] = None
_hb_thread: Optional[threading.Thread] = None


def _collect_metrics() -> dict:
    """
    收集节点指标（best-effort）：diskFreePct / diskFreeBytes / containerCount。
    """
    metrics = {}
    # 1. 磁盘水位（优先 /data/funai，fallback 到 /）
    try:
        path = "/data/funai" if os.path.exists("/data/funai") else "/"
        stat = shutil.disk_usage(path)
        total = stat.total
        free = stat.free
        if total > 0:
            metrics["diskFreePct"] = round((free / total) * 100.0, 2)
            metrics["diskFreeBytes"] = free
    except Exception as e:
        log.debug("collect disk metrics failed: %s", e)

    # 2. 容器数（运行中的用户应用容器：rt-u-* 前缀）
    try:
        ps = docker("ps", "--filter", "name=^rt-u-", "--format", "{{.Names}}", timeout_sec=5)
        if ps.code == 0 and ps.out:
            count = len([line for line in (ps.out or "").splitlines() if line.strip()])
            metrics["containerCount"] = count
    except Exception as e:
        log.debug("collect container count failed: %s", e)

    return metrics


def heartbeat() -> None:
    """
    上报一次 runtime 节点心跳（best-effort）。
    """
    if not settings.DEPLOY_BASE_URL or not settings.DEPLOY_NODE_TOKEN:
        log.warning("deploy heartbeat skipped: DEPLOY_BASE_URL/DEPLOY_NODE_TOKEN not configured")
        return
    if not settings.RUNTIME_NODE_AGENT_BASE_URL or not settings.RUNTIME_NODE_GATEWAY_BASE_URL:
        log.warning("deploy heartbeat skipped: RUNTIME_NODE_AGENT_BASE_URL/RUNTIME_NODE_GATEWAY_BASE_URL not configured")
        return

    url = settings.DEPLOY_BASE_URL.rstrip("/") + "/internal/runtime-nodes/heartbeat"
    headers = {"X-RT-Node-Token": settings.DEPLOY_NODE_TOKEN}
    body = {
        "nodeName": settings.RUNTIME_NODE_NAME,
        "agentBaseUrl": settings.RUNTIME_NODE_AGENT_BASE_URL,
        "gatewayBaseUrl": settings.RUNTIME_NODE_GATEWAY_BASE_URL,
    }
    # 收集指标（best-effort）
    try:
        metrics = _collect_metrics()
        body.update(metrics)
    except Exception as e:
        log.debug("collect metrics failed: %s", e)

    # best effort
    try:
        r = requests.post(url, json=body, headers=headers, timeout=3)
        if r.status_code >= 400:
            log.warning("deploy heartbeat failed: status=%s body=%s", r.status_code, (r.text or "")[:300])
        else:
            log.info("deploy heartbeat ok: node=%s metrics=%s", settings.RUNTIME_NODE_NAME, metrics)
    except Exception as e:
        log.warning("deploy heartbeat exception: %s", e)


def start_heartbeat_loop() -> None:
    """
    周期性向 Deploy 控制面上报 runtime 节点心跳，避免 health=STALE。
    - 间隔：settings.DEPLOY_HEARTBEAT_SECONDS（默认 60s）
    """
    global _hb_stop, _hb_thread
    if _hb_thread is not None and _hb_thread.is_alive():
        return
    _hb_stop = threading.Event()

    def _run():
        # 立即打一发，随后按间隔循环
        interval = int(getattr(settings, "DEPLOY_HEARTBEAT_SECONDS", 60) or 60)
        interval = 60 if interval <= 0 else interval
        log.info(
            "deploy heartbeat loop started: interval=%ss deployBaseUrl=%s node=%s",
            interval,
            settings.DEPLOY_BASE_URL,
            settings.RUNTIME_NODE_NAME,
        )
        while _hb_stop is not None and not _hb_stop.is_set():
            heartbeat()
            # sleep with stop support
            end = time.time() + interval
            while _hb_stop is not None and not _hb_stop.is_set() and time.time() < end:
                time.sleep(0.2)

    _hb_thread = threading.Thread(target=_run, name="deploy-heartbeat", daemon=True)
    _hb_thread.start()


def stop_heartbeat_loop() -> None:
    global _hb_stop, _hb_thread
    if _hb_stop is not None:
        _hb_stop.set()
    if _hb_thread is not None and _hb_thread.is_alive():
        _hb_thread.join(timeout=2)
    _hb_stop = None
    _hb_thread = None


