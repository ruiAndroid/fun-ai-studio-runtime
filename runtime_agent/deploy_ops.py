from runtime_agent import settings
from runtime_agent.docker_ops import docker, container_name
from runtime_agent.traefik_labels import labels_for_app

import re
from datetime import datetime, timezone

try:
    # Optional dependency, used for best-effort DB pre-create.
    from pymongo import MongoClient  # type: ignore
except Exception:  # pragma: no cover
    MongoClient = None  # type: ignore


def ensure_network(network: str) -> None:
    if not network:
        return
    r = docker("network", "inspect", network, timeout_sec=10)
    if r.code == 0:
        return
    docker("network", "create", network, timeout_sec=30)


_MONGO_DB_SAFE_RE = re.compile(r"[^a-zA-Z0-9_]+")


def _mongo_db_name(user_id: str, app_id: str) -> str:
    """
    Generate a safe MongoDB database name.
    - Uses template RUNTIME_MONGO_DB_TEMPLATE with placeholders {userId}/{appId}.
    - Replaces invalid characters with '_'.
    """
    raw = (settings.RUNTIME_MONGO_DB_TEMPLATE or "db_u{userId}_a{appId}").format(userId=user_id, appId=app_id)
    name = _MONGO_DB_SAFE_RE.sub("_", (raw or "").strip())
    # avoid empty / leading underscore-only
    if not name or set(name) == {"_"}:
        name = f"db_u{user_id}_a{app_id}"
        name = _MONGO_DB_SAFE_RE.sub("_", name)
    # MongoDB has a 63-byte namespace limit for some constructs; DB name practical limit is small.
    # Keep it conservative.
    return name[:63]


def _mongodb_uri(db_name: str) -> str:
    host = (settings.RUNTIME_MONGO_HOST or "").strip()
    port = int(settings.RUNTIME_MONGO_PORT or 27017)
    if not host:
        return ""
    user = (settings.RUNTIME_MONGO_USERNAME or "").strip()
    pwd = (settings.RUNTIME_MONGO_PASSWORD or "").strip()
    auth_source = (settings.RUNTIME_MONGO_AUTH_SOURCE or "admin").strip()
    if user and pwd:
        return f"mongodb://{user}:{pwd}@{host}:{port}/{db_name}?authSource={auth_source}"
    return f"mongodb://{host}:{port}/{db_name}"


def _mongo_precreate_best_effort(uri: str, db_name: str, user_id: str, app_id: str) -> None:
    """
    Best-effort create DB/collection by doing a single upsert.
    This should never break deployment flow.
    """
    if not settings.RUNTIME_MONGO_PRECREATE:
        return
    if not uri:
        return
    if MongoClient is None:
        return
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=int(settings.RUNTIME_MONGO_PRECREATE_TIMEOUT_SECONDS * 1000))
        db = client.get_database(db_name)
        db.get_collection("__funai_meta__").update_one(
            {"_id": "init"},
            {
                "$setOnInsert": {
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                    "userId": str(user_id),
                    "appId": str(app_id),
                }
            },
            upsert=True,
        )
    except Exception:
        # swallow: DB might be temporarily unreachable; app may still start and retry later.
        pass
    finally:
        try:
            client.close()  # type: ignore
        except Exception:
            pass


def deploy_container(user_id: str, app_id: str, image: str, container_port: int, base_path: str = "") -> str:
    name = container_name(user_id, app_id)

    ensure_network(settings.RUNTIME_DOCKER_NETWORK)

    # pull image (optional but helpful)
    docker("pull", image, timeout_sec=300)

    # remove existing
    docker("rm", "-f", name, timeout_sec=30)

    args = ["run", "-d", "--restart=always", "--name", name]

    # Optional per-app resource limits (docker/podman compatible flags).
    if settings.RUNTIME_APP_CPUS:
        args += ["--cpus", settings.RUNTIME_APP_CPUS]
    if settings.RUNTIME_APP_CPU_SHARES:
        args += ["--cpu-shares", settings.RUNTIME_APP_CPU_SHARES]
    if settings.RUNTIME_APP_CPUSET_CPUS:
        args += ["--cpuset-cpus", settings.RUNTIME_APP_CPUSET_CPUS]
    if settings.RUNTIME_APP_MEMORY:
        args += ["--memory", settings.RUNTIME_APP_MEMORY]
    if settings.RUNTIME_APP_MEMORY_SWAP:
        args += ["--memory-swap", settings.RUNTIME_APP_MEMORY_SWAP]
    if settings.RUNTIME_APP_PIDS_LIMIT:
        args += ["--pids-limit", settings.RUNTIME_APP_PIDS_LIMIT]

    if settings.RUNTIME_DOCKER_NETWORK:
        args += ["--network", settings.RUNTIME_DOCKER_NETWORK]

    if settings.RUNTIME_TRAEFIK_ENABLE:
        for k, v in labels_for_app(app_id, container_port, base_path=base_path).items():
            args += ["--label", f"{k}={v}"]

    # Inject runtime Mongo connection for user apps (recommended).
    # Apps should read process.env.MONGODB_URI (or MONGO_URL).
    if (settings.RUNTIME_MONGO_HOST or "").strip():
        db_name = _mongo_db_name(user_id, app_id)
        uri = _mongodb_uri(db_name)
        if uri:
            args += ["-e", f"MONGODB_URI={uri}", "-e", f"MONGO_URL={uri}"]
            args += ["-e", f"FUNAI_MONGO_DB_NAME={db_name}"]
            # best-effort precreate (so DB appears immediately even if app doesn't write yet)
            _mongo_precreate_best_effort(uri=uri, db_name=db_name, user_id=user_id, app_id=app_id)

    # no host port publishing; traffic goes via gateway container network
    args += [image]

    r = docker(*args, timeout_sec=120)
    if r.code != 0:
        raise RuntimeError(f"docker run failed: {r.err or r.out}")
    return name


def stop_container(user_id: str, app_id: str) -> None:
    docker("rm", "-f", container_name(user_id, app_id), timeout_sec=30)


def remove_app_images(user_id: str, app_id: str) -> dict:
    """
    Best-effort remove local images for this app.

    Repo naming convention (from Runner):
      <registry>/<namespace>/u{userId}-app{appId}:<tag>

    On runtime node we don't persist the exact image ref, so we match by repository suffix:
      .../u{userId}-app{appId}
    """
    suffix = f"/u{user_id}-app{app_id}"
    removed: list[str] = []
    kept: list[str] = []

    imgs = docker("images", "--format", "{{.Repository}}:{{.Tag}}", timeout_sec=30)
    if imgs.code != 0:
        return {"removed": removed, "kept": kept, "error": (imgs.err or imgs.out or "").strip()}

    for line in (imgs.out or "").splitlines():
        ref = (line or "").strip()
        if not ref or ref.endswith(":<none>") or ref.startswith("<none>"):
            continue
        # Repository part is before the last ":"; tag after it.
        # We only need to know if repository ends with suffix.
        repo = ref.rsplit(":", 1)[0]
        if not repo.endswith(suffix):
            continue
        # remove
        r = docker("rmi", "-f", ref, timeout_sec=60)
        if r.code == 0:
            removed.append(ref)
        else:
            kept.append(ref)

    # remove dangling layers (safe; doesn't touch tagged images)
    try:
        docker("image", "prune", "-f", timeout_sec=120)
    except Exception:
        pass

    return {"removed": removed, "kept": kept}

