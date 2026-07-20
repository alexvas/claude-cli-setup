[ Русский ](README.md) | [ English ](README.en.md) | **中文**

# Pi Docker runtime

用于运行 π coding agent 和开发工具的隔离 Docker 环境。

## 要求

- Docker Engine 24+，启用 BuildKit
- Docker Compose v2（`docker compose`）

## 内容

| 文件 | 用途 |
|------|------|
| `Dockerfile` | Pi 和开发工具的多阶段镜像 |
| `docker-compose.yml` | Compose 服务 `pi` |
| `docker/compose.proj2.yml`、`docker/compose.proj3.yml` | 可选项目挂载 |
| `docker/build_wrapper.py` | 主机网关诊断和构建封装 |
| `launch-pi.py` | 项目选择 TUI 和容器启动器 |
| `.env.example` | 配置模板 |

镜像包含 `pi`、OpenSpec、Rust、`uv`、`ty`、`rtk`、`fd`、Yarn Berry、MCP、git、zsh、vim、jq、ripgrep 等工具。容器使用 `dev` 用户运行；`DEV_UID`/`DEV_GID` 必须与主机文件所有者一致。

## 设置

```bash
cp .env.example .env
```

在 `.env` 中设置：

- `PROJECT_PATH_1` — 必需的第一个项目路径；
- `PROJECT_PATH_2`、`PROJECT_PATH_3` — 可选的其他项目；
- `COMPOSE_FILE` — 基础 Compose 文件和所需 fragments；
- `HOST_GATEWAY_IP` — rootless Docker 的主机地址，通常由 wrapper 设置；
- `DEV_UID`、`DEV_GID` — 容器 `dev` 用户的 UID/GID。

`SOCKS_PORT`、`SOCKS_HOST` 和 `EXTERNAL_IP` 不再用于镜像构建，也不属于受支持的接口。容器运行时通过 `host.docker.internal` 访问主机服务。

检查最终配置（输出可能包含密钥）：

```bash
docker compose config
```

## 构建

Rootful Docker：

```bash
docker compose build pi
```

Rootless Docker：

```bash
python3 docker/build_wrapper.py diagnose
python3 docker/build_wrapper.py apply -y
python3 docker/build_wrapper.py build -y
```

wrapper 会将检测到的 `HOST_GATEWAY_IP` 写入 `.env`，保留运行时主机映射，并构建 `pi` 服务。

完全重建：

```bash
docker compose build --no-cache pi
```

## 运行

```bash
docker compose run --rm pi
docker compose run --rm pi pi --version
docker compose run --rm pi bash -lc 'openspec --help'
python3 launch-pi.py
```

`launch-pi.py` 可以选择最多三个项目，并运行 `docker compose run ... pi`。其他项目通过 `docker/` 中的 fragments 挂载。

## Shell prompt

唯一支持的 prompt 文件是 `/home/dev/.pi-zsh-prompt`。不会加载其他 prompt 文件。

## Docker 存储清理

旧 prompt 名称可能仍存在于旧 rootless Docker 镜像的层中。不要手动删除 `~/.local/share/docker/containerd/` 下的文件。先检查存储：

```bash
docker system df -v
```

然后按需清理构建缓存或未使用的镜像：

```bash
docker builder prune
# 更激进地清理：
# docker builder prune -af
# docker image prune -a
```

除非确认 volumes 中没有需要的数据，否则不要使用 `--volumes`。

## 故障排除

- **没有主机网关** — 运行 `python3 docker/build_wrapper.py diagnose`；rootless Docker 必要时运行 `apply -y`。
- **缺少其他项目** — 设置 `PROJECT_PATH_2`/`PROJECT_PATH_3`，并将对应 fragment 加入 `COMPOSE_FILE`。
- **EACCES** — 检查 `DEV_UID`/`DEV_GID`，或设置 `CHOWN_WORK_ON_START=0` 后手动修复权限。
- **仍显示旧名称** — 更新 wrapper 和文档；服务及命令名称统一为 `pi`。
