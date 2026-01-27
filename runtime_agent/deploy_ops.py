from runtime_agent import settings
from runtime_agent.docker_ops import docker, container_name
from runtime_agent.traefik_labels import labels_for_app


def ensure_network(network: str) -> None:
    if not network:
        return
    r = docker("network", "inspect", network, timeout_sec=10)
    if r.code == 0:
        return
    docker("network", "create", network, timeout_sec=30)


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

