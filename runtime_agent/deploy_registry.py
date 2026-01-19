import requests

from runtime_agent import settings


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


