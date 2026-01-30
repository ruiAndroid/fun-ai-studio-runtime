# Runtime Harbor 认证配置升级

## 问题背景

之前runtime需要手动在102服务器上执行 `podman login` 来保存Harbor凭证，这种方式：
- 不便于自动化部署
- 容易在服务重启后失效
- 配置不统一（runner用配置文件，runtime用手动登录）

## 解决方案

现在runtime支持通过环境变量配置Harbor凭证，与runner保持一致。

## 修改内容

### 1. settings.py
添加了三个新的配置项：
- `REGISTRY_URL`: Harbor地址
- `REGISTRY_USERNAME`: Harbor用户名（推荐使用机器人账号）
- `REGISTRY_PASSWORD`: Harbor密码/Token

### 2. docker_ops.py
- 修改 `run()` 和 `docker()` 函数，支持 `stdin` 参数
- 用于安全地传递密码（不会暴露在进程列表中）

### 3. deploy_ops.py
- 添加 `ensure_registry_login()` 函数
- 在拉取镜像前自动登录Harbor
- 登录失败只警告不中断（兼容已有手动登录的场景）

### 4. config/runtime.env
添加配置示例：
```bash
REGISTRY_URL=172.21.138.103
REGISTRY_USERNAME=robot$robot-runner
REGISTRY_PASSWORD=<Harbor机器人Token>
```

## 使用方法

### 1. 在Harbor中创建机器人账号
1. 访问 `http://172.21.138.103`
2. 进入 `funaistudio` 项目 → Robot Accounts
3. 创建机器人账号，权限选择 `Pull Artifact`
4. 复制生成的Token

### 2. 更新102服务器配置
```bash
# 编辑配置文件
vi /opt/fun-ai-studio/config/runtime.env

# 添加或更新以下配置
REGISTRY_URL=172.21.138.103
REGISTRY_USERNAME=robot$robot-runner
REGISTRY_PASSWORD=<刚才复制的Token>

# 重启服务
sudo systemctl restart fun-ai-studio-runtime
```

### 3. 验证
重新部署一个应用，查看runtime日志，应该能看到自动登录和拉取镜像成功。

## 兼容性

- 如果不配置这些环境变量，runtime仍然使用系统中已保存的凭证（向后兼容）
- 如果配置了但登录失败，会打印警告但不中断流程
- 推荐配置环境变量，更易于管理和自动化

## 安全建议

1. 使用Harbor Robot Account而不是admin账号
2. Robot Account只给必要的权限（Runtime只需Pull）
3. 定期轮换Token
4. 不要将Token提交到代码仓库
