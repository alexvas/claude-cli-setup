**Русский** | [ English ](README.en.md) | [ 中文 ](README.zh.md)

Этот проект — среда для запуска агента Claude CLI в изолированном окружении Docker.

## Требования

- Docker Engine 24+ с [BuildKit](https://docs.docker.com/build/buildkit/) (включён по умолчанию в современных установках)
- Docker Compose v2 (`docker compose`, не `docker-compose` v1)

## Состав

| Файл | Назначение |
|------|------------|
| [claude.cli.agent.bootstrap.sh](claude.cli.agent.bootstrap.sh) | Установщик Claude Code (используется при сборке образа) |
| [Dockerfile](Dockerfile) | Multi-stage образ: Ubuntu 24.04, Claude, MCP, инструменты |
| [docker-compose.yml](docker-compose.yml) | Сервис `claude`, переменные из `.env` |
| [docker/compose.proj2.yml](docker/compose.proj2.yml) | Опциональный mount `PROJECT_PATH_2` (1:1 как на хосте) |
| [docker/compose.proj3.yml](docker/compose.proj3.yml) | Опциональный mount `PROJECT_PATH_3` (1:1 как на хосте) |
| [.env.example](.env.example) | Шаблон конфигурации |
| [docker/build_wrapper.py](docker/build_wrapper.py) | Подготовка сети (host gateway + SOCKS) и сборка образов |

Образ собирается под пользователем `dev` (UID/GID из `DEV_UID` / `DEV_GID`, по умолчанию 1000). На этапе сборки SOCKS на хосте (`0.0.0.0:${SOCKS_PORT}`) доступен из build-контейнера через IP шлюза хоста. В **rootful** Docker достаточно `docker compose build` (шлюз определяется автоматически). В **rootless** — [docker/build_wrapper.py](docker/build_wrapper.py) подбирает `HOST_GATEWAY_IP` через ephemeral HTTP-probe.

В образ входят: Python через `uv` (команда `python3` — wrapper/alias на `uv run python`), Yarn Berry, `vim`, `less`, `bat`, `git`, `openssh-client`, `gh`, `rpmbuild` (пакет `rpm`), MCP для filesystem, ripgrep, fetch, git, Rust (stable), uv/ty, Astro CLI, `build-essential`, локаль `ru_RU.UTF-8` и удалённая документация Astro.

## Подготовка

1. Скопируйте конфигурацию:

```bash
cp .env.example .env
```

2. Отредактируйте `.env`:

- `SOCKS_PORT` — порт SOCKS-прокси на **хосте** (для скачивания Claude при сборке; прокси должен слушать `0.0.0.0:${SOCKS_PORT}`).
- `HOST_GATEWAY_IP` — опционально. **Rootful:** не задавайте (compose использует `host-gateway`, Dockerfile определяет IP моста). **Rootless:** выставляется `docker/build_wrapper.py build` после probe.
- `PROJECT_PATH_1` — обязательный путь к первому проекту на хосте.
- `PROJECT_PATH_2`, `PROJECT_PATH_3` — при необходимости; подключите фрагменты через `COMPOSE_FILE` (см. ниже).
- **Rootless Docker:** используйте [docker/build_wrapper.py](docker/build_wrapper.py); при необходимости он предложит [docker/apply-rootless-port-forward.sh](docker/apply-rootless-port-forward.sh).
- `CLAUDE_TARGET` — цель установщика Claude при сборке: `stable`, `latest` или конкретная версия `X.Y.Z` (по умолчанию `stable`).
- `DEV_UID`, `DEV_GID` — UID/GID пользователя в контейнере; **обязательно** выровняйте с владельцем каталога проекта на хосте (`id -u` / `id -g`), иначе bind-mount будет root-owned и git в контейнере сломается.

3. На хосте должны быть доступны SOCKS (на время сборки).

### Проекты на хосте (1–3 каталога)

| Сценарий | `COMPOSE_FILE` в `.env` |
|----------|-------------------------|
| Один проект | `docker-compose.yml` |
| Два проекта | `docker-compose.yml:docker/compose.proj2.yml` (+ `PROJECT_PATH_2`) |
| Три проекта | `…:docker/compose.proj2.yml:docker/compose.proj3.yml` (+ `PROJECT_PATH_3`) |

Пути в контейнере совпадают с хостовыми (bind-mount 1:1).

Проверка итоговой конфигурации (секреты подставляются из `.env`; **не публикуйте вывод**, если в нём есть ключи):

```bash
docker compose config
```

## Безопасность

- Не коммитьте `.env` и не кладите в репозиторий API-ключи.
- `docker compose config` раскрывает подставленные значения переменных — не вставляйте этот вывод в тикеты и логи CI.
- Ротируйте API-ключ при утечке; обновите `.env` и перезапустите контейнер.
- Образ собирается с доступом к SOCKS только на этапе build.

## Сборка образа

Требуется SOCKS на хосте (`0.0.0.0:${SOCKS_PORT}`).

### Rootful Docker (по умолчанию)

```bash
docker compose build claude
```

### Rootless Docker

Обёртка: диагностика → при необходимости systemd override → запись `.env` → сборка:

```bash
python3 docker/build_wrapper.py diagnose
python3 docker/build_wrapper.py apply -y
python3 docker/build_wrapper.py build -y
```

Флаг `-y`/`--yes` можно указать до или после подкоманды (`-y build` или `build -y`).

Ручная сборка rootless (если `HOST_GATEWAY_IP` уже в `.env`):

```bash
docker compose build claude
```

Другая версия Claude при сборке:

```bash
CLAUDE_TARGET=latest docker compose build claude
```

Полная пересборка без кэша:

```bash
docker compose build --no-cache claude
```

## Команды Docker Compose

| Команда | Назначение |
|---------|------------|
| `docker compose build claude` | Собрать образ |
| `docker compose build --no-cache claude` | Собрать образ с нуля |
| `docker compose run claude` | Запустить контейнер (bash по умолчанию); контейнер остаётся после выхода |
| `docker compose run --rm claude` | То же, но удалить контейнер после выхода |
| `docker compose run --rm claude claude` | Сразу запустить Claude CLI |
| `docker compose run --rm claude bash -lc 'claude --version'` | Проверить установку Claude |
| `docker compose run --rm claude bash -lc 'claude mcp list'` | Список MCP-серверов |

Флаг `--rm` удобен для одноразовых сессий; без него контейнер можно снова запустить через `docker compose start`.

## Переменные в контейнере

При `docker compose run` в контейнер передаются (из `.env`):

- `ANTHROPIC_BASE_URL` ← URL Anthropic-совместимого API (прямой эндпоинт или прокси)
- `ANTHROPIC_AUTH_TOKEN` ← API-ключ (опционален)
- `ANTHROPIC_MODEL` ← из `.env` (по умолчанию `deepseek-v4-pro[1m]`)
- `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL` ← DeepSeek
- `ANTHROPIC_DEFAULT_HAIKU_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL` ← deepseek-flash или локальная Ollama/llamacpp модель
- `CLAUDE_CODE_EFFORT_LEVEL` ← из `.env`

## Устранение неполадок

- **Сборка падает на bootstrap** — проверьте `SOCKS_PORT` (SOCKS на хосте слушает `0.0.0.0`). Rootful: `docker compose build claude` без `build_wrapper`. Rootless: `python3 docker/build_wrapper.py diagnose`; при необходимости `docker/apply-rootless-port-forward.sh`.
- **Ошибка `UnsupportedProxyProtocol`** — для шага установки Claude используется `fetch`, который часто не понимает `socks5://` напрямую; в этом образе это обходится через локальный HTTP bridge (`privoxy`).
- **Нет второго проекта в контейнере** — задайте `PROJECT_PATH_2` и добавьте `docker/compose.proj2.yml` в `COMPOSE_FILE`.
- **Пустой `PROJECT_PATH_2` в compose** — не подключайте фрагмент `compose.proj2.yml`, иначе Compose потребует непустой путь.
- **EACCES при записи в рабочий каталог** — по умолчанию при старте entrypoint делает `chown -R dev:dev` на смонтированные каталоги (`CHOWN_WORK_ON_START=1`). Это меняет владельца файлов и на хосте. Отключить: `CHOWN_WORK_ON_START=0` в `.env` и выровняйте права на хосте вручную (`chown` + `DEV_UID`/`DEV_GID` = `id -u` / `id -g`).
- **`python3` / `pip` не найдены** — пересоберите образ (`docker compose build claude`). `python3` вызывает `uv run python`; `pip` — alias на `uv pip --system` (в интерактивном shell). Вне проекта для установки пакетов используйте `uv pip install --system …` или `uv run` внутри venv проекта.
- **`rustc` / `cargo` не работают** — пересоберите образ; в runtime копируется toolchain из builder (`~/.rustup`).
