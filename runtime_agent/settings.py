import os


def env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v.strip()


RUNTIME_AGENT_HOST = env("RUNTIME_AGENT_HOST", "0.0.0.0")
RUNTIME_AGENT_PORT = int(env("RUNTIME_AGENT_PORT", "7005"))
RUNTIME_AGENT_TOKEN = env("RUNTIME_AGENT_TOKEN", "CHANGE_ME")

RUNTIME_NODE_NAME = env("RUNTIME_NODE_NAME", "rt-node-01")
RUNTIME_NODE_AGENT_BASE_URL = env("RUNTIME_NODE_AGENT_BASE_URL")  # e.g. http://10.0.0.12:7005
RUNTIME_NODE_GATEWAY_BASE_URL = env("RUNTIME_NODE_GATEWAY_BASE_URL")  # e.g. https://gw.example.com

DEPLOY_BASE_URL = env("DEPLOY_BASE_URL")  # e.g. http://10.0.0.10:7002
DEPLOY_NODE_TOKEN = env("DEPLOY_NODE_TOKEN")  # X-RT-Node-Token

RUNTIME_DOCKER_NETWORK = env("RUNTIME_DOCKER_NETWORK", "")
RUNTIME_TRAEFIK_ENABLE = env("RUNTIME_TRAEFIK_ENABLE", "true").lower() != "false"
RUNTIME_CONTAINER_PORT = int(env("RUNTIME_CONTAINER_PORT", "3000"))


