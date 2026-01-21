import logging
import threading
import time
from typing import Optional
import requests

from runtime_agent import settings

log = logging.getLogger(__name__)

_hb_stop: Optional[threading.Event] = None
_hb_thread: Optional[threading.Thread] = None


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
    # best effort
    try:
        r = requests.post(url, json=body, headers=headers, timeout=3)
        if r.status_code >= 400:
            log.warning("deploy heartbeat failed: status=%s body=%s", r.status_code, (r.text or "")[:300])
        else:
            log.info("deploy heartbeat ok: node=%s", settings.RUNTIME_NODE_NAME)
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


