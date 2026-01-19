def labels_for_app(app_id: str, container_port: int) -> dict[str, str]:
    # PathPrefix(`/apps/{appId}`) + StripPrefix(`/apps/{appId}`)
    prefix = f"/apps/{app_id}"
    router = f"rt-app-{app_id}"
    svc = f"rt-svc-{app_id}"
    mw = f"rt-mw-{app_id}"
    return {
        "traefik.enable": "true",
        f"traefik.http.routers.{router}.rule": f"PathPrefix(`{prefix}`)",
        f"traefik.http.routers.{router}.middlewares": mw,
        f"traefik.http.middlewares.{mw}.stripprefix.prefixes": prefix,
        f"traefik.http.services.{svc}.loadbalancer.server.port": str(container_port),
        f"traefik.http.routers.{router}.service": svc,
    }


