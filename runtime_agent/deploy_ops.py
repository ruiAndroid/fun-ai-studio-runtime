from runtime_agent import settings
from runtime_agent.docker_ops import docker, container_name, is_podman, docker_bin_name
from runtime_agent.traefik_labels import labels_for_app

import re
import time
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


def ensure_registry_login() -> None:
    """
    Auto-login to registry (Harbor) if credentials are configured.
    This ensures runtime can pull images from private registry.
    """
    if not settings.REGISTRY_URL:
        return
    if not settings.REGISTRY_USERNAME or not settings.REGISTRY_PASSWORD:
        return
    
    # Check if already logged in by trying to pull a test (will fail gracefully if not logged in)
    # For simplicity, we just login every time (docker/podman will cache credentials)
    try:
        # Use stdin for password to avoid exposing it in process list
        r = docker(
            "login",
            settings.REGISTRY_URL,
            "-u",
            settings.REGISTRY_USERNAME,
            "--password-stdin",
            stdin=settings.REGISTRY_PASSWORD,
            timeout_sec=30
        )
        if r.code != 0:
            # Log warning but don't fail - maybe credentials are already cached
            print(f"Warning: Registry login failed: {r.err or r.out}")
    except Exception as e:
        print(f"Warning: Registry login error: {e}")


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


def drop_app_db_best_effort(user_id: str, app_id: str) -> dict:
    """
    Best-effort drop the app database when app is deleted.
    This must never break the delete flow.
    """
    if not settings.RUNTIME_MONGO_DROP_ON_DELETE:
        return {"enabled": False, "dropped": False}
    if not (settings.RUNTIME_MONGO_HOST or "").strip():
        return {"enabled": True, "dropped": False, "reason": "RUNTIME_MONGO_HOST not configured"}
    if MongoClient is None:
        return {"enabled": True, "dropped": False, "reason": "pymongo not installed"}
    try:
        db_name = _mongo_db_name(user_id, app_id)
        uri = _mongodb_uri(db_name)
        if not uri:
            return {"enabled": True, "dropped": False, "reason": "mongodb uri empty"}
        client = MongoClient(uri, serverSelectionTimeoutMS=int(settings.RUNTIME_MONGO_PRECREATE_TIMEOUT_SECONDS * 1000))
        client.drop_database(db_name)
        return {"enabled": True, "dropped": True, "dbName": db_name}
    except Exception as e:
        return {"enabled": True, "dropped": False, "error": str(e)}
    finally:
        try:
            client.close()  # type: ignore
        except Exception:
            pass


def deploy_container(user_id: str, app_id: str, image: str, container_port: int, base_path: str = "") -> str:
    name = container_name(user_id, app_id)

    ensure_network(settings.RUNTIME_DOCKER_NETWORK)
    
    # Auto-login to registry if configured
    ensure_registry_login()

    # pull image (optional but helpful)
    docker("pull", image, timeout_sec=300)

    # remove existing (idempotent deploy)
    # - For Podman: prefer --replace to avoid "name already in use" races and storage edge-cases.
    # - For Docker: best-effort rm -f; if still exists, fail fast with a clearer error.
    rm = docker("rm", "-f", name, timeout_sec=30)
    if rm.code != 0:
        # "no such container" is fine; any other error should be surfaced because it will cause name conflicts.
        msg = (rm.err or rm.out or "").strip().lower()
        if "no such" not in msg and "not found" not in msg:
            # keep going for podman --replace path; for docker we will hard-fail later if still exists
            pass

    args = ["run", "-d", "--restart=always", "--name", name]
    if is_podman():
        # Podman supports --replace to atomically replace existing container with same name.
        args.insert(1, "--replace")
    else:
        # docker: ensure name is actually free (otherwise we will get a confusing error at run time)
        chk = docker("inspect", name, timeout_sec=10)
        if chk.code == 0:
            raise RuntimeError(
                "deploy refused: existing container still present after rm -f. "
                f"engine={docker_bin_name()}, name={name}, rmErr={(rm.err or rm.out)}"
            )

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

    # Post-check: ensure container did not immediately crash-loop (common: missing build artifacts / bad CMD).
    # Without this, deployment might be reported "success" while container exits instantly, leading to /runtime/{appId} 502.
    _assert_container_running_best_effort(name, wait_seconds=3)
    return name


def _inspect_field(name: str, go_template: str) -> str:
    """
    Inspect a single field via Go template. Works for docker/podman.
    Returns trimmed stdout on success, else empty string.
    """
    r = docker("inspect", "-f", go_template, name, timeout_sec=10)
    if r.code != 0:
        return ""
    return (r.out or "").strip()


def _assert_container_running_best_effort(name: str, wait_seconds: int = 3) -> None:
    """
    Wait briefly for container to stay in running state.

    If it exits quickly, raise RuntimeError with exitCode and tail logs to surface real cause
    (e.g., MODULE_NOT_FOUND, config missing, port binding error).
    """
    deadline = time.time() + max(0, int(wait_seconds))
    last_running = ""
    while True:
        running = _inspect_field(name, "{{.State.Running}}").lower()
        last_running = running
        if running == "true":
            return

        # If already exited, we can fail fast without waiting full timeout.
        exit_code = _inspect_field(name, "{{.State.ExitCode}}")
        status = _inspect_field(name, "{{.State.Status}}") or "unknown"
        err = _inspect_field(name, "{{.State.Error}}")
        finished = _inspect_field(name, "{{.State.FinishedAt}}")
        if exit_code and exit_code != "0" and status in ("exited", "dead"):
            logs = docker("logs", "--tail", "120", name, timeout_sec=10)
            tail = (logs.out or logs.err or "").strip()
            raise RuntimeError(
                "container exited right after start: "
                f"name={name}, status={status}, exitCode={exit_code}, finishedAt={finished}, error={err}, "
                f"logsTail={tail[-2000:]}"
            )

        if time.time() >= deadline:
            # timeout: still not running; include minimal diag
            logs = docker("logs", "--tail", "80", name, timeout_sec=10)
            tail = (logs.out or logs.err or "").strip()
            raise RuntimeError(
                "container not running after deploy: "
                f"name={name}, running={last_running}, status={status}, exitCode={exit_code}, error={err}, "
                f"logsTail={tail[-2000:]}"
            )

        time.sleep(0.3)


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

