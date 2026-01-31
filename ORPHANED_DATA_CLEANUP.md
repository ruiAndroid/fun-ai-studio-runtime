# 部署态孤立数据清理配置

## 概述

部署态孤立数据清理任务用于清理数据库中已删除的应用在 89 MongoDB 服务器上的残留数据。

## 清理内容

1. **MongoDB 数据库**：删除不在应用列表中的 `db_u{userId}_a{appId}` 数据库

## 执行时间

- 每天凌晨 3:00 执行（错开 workspace 的 2:00，避免同时查询数据库）

## 配置方式

### 方式 1：使用 cron（推荐）

在 102 服务器上配置 cron 任务：

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每天凌晨 3:00 执行）
0 3 * * * cd /opt/fun-ai-studio/fun-ai-studio-runtime && /usr/bin/python3 -m runtime_agent.orphaned_data_cleaner >> /data/funai/logs/orphaned-cleanup.log 2>&1
```

### 方式 2：使用 systemd timer

#### 1. 创建 service 文件

创建 `/etc/systemd/system/funai-runtime-cleanup.service`：

```ini
[Unit]
Description=FunAI Runtime Orphaned Data Cleanup
After=network.target

[Service]
Type=oneshot
User=root
WorkingDirectory=/opt/fun-ai-studio/fun-ai-studio-runtime
EnvironmentFile=/opt/fun-ai-studio/config/runtime.env
ExecStart=/usr/bin/python3 -m runtime_agent.orphaned_data_cleaner
StandardOutput=append:/data/funai/logs/orphaned-cleanup.log
StandardError=append:/data/funai/logs/orphaned-cleanup.log

[Install]
WantedBy=multi-user.target
```

#### 2. 创建 timer 文件

创建 `/etc/systemd/system/funai-runtime-cleanup.timer`：

```ini
[Unit]
Description=FunAI Runtime Orphaned Data Cleanup Timer
Requires=funai-runtime-cleanup.service

[Timer]
# 每天凌晨 3:00 执行
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

#### 3. 启用并启动 timer

```bash
# 重载 systemd 配置
systemctl daemon-reload

# 启用 timer（开机自启）
systemctl enable funai-runtime-cleanup.timer

# 启动 timer
systemctl start funai-runtime-cleanup.timer

# 查看 timer 状态
systemctl status funai-runtime-cleanup.timer

# 查看下次执行时间
systemctl list-timers funai-runtime-cleanup.timer
```

#### 4. 手动触发清理

```bash
# 手动执行一次清理
systemctl start funai-runtime-cleanup.service

# 查看执行日志
journalctl -u funai-runtime-cleanup.service -f
```

## 手动执行

如需手动执行清理任务：

```bash
cd /opt/fun-ai-studio/fun-ai-studio-runtime
python3 -m runtime_agent.orphaned_data_cleaner
```

## 依赖配置

清理任务依赖以下环境变量（在 `runtime.env` 中配置）：

```bash
# Deploy 服务地址（用于获取应用列表）
DEPLOY_BASE_URL=http://172.21.138.100:7002

# Runtime-Agent Token（用于认证）
RUNTIME_AGENT_TOKEN=8f3d1a6c9e0b4f2d7c5a1e9b6d3f0c8a2e7b4d1f9c6a3b0e5d8c2f7a1b9e4d0c

# MongoDB 配置（用于清理数据库）
RUNTIME_MONGO_HOST=172.21.138.89
RUNTIME_MONGO_PORT=27017
RUNTIME_MONGO_USERNAME=funai
RUNTIME_MONGO_PASSWORD=Ss123456!
RUNTIME_MONGO_AUTH_SOURCE=admin
```

## 日志查看

### cron 方式

```bash
tail -f /data/funai/logs/orphaned-cleanup.log
```

### systemd 方式

```bash
journalctl -u funai-runtime-cleanup.service -f
```

## 注意事项

1. **执行时间**：部署态清理任务在凌晨 3:00 执行，错开 workspace 的 2:00，避免同时查询数据库
2. **安全性**：清理任务只删除 `db_u*_a*` 格式的数据库，不会影响其他数据库
3. **幂等性**：清理任务可以重复执行，不会产生副作用
4. **失败处理**：清理失败不会影响应用正常运行，只会记录日志
5. **网络依赖**：清理任务需要访问 100 服务器（deploy）和 89 服务器（MongoDB）

## 监控建议

1. 定期检查清理日志，确保任务正常执行
2. 监控 MongoDB 磁盘使用情况，确保清理有效
3. 如果发现大量孤立数据，可以手动触发清理任务
