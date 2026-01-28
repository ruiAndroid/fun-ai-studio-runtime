import os
from typing import Optional


def env(name: str, default: Optional[str] = None) -> Optional[str]:
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
DEPLOY_HEARTBEAT_SECONDS = int(env("DEPLOY_HEARTBEAT_SECONDS", "60") or "60")

RUNTIME_DOCKER_NETWORK = env("RUNTIME_DOCKER_NETWORK", "")
RUNTIME_TRAEFIK_ENABLE = env("RUNTIME_TRAEFIK_ENABLE", "true").lower() != "false"
RUNTIME_CONTAINER_PORT = int(env("RUNTIME_CONTAINER_PORT", "3000"))

# -----------------------------
# Runtime Mongo (optional but recommended for deployed apps)
# -----------------------------
# If RUNTIME_MONGO_HOST is empty -> do not inject MONGODB_URI into user app containers.
RUNTIME_MONGO_HOST = env("RUNTIME_MONGO_HOST", "")  # e.g. 172.21.138.89
RUNTIME_MONGO_PORT = int(env("RUNTIME_MONGO_PORT", "27017") or "27017")
RUNTIME_MONGO_USERNAME = env("RUNTIME_MONGO_USERNAME", "")
RUNTIME_MONGO_PASSWORD = env("RUNTIME_MONGO_PASSWORD", "")
RUNTIME_MONGO_AUTH_SOURCE = env("RUNTIME_MONGO_AUTH_SOURCE", "admin")

# Database naming template. Available placeholders: {userId}, {appId}
# Recommended (user-app dimension): db_u{userId}_a{appId}
RUNTIME_MONGO_DB_TEMPLATE = env("RUNTIME_MONGO_DB_TEMPLATE", "db_u{userId}_a{appId}") or "db_u{userId}_a{appId}"

# If true, runtime-agent will best-effort pre-create the database by writing a sentinel document.
# Note: MongoDB "creates" DB/collections on first write, so this is only to make it explicit/visible.
RUNTIME_MONGO_PRECREATE = env("RUNTIME_MONGO_PRECREATE", "true").lower() == "true"
RUNTIME_MONGO_PRECREATE_TIMEOUT_SECONDS = int(env("RUNTIME_MONGO_PRECREATE_TIMEOUT_SECONDS", "3") or "3")

# -----------------------------
# User app container resource limits (optional)
# -----------------------------
# If empty -> do not pass the flag to docker/podman.
RUNTIME_APP_CPUS = env("RUNTIME_APP_CPUS", "")  # e.g. "1", "1.5", "2"
RUNTIME_APP_CPU_SHARES = env("RUNTIME_APP_CPU_SHARES", "")  # e.g. "512" (default 1024)
RUNTIME_APP_CPUSET_CPUS = env("RUNTIME_APP_CPUSET_CPUS", "")  # e.g. "0-3"
RUNTIME_APP_MEMORY = env("RUNTIME_APP_MEMORY", "")  # e.g. "512m", "1g", "2g"
RUNTIME_APP_MEMORY_SWAP = env("RUNTIME_APP_MEMORY_SWAP", "")  # e.g. "1g" (or "0" to disable swap)
RUNTIME_APP_PIDS_LIMIT = env("RUNTIME_APP_PIDS_LIMIT", "")  # e.g. "256"

# -----------------------------
# Cleanup behavior
# -----------------------------
# If true, stop (offline) will also remove local images for this app (saves disk, slower redeploy).
RUNTIME_CLEANUP_IMAGES_ON_STOP = env("RUNTIME_CLEANUP_IMAGES_ON_STOP", "false").lower() == "true"


