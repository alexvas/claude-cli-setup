[ Русский ](README.md) | [ English ](README.en.md) | **中文**

# Pi Docker runtime

用于 Pi 和开发工具的隔离 Docker 环境。除 Debian 外，所有选定输入都保存在 `docker-constructor.toml`；不要在 README、`.env`、Dockerfile 或 Compose 中重复具体版本。

## 要求

- 启用 BuildKit 的 Docker Engine 24+
- 主机上的 Python 3

## 1. 构建环境

先验证已审核的清单，再构建镜像：

```bash
./docker/docker-constructor.py validate
./docker/docker-constructor.py build -y
```

构建不需要项目路径、`.env` 或可访问的 host gateway。gateway 诊断只用于运行时容器到主机的连通性；对于 rootless Docker，请在需要检查或修复该连通性时单独运行 `doctor`：

```bash
./docker/docker-constructor.py doctor
./docker/docker-constructor.py doctor --apply-rootless-override -y
```

显式 Python 版本覆盖方式：

```bash
./docker/docker-constructor.py build --override build.stages.toolchain.python.version=X.Y.Z
```

约束只接受完整 `X.Y.Z` 版本上的 `==, >, >=, <, <=`。通配符、不完整版本、OR 和 prerelease 会被拒绝，除非策略明确允许。清单固定已审核的非 Debian 输入，但 Debian 仓库和 BuildKit 元数据意味着不能保证逐字节相同的 OCI 镜像。

## 2. 启动环境

打开交互式项目选择器：

```bash
./docker/docker-constructor.py run --tui
```

选中的主项目会成为容器工作目录，并按相同绝对路径进行 1:1 bind mount。其他项目以 `PROJECT_PATH_2`、`PROJECT_PATH_3`……的形式连续编号进行 1:1 mount，无数量上限。主机 `~/.pi` 挂载到 `/home/dev/.pi`。可在 `.env` 设置 `BASE_PROJECT_DIR`，或传入 `--base-project-dir` 来选择 TUI 树根目录。

使用显式项目直接启动：

```bash
./docker/docker-constructor.py run -m /path/to/main --project /path/to/additional
```

### 运行时扩展工件

在 Docker 启动前，`run` 会在主机上选择已审核的运行时扩展，并将每个选定 tarball 写入私有的 content-addressed cache。首次启动时，如果选定工件尚未缓存，可能需要网络来获取已审核的工件。后续启动会复用已验证的 cache hit，不需要扩展工件网络访问，因此可以离线启动。

容器不会获得工件 URL 或 cache 目录。它只获得窄化的运行时投影，以及每个已选、已验证工件在 `/run/pi-cli/runtime-artifacts` 下的一个只读文件挂载；未选中的 cache 内容绝不会被挂载。如果 cache miss 无法下载、验证或发布，`run` 会在 Docker 启动前失败。没有公开的 prefetch 命令；缓存物化由 `run` 准备阶段负责。

## 3. 更新环境组件

### Pi 发布后的更新流程

1. 只检查 Pi 并请求可审核建议：

   ```bash
   ./docker/docker-constructor.py check-updates --only build.stages.pi-tools.pi --suggest
   ```

2. `--suggest` 是 **non-mutating**：核对上游发布，然后手动把接受的值及相关元数据应用到 `docker-constructor.toml` 的 `build.stages.pi-tools.pi`。
3. 验证并审查准确变更：

   ```bash
   ./docker/docker-constructor.py validate
   git diff -- docker-constructor.toml
   ```

4. 重新构建并验证运行时镜像：

   ```bash
   ./docker/docker-constructor.py build
   ./docker/docker-constructor.py verify
   ```

### 组件生命周期

| 类别 | 代表组件 | 安装位置 / 所有者 | 更新来源 |
|---|---|---|---|
| Base image | Node 基础镜像 | 镜像拥有的 OCI 层 | `docker-constructor.toml` 中的 Docker registry 元数据 |
| Toolchain | Rust、uv、Python、ty | builder/镜像拥有的路径 | Rust channel、GitHub、uv、PyPI |
| Node CLIs | Pi、OpenSpec | 镜像拥有的全局工具 | npm |
| Prebuilt binaries | rtk、fd | 镜像拥有的运行时二进制 | GitHub releases 和 checksums |
| Shell runtime | Oh My Zsh | 镜像中的 `/home/dev` 内容 | Git revision |
| Pi extensions | pi-read、usage、proxy、rtk 注册 | 主机挂载的 `/home/dev/.pi` | `runtime.pi-extensions` npm 元数据 |
| Debian packages | 系统工具和库 | 镜像系统路径 | APT；不属于 `docker-constructor.toml` 更新发现 |

更新其他托管组件时，找到清单路径，运行 `check-updates --only <path> --suggest`，手动审核并编辑，然后执行验证、diff 审查、重建和运行时验证。对于 `runtime.pi-extensions`，重建只更新镜像的有效清单，不更新挂载状态；请在"维护"中刷新。

### 更新检查控制项

- **交互审核：** `--only <provider-or-path>` 缩小范围；`--suggest` 添加 non-mutating TOML 建议。
- **自动化和策略：** `--json` 输出机器可读格式；`--strict` 在 provider 错误时失败；`--fail-on-outdated` 在存在更新时失败。
- **高级发现/缓存：** `--include-prerelease` 包含 prerelease；`--cache-ttl`、`--cache-dir` 和 `--no-cache` 控制更新发现 HTTP 缓存。

普通构建、验证、启动和扩展安装不会执行更新发现。

## 维护

### 验证镜像

```bash
./docker/docker-constructor.py verify
```

### 刷新挂载的 Pi extensions

更改 `runtime.pi-extensions` 后，挂载目标 Pi home 并启动容器 —— 入口点将自动通过 `docker.runtime_installer` 运行幂等安装程序：

```bash
./docker/docker-constructor.py run
```

### 修复主机所有权和权限

使用 rootless Docker 时，以下两种情况可能导致 `EACCES`：

1. 容器内的 Agent 无法修改主机用户创建的文件。
2. 主机用户无法修改或读取容器内创建的文件。

要让双方获得所需权限，请将目标目录的所有者和组设为 `docker-dev`，然后允许所有者和组读写：

```bash
sudo chown -R <docker-dev>:<docker-dev> /path/you-intend-to-own
chmod -R ug+rwX /path/you-intend-to-own
```

在 rootless Docker 配置中，`docker-dev` 用户和组通常对应 UID/GID `100999`。还需要将主机用户加入 `docker-dev` 组：

```bash
sudo usermod -aG <docker-dev> "$USER"
```

执行命令前请确认实际 UID/GID，并将递归权限更改限制在你打算拥有的目录中。

### 清理 Docker 存储和缓存

先检查占用，再只删除可丢弃的构建缓存：

```bash
docker system df -v
docker builder prune
```

仅在确实需要完全重置缓存/镜像时使用 `docker builder prune -af` 或 `docker image prune -a`。除非确认所有数据都可丢弃，否则不要使用 `--volumes`。

## 故障排除

- **挂载项目或 Pi home 出现 EACCES：** 比较主机所有权与运行时 UID/GID。可让 `CHOWN_WORK_ON_START=1` 修复实际 mount points，或禁用它并采用"维护"中的窄范围步骤。
- **更新 provider 不可用：** 稍后重试或检查缓存；仅在必须强制 provider 可用时使用 `--strict`。
