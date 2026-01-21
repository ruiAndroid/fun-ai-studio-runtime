"""
Runtime-Agent 生产启动入口。

为什么要单独做入口：
- 直接用 `uvicorn runtime_agent.main:app`（CLI）时，uvicorn 默认会应用自己的 logging config，
  可能覆盖我们在代码里配置的 file handler，导致日志不落盘。
- 这里用 uvicorn.run(..., log_config=None) 保留我们自己的 logging（app.log + gz rolling）。
"""

import uvicorn

from runtime_agent import settings
from runtime_agent.logging_setup import setup_logging


def main() -> None:
    setup_logging("fun-ai-studio-runtime")
    uvicorn.run(
        "runtime_agent.main:app",
        host=str(settings.RUNTIME_AGENT_HOST or "0.0.0.0"),
        port=int(settings.RUNTIME_AGENT_PORT or 7005),
        log_config=None,  # 关键：不要让 uvicorn 覆盖 logging handlers
        access_log=True,
    )


if __name__ == "__main__":
    main()


