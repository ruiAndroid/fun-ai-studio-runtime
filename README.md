# fun-ai-studio-runtime

Runtime 节点：运行用户应用容器，并提供一个 **Runtime-Agent（HTTP）** 给 Runner 调用。

## 组件

- Runtime-Agent：FastAPI（默认 `7005`）
- Docker：运行用户应用容器
- 网关：建议 Traefik（对外 80/443），按路径 `/apps/{appId}` 路由到容器

## 配置（环境变量）

- `RUNTIME_AGENT_HOST=0.0.0.0`
- `RUNTIME_AGENT_PORT=7005`
- `RUNTIME_AGENT_TOKEN=CHANGE_ME`（Runner 调用时通过 `X-Runtime-Token` 传入）
- `RUNTIME_NODE_NAME=rt-node-01`
- `RUNTIME_NODE_AGENT_BASE_URL=http://<this-node>:7005`
- `RUNTIME_NODE_GATEWAY_BASE_URL=https://<public-gateway>`
- `DEPLOY_BASE_URL=http://<deploy-host>:7002`
- `DEPLOY_NODE_TOKEN=<same as deploy.runtime-node-registry.shared-secret>`
- `RUNTIME_DOCKER_NETWORK=funai-runtime-net`（可选）
- `RUNTIME_TRAEFIK_ENABLE=true`（默认 true）

## 配置文件（推荐：EnvironmentFile）

- 仓库内提供：`config/runtime.env`（你们当前选择在内网环境直接提交）
- 部署时建议将其放到服务器：`/opt/fun-ai-studio/config/runtime.env`

systemd 方式加载（示例）：

- 在 `runtime-agent.service` 中加入：
  - `EnvironmentFile=/opt/fun-ai-studio/config/runtime.env`

## 启动（示例）

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m runtime_agent.serve
```

## API

- `GET /internal/health`
- `POST /agent/apps/deploy`
- `POST /agent/apps/stop`
- `GET /agent/apps/status?appId=...`

## 网关（Traefik）快速启动（Podman 推荐）

> 说明：runtime-agent 在部署容器时会打 Traefik labels，并把用户容器放入 `RUNTIME_DOCKER_NETWORK`。
> 因此要让 `http://<runtime-node>/apps/{appId}/...` 可访问，需要在同一网络里运行一个 Traefik 网关容器，并监听宿主机 `80/443`。

在 Runtime 节点（102）执行（以 `funai-runtime-net` 为例）：

```bash
# 1) 确保 podman socket 开启（Traefik 用它读取 labels）
sudo systemctl enable --now podman.socket

# 2) 确保网络存在（runtime-agent 也会 ensure，但这里提前做更直观）
sudo podman network create funai-runtime-net 2>/dev/null || true

# 3) 启动 Traefik（监听 80；需要 https 再加 443 及证书配置）
sudo podman rm -f funai-traefik 2>/dev/null || true
sudo podman run -d --name funai-traefik \
  --restart=always \
  --network funai-runtime-net \
  -p 80:80 \
  -v /run/podman/podman.sock:/var/run/docker.sock:Z \
  docker.io/traefik:v2.11 \
  --entrypoints.web.address=:80 \
  --providers.docker=true \
  --providers.docker.endpoint=unix:///var/run/docker.sock \
  --providers.docker.exposedbydefault=false

# 4) 验证 80 端口监听
ss -lntp | grep ':80' || true
```

如果你所在环境无法直连 DockerHub（拉取 `docker.io/traefik` 超时），建议先把镜像同步到你们 ACR，再从 ACR pull（同你们同步 gitea 的方式）。


