from typing import Dict


def labels_for_app(app_id: str, container_port: int, base_path: str = "") -> Dict[str, str]:
    # PathPrefix(`<basePath>`) + StripPrefix(`<basePath>`)
    # base_path 示例：/runtime/{appId}
    prefix = (base_path or "").strip()
    if not prefix:
        prefix = f"/runtime/{app_id}"
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    # 避免 /runtime/123/ 这种尾部斜杠造成匹配异常
    if len(prefix) > 1 and prefix.endswith("/"):
        prefix = prefix[:-1]
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


