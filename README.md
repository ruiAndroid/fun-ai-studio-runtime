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

## 启动（示例）

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn runtime_agent.main:app --host 0.0.0.0 --port 7005
```

## API

- `GET /internal/health`
- `POST /agent/apps/deploy`
- `POST /agent/apps/stop`
- `GET /agent/apps/status?appId=...`


