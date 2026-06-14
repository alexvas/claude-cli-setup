[ Русский ](README.md) | [ English ](README.en.md) | **中文**

本项目是在隔离的 Docker 环境中运行 Claude CLI 代理的运行时环境。

## 要求

- Docker Engine 24+，需启用 [BuildKit](https://docs.docker.com/build/buildkit/)（现代安装中默认启用）
- Docker Compose v2（`docker compose`，而非 `docker-compose` v1）

## 内容

| 文件 | 用途 |
|------|------|
| [claude.cli.agent.bootstrap.sh](claude.cli.agent.bootstrap.sh) | Claude Code 安装程序（在镜像构建时使用） |
| [Dockerfile](Dockerfile) | 多阶段镜像：Ubuntu 24.04、Claude、MCP、工具 |
| [docker-compose.yml](docker-compose.yml) | `claude` 服务，变量来自 `.env` |
| [docker/compose.proj2.yml](docker/compose.proj2.yml) | `PROJECT_PATH_2` 的可选挂载（与主机路径 1:1） |
| [docker/compose.proj3.yml](docker/compose.proj3.yml) | `PROJECT_PATH_3` 的可选挂载（与主机路径 1:1） |
| [.env.example](.env.example) | 配置模板 |
| [docker/build_wrapper.py](docker/build_wrapper.py) | 网络设置（主机网关 + SOCKS）和镜像构建 |

镜像为 `dev` 用户构建（UID/GID 来自 `DEV_UID` / `DEV_GID`，默认为 1000）。在构建阶段，主机 SOCKS 代理（`0.0.0.0:${SOCKS_PORT}`）可通过主机网关 IP 从构建容器访问。使用 **rootful** Docker 时，`docker compose build` 即可（网关自动检测）。使用 **rootless** 时，[docker/build_wrapper.py](docker/build_wrapper.py) 通过临时 HTTP 探测确定 `HOST_GATEWAY_IP`。

镜像包含：通过 `uv` 的 Python（`python3` 命令 — 是 `uv run python` 的封装/别名）、Yarn Berry、`vim`、`less`、`bat`、`git`、`openssh-client`、`gh`、`rpmbuild`（`rpm` 包）、用于 filesystem/ripgrep/fetch/git 的 MCP、Rust (stable)、uv/ty、Astro CLI、`build-essential`、`ru_RU.UTF-8` 区域设置以及远程 Astro 文档。

## 设置

1. 复制配置文件：

```bash
cp .env.example .env
```

2. 编辑 `.env`：

- `SOCKS_PORT` — **主机**上的 SOCKS 代理端口（用于在构建时下载 Claude；代理必须监听 `0.0.0.0:${SOCKS_PORT}`）。
- `HOST_GATEWAY_IP` — 可选。**Rootful：** 留空（compose 使用 `host-gateway`，Dockerfile 检测桥接 IP）。**Rootless：** 由 `docker/build_wrapper.py build` 在探测后设置。
- `PROJECT_PATH_1` — **必需**的主机第一个项目路径。
- `PROJECT_PATH_2`、`PROJECT_PATH_3` — 可选；通过 `COMPOSE_FILE` 包含片段（见下文）。
- **Rootless Docker：** 使用 [docker/build_wrapper.py](docker/build_wrapper.py)；如有需要，它会建议使用 [docker/apply-rootless-port-forward.sh](docker/apply-rootless-port-forward.sh)。
- `CLAUDE_TARGET` — 构建时 Claude 安装目标：`stable`、`latest` 或特定版本 `X.Y.Z`（默认 `stable`）。
- `DEV_UID`、`DEV_GID` — 容器内用户的 UID/GID；**必须**与主机上项目目录的所有者匹配（`id -u` / `id -g`），否则 bind-mount 将为 root 所有，容器内的 git 将无法正常工作。

3. 主机上必须可用 SOCKS（构建期间）。

### 主机项目（1–3 个目录）

| 场景 | `.env` 中的 `COMPOSE_FILE` |
|------|----------------------------|
| 一个项目 | `docker-compose.yml` |
| 两个项目 | `docker-compose.yml:docker/compose.proj2.yml`（+ `PROJECT_PATH_2`） |
| 三个项目 | `…:docker/compose.proj2.yml:docker/compose.proj3.yml`（+ `PROJECT_PATH_3`） |

容器内的路径与主机路径一致（1:1 bind-mount）。

验证最终配置（密钥从 `.env` 中替换；**不要发布**包含密钥的输出）：

```bash
docker compose config
```

## 安全

- 不要提交 `.env` 或将 API 密钥存储在仓库中。
- `docker compose config` 会显示替换后的变量值 — 不要将这些输出粘贴到工单或 CI 日志中。
- 如果密钥泄露，请轮换 API 密钥；更新 `.env` 并重启容器。
- 镜像仅在构建阶段可访问 SOCKS。

## 构建镜像

需要主机上的 SOCKS 代理（`0.0.0.0:${SOCKS_PORT}`）。

### Rootful Docker（默认）

```bash
docker compose build claude
```

### Rootless Docker

封装脚本：诊断 → 如有需要则进行 systemd 覆盖 → 写入 `.env` → 构建：

```bash
python3 docker/build_wrapper.py diagnose
python3 docker/build_wrapper.py apply -y
python3 docker/build_wrapper.py build -y
```

`-y`/`--yes` 标志可以放在子命令之前或之后（`-y build` 或 `build -y`）。

手动 rootless 构建（如果 `.env` 中已有 `HOST_GATEWAY_IP`）：

```bash
docker compose build claude
```

构建时使用不同的 Claude 版本：

```bash
CLAUDE_TARGET=latest docker compose build claude
```

无缓存完全重建：

```bash
docker compose build --no-cache claude
```

## Docker Compose 命令

| 命令 | 用途 |
|------|------|
| `docker compose build claude` | 构建镜像 |
| `docker compose build --no-cache claude` | 从头构建镜像 |
| `docker compose run claude` | 启动容器（默认 bash）；退出后容器保留 |
| `docker compose run --rm claude` | 同上，但退出后删除容器 |
| `docker compose run --rm claude claude` | 立即启动 Claude CLI |
| `docker compose run --rm claude bash -lc 'claude --version'` | 检查 Claude 安装 |
| `docker compose run --rm claude bash -lc 'claude mcp list'` | 列出 MCP 服务器 |

`--rm` 标志适用于一次性会话；不使用时，可以通过 `docker compose start` 重新启动容器。

## 容器环境变量

运行 `docker compose run` 时，以下变量会传递到容器中（来自 `.env`）：

- `ANTHROPIC_BASE_URL` ← Anthropic 兼容 API 地址（直接端点或代理）
- `ANTHROPIC_AUTH_TOKEN` ← API 密钥（可选）
- `ANTHROPIC_MODEL` ← 来自 `.env`（默认 `deepseek-v4-pro[1m]`）
- `ANTHROPIC_DEFAULT_OPUS_MODEL`、`ANTHROPIC_DEFAULT_SONNET_MODEL` ← DeepSeek
- `ANTHROPIC_DEFAULT_HAIKU_MODEL`、`CLAUDE_CODE_SUBAGENT_MODEL` ← deepseek-flash 或本地 Ollama/llamacpp 模型
- `CLAUDE_CODE_EFFORT_LEVEL` ← 来自 `.env`

## 故障排除

- **构建在 bootstrap 阶段失败** — 检查 `SOCKS_PORT`（主机上的 SOCKS 必须监听 `0.0.0.0`）。Rootful：直接使用 `docker compose build claude`（无需 `build_wrapper`）。Rootless：`python3 docker/build_wrapper.py diagnose`；如有需要，`docker/apply-rootless-port-forward.sh`。
- **容器中缺少第二个项目** — 设置 `PROJECT_PATH_2` 并将 `docker/compose.proj2.yml` 添加到 `COMPOSE_FILE`。
- **compose 中 `PROJECT_PATH_2` 为空** — 除非路径已设置，否则不要包含 `compose.proj2.yml` 片段。
- **写入工作目录时出现 EACCES** — 默认情况下，入口点在启动时对挂载目录运行 `chown -R dev:dev`（`CHOWN_WORK_ON_START=1`）。这也会更改主机上的文件所有权。禁用方法：在 `.env` 中设置 `CHOWN_WORK_ON_START=0`，并手动调整主机权限（`chown` + `DEV_UID`/`DEV_GID` = `id -u` / `id -g`）。
