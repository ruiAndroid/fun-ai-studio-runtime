import logging
import threading
import time
import requests

from runtime_agent import settings

log = logging.getLogger(__name__)

_hb_stop: threading.Event | None = None
_hb_thread: threading.Thread | None = None


def heartbeat() -> None:
    if not settings.DEPLOY_BASE_URL or not settings.DEPLOY_NODE_TOKEN:
        return
    if not settings.RUNTIME_NODE_AGENT_BASE_URL or not settings.RUNTIME_NODE_GATEWAY_BASE_URL:
        return

    url = settings.DEPLOY_BASE_URL.rstrip("/") + "/internal/runtime-nodes/heartbeat"
    headers = {"X-RT-Node-Token": settings.DEPLOY_NODE_TOKEN}
    body = {
        "nodeName": settings.RUNTIME_NODE_NAME,
        "agentBaseUrl": settings.RUNTIME_NODE_AGENT_BASE_URL,
        "gatewayBaseUrl": settings.RUNTIME_NODE_GATEWAY_BASE_URL,
    }
    # best effort
    requests.post(url, json=body, headers=headers, timeout=3)


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
        while _hb_stop is not None and not _hb_stop.is_set():
            try:
                heartbeat()
            except Exception as e:
                # best-effort：不让线程死掉
                log.warning("deploy heartbeat failed: %s", e)
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


