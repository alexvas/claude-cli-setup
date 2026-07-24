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
./docker/versions.py compose config
```

## 版本管理

`versions.toml` 是所选 non-Debian 工具版本、revision、URL 和 digest 的唯一
受支持来源。不要在 `.env`、Dockerfile 或 Compose 中定义这些值。构建前可在
本地验证 inventory：

```bash
./docker/versions.py validate
```

Canonical build 始终使用 `./docker/versions.py compose`。对于底层集成，
以下命令输出 shell-safe `export` 行，可在手动调用 Compose 前加载：

```bash
./docker/versions.py env
```

将受支持的 override 显式传给 resolver：

```bash
./docker/versions.py compose --override stages.toolchain.python.version=X.Y.Z -- build pi
```

`versions.toml` 中的 override policy 与所选版本分离。受限语法只支持
`==, >, >=, <, <=` 和完整数字版本 `X.Y.Z`；逗号分隔的 clauses 表示 AND。
除非 policy 明确允许，否则 wildcard、OR、不完整版本和 prerelease 都会被拒绝。

更新发现只能显式运行，普通 build、launch、validate 和 runtime setup 路径
不会调用 provider：

```bash
./docker/versions.py check-updates
./docker/versions.py check-updates --only stages.toolchain.python --json
./docker/versions.py check-updates --suggest
./docker/versions.py check-updates --strict
./docker/versions.py check-updates --fail-on-outdated
```

默认模式为 best-effort：会报告不可用 provider，但构建不依赖它们。
`--strict` 将 provider failure 视为错误，`--fail-on-outdated` 用于 policy check。
`--suggest` 是 **non-mutating**：它输出可审查的 candidate values、URL 和已发布
checksum，但不会修改仓库。请手动将建议应用到 `versions.toml`，核对 upstream
release/checksum，运行 `validate`、测试和 canonical build，然后检查镜像中的
effective inventory。

可复现性边界：inventory 固定 non-Debian inputs，但不冻结 Debian repositories
或 BuildKit metadata，也不保证 byte-identical OCI image。Prebuilt `rtk`/`fd`
安装仍归已完成的 `split-rtk-fd-prebuilt` change 管理；挂载 Pi home 的 npm 扩展
安装仍归 `pin-pi-read-npm` 管理。共享 inventory 不替代这些 workflows。

## 构建

Rootful Docker：

```bash
./docker/versions.py compose build pi
```

Rootless Docker：

```bash
python3 docker/build_wrapper.py diagnose
python3 docker/build_wrapper.py apply -y
python3 docker/build_wrapper.py build -y
```

wrapper 会将检测到的 `HOST_GATEWAY_IP` 写入 `.env`，保留运行时主机映射，并构建 `pi` 服务。

镜像从任意工作目录提供配置的 uv-managed CPython 的直接 `python` 和 `python3` 可执行文件。它们不会运行 `uv run`，也不会同步项目环境。镜像不提供独立的 `pip` 或 `pip3` 命令；请显式使用，例如 `uv pip install --python "$(command -v python3)" <package>`。

构建时可以明确覆盖 Python 版本：

```bash
./docker/versions.py compose --override stages.toolchain.python.version=X.Y.Z -- build pi
```

完全重建：

```bash
./docker/versions.py compose build --no-cache pi
```

### BuildKit 缓存验证

使用普通进度输出，以区分已缓存和实际执行的步骤：

```bash
./docker/versions.py compose -- --progress plain build pi 2>&1 | tee /tmp/pi-build-1.log
./docker/versions.py compose -- --progress plain build pi 2>&1 | tee /tmp/pi-build-2.log
```

第二次构建应完全使用缓存。定向失效测试 — 编辑 ``versions.toml`` 中的
单个版本项（如 Pi 或 OpenSpec），重新构建，然后还原编辑：

```bash
./docker/versions.py compose -- --progress plain build pi 2>&1 | tee /tmp/pi-cache-test.log
```

仅修改 Pi 应只重新构建 Pi 安装及最终组装（保留 OpenSpec 缓存层）。
仅修改 OpenSpec 应使 OpenSpec 层失效，但保留 Pi 安装缓存。

验证 `dev` 用户下的运行时工具：

```bash
./docker/verify-runtime.sh pi-cli-pi:latest
```

### 安装 Pi 扩展和注册 rtk

Pi 扩展和 rtk 集成通过受保护的脚本安装到挂载的主机
`/home/dev/.pi` 目录中，而非写入镜像。首次启动容器后，运行：

```bash
./docker/versions.py compose run --rm pi /home/dev/install-pi-extensions.sh
```

脚本安装固定版本的 `@arcanemachine/pi-read`、`@llblab/pi-codex-usage`、
`pi-proxy`，并为 Pi 注册 `rtk`。重复运行安全——
安装是幂等的。未挂载 `/home/dev/.pi` 时脚本会报错退出。

BuildKit 缓存可以使用 `docker builder prune` 清理；只有需要完全重置
缓存时才使用 `-af`。

## 运行

```bash
./docker/versions.py compose run --rm pi
./docker/versions.py compose run --rm pi pi --version
./docker/versions.py compose run --rm pi bash -lc 'openspec --help'
./docker/verify-runtime.sh pi-cli-pi:latest
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
- **EACCES** — `CHOWN_WORK_ON_START` 修复作为挂载点（`mountpoint -q`）的 `PROJECT_PATH_*` 路径和 `/home/dev/.pi`。检查 `DEV_UID`/`DEV_GID`，或设置 `CHOWN_WORK_ON_START=0` 后手动修复权限。验证镜像内权限：`./docker/verify-runtime.sh pi-cli-pi:latest`。
- **仍显示旧名称** — 更新 wrapper 和文档；服务及命令名称统一为 `pi`。
