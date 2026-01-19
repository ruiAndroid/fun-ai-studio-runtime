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


def deploy_container(app_id: str, image: str, container_port: int) -> str:
    name = container_name(app_id)

    ensure_network(settings.RUNTIME_DOCKER_NETWORK)

    # pull image (optional but helpful)
    docker("pull", image, timeout_sec=300)

    # remove existing
    docker("rm", "-f", name, timeout_sec=30)

    args = ["run", "-d", "--restart=always", "--name", name]

    if settings.RUNTIME_DOCKER_NETWORK:
        args += ["--network", settings.RUNTIME_DOCKER_NETWORK]

    if settings.RUNTIME_TRAEFIK_ENABLE:
        for k, v in labels_for_app(app_id, container_port).items():
            args += ["--label", f"{k}={v}"]

    # no host port publishing; traffic goes via gateway container network
    args += [image]

    r = docker(*args, timeout_sec=120)
    if r.code != 0:
        raise RuntimeError(f"docker run failed: {r.err or r.out}")
    return name


def stop_container(app_id: str) -> None:
    docker("rm", "-f", container_name(app_id), timeout_sec=30)


