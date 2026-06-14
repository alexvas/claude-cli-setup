Этот проект — среда для запуска агента Claude CLI в изолированном окружении Docker.

Агент использует [DeepSeek Anthropic API](https://api-docs.deepseek.com/guides/coding_agents) и локальную [Ollama](https://ollama.com/) на хосте.

## Требования

- Docker Engine 24+ с [BuildKit](https://docs.docker.com/build/buildkit/) (включён по умолчанию в современных установках)
- Docker Compose v2 (`docker compose`, не `docker-compose` v1)

## Состав

| Файл | Назначение |
|------|------------|
| [claude.cli.agent.bootstrap.sh](claude.cli.agent.bootstrap.sh) | Установщик Claude Code (используется при сборке образа) |
| [Dockerfile](Dockerfile) | Multi-stage образ: Ubuntu 24.04, Claude, MCP, инструменты |
| [docker-compose.yml](docker-compose.yml) | Сервисы `claude` и `inf-splitter`, переменные из `.env` |
| [inf-splitter/README.md](inf-splitter/README.md) | Rust-роутер Anthropic API: local (Ollama) / remote (DeepSeek) |
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
- `DEEPSEEK_API_KEY` — **обязательный** ключ DeepSeek для контейнера `claude` (без него `docker compose run claude` завершится с ошибкой).
- `OLLAMA_PORT` — порт Ollama на хосте (по умолчанию `11434`).
- параметры `inf-splitter` (`LOCAL_MODELS`, `PROXY_PORT`, …) — см. [inf-splitter/README.md](inf-splitter/README.md).
- **Rootless Docker:** используйте [docker/build_wrapper.py](docker/build_wrapper.py); при необходимости он предложит [docker/apply-rootless-port-forward.sh](docker/apply-rootless-port-forward.sh).
- `NODE_VERSION`, `YARN_VERSION`, `ASTRO_VERSION` — версии при сборке (по умолчанию `22.12.0`, `4.15.0`, `6.4.2`).
- `CLAUDE_TARGET` — цель установщика Claude при сборке: `stable`, `latest` или конкретная версия `X.Y.Z` (по умолчанию `stable`).
- `DEV_UID`, `DEV_GID` — UID/GID пользователя в контейнере; **обязательно** выровняйте с владельцем каталога проекта на хосте (`id -u` / `id -g`), иначе bind-mount будет root-owned и git в контейнере сломается.
- `ANTHROPIC_MODEL` — основная модель Claude Code (по умолчанию `deepseek-v4-pro[1m]`).
- `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL` — DeepSeek-профили (по умолчанию `deepseek-v4-pro[1m]`).
- `ANTHROPIC_DEFAULT_HAIKU_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL` — локальные модели через Ollama (по умолчанию `gemma4:31b`).
- `CLAUDE_CODE_EFFORT_LEVEL` — уровень усилия Claude Code (по умолчанию `max`).

3. На хосте должны быть доступны SOCKS (на время сборки) и Ollama (на время работы контейнера). Для Ollama из контейнера часто нужно слушать все интерфейсы, например `OLLAMA_HOST=0.0.0.0 ollama serve`.

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

- Не коммитьте `.env` и не кладите в репозиторий `DEEPSEEK_API_KEY`.
- `docker compose config` раскрывает подставленные значения переменных — не вставляйте этот вывод в тикеты и логи CI.
- Ротируйте ключ DeepSeek при утечке; обновите `.env` и перезапустите контейнер.
- Образ собирается с доступом к SOCKS только на этапе build; runtime-стадия не содержит `privoxy`.

## Сборка образа

Требуется SOCKS на хосте (`0.0.0.0:${SOCKS_PORT}`).

### Rootful Docker (по умолчанию)

```bash
docker compose build inf-splitter
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
docker compose build inf-splitter
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
| `docker compose build inf-splitter` | Собрать роутер |
| `docker compose build --no-cache claude` | Собрать образ с нуля |
| `docker compose up -d inf-splitter` | Запустить роутер в фоне |
| `docker compose run claude` | Запустить контейнер (bash по умолчанию); контейнер остаётся после выхода |
| `docker compose run --rm claude` | То же, но удалить контейнер после выхода |
| `docker compose run --rm claude claude` | Сразу запустить Claude CLI |
| `docker compose run --rm claude bash -lc 'claude --version'` | Проверить установку Claude (работает без запущенного `inf-splitter`) |
| `docker compose run --rm claude bash -lc 'claude mcp list'` | Список MCP-серверов (работает без запущенного `inf-splitter`) |
| `docker compose run --rm claude bash -lc 'curl -s http://host.docker.internal:11434/api/tags'` | Проверить доступ к Ollama на хосте |

Флаг `--rm` удобен для одноразовых сессий; без него контейнер можно снова запустить через `docker compose start`.

## Маршрутизация через inf-splitter

Claude Code обращается к DeepSeek и Ollama через Rust-роутер `inf-splitter` (`ANTHROPIC_BASE_URL=http://inf-splitter:3000` внутри Docker-сети).

Перед сессией с API-запросами:

```bash
docker compose up -d inf-splitter
docker compose run --rm claude claude
```

Команды `claude --version` и `claude mcp list` работают без запущенного `inf-splitter`.

Маршрутизация моделей, переменные окружения, доступ к Ollama, HTTP API, сборка и troubleshooting — в [inf-splitter/README.md](inf-splitter/README.md).

## Переменные в контейнере

При `docker compose run` в контейнер передаются (из `.env`):

- `ANTHROPIC_BASE_URL=http://inf-splitter:3000` (см. [inf-splitter/README.md](inf-splitter/README.md))
- `ANTHROPIC_AUTH_TOKEN` ← `DEEPSEEK_API_KEY` (обязателен)
- `ANTHROPIC_MODEL` ← из `.env` (по умолчанию `deepseek-v4-pro[1m]`)
- `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL` ← DeepSeek
- `ANTHROPIC_DEFAULT_HAIKU_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL` ← локальная Ollama-модель
- `CLAUDE_CODE_EFFORT_LEVEL` ← из `.env`

Подробнее: [интеграция Claude Code с DeepSeek](https://api-docs.deepseek.com/guides/coding_agents).

## Устранение неполадок

- **Сборка падает на bootstrap** — проверьте `SOCKS_PORT` (SOCKS на хосте слушает `0.0.0.0`). Rootful: `docker compose build claude` без `build_wrapper`. Rootless: `python3 docker/build_wrapper.py diagnose`; при необходимости `docker/apply-rootless-port-forward.sh`.
- **Ошибка `UnsupportedProxyProtocol`** — для шага установки Claude используется `fetch`, который часто не понимает `socks5://` напрямую; в этом образе это обходится через локальный HTTP bridge (`privoxy`).
- **`set DEEPSEEK_API_KEY` при run claude** — задайте ключ в `.env`; без него Compose не поднимет контейнер `claude`.
- **Ollama недоступна из контейнера `claude`** — убедитесь, что Ollama слушает `0.0.0.0:${OLLAMA_PORT}`. Проверка: `curl -s http://host.docker.internal:11434/api/tags`.
- **Проблемы с `inf-splitter`** — см. [inf-splitter/README.md](inf-splitter/README.md#устранение-неполадок).
- **Ollama: Connection refused на `host.docker.internal` (rootless)** — выполните `docker/apply-rootless-port-forward.sh`, пересоздайте контейнеры (`docker compose up -d --force-recreate inf-splitter`). Проверка: `docker compose exec inf-splitter wget -qO- http://host.docker.internal:11434/api/tags`.
- **Нет второго проекта в контейнере** — задайте `PROJECT_PATH_2` и добавьте `docker/compose.proj2.yml` в `COMPOSE_FILE`.
- **Пустой `PROJECT_PATH_2` в compose** — не подключайте фрагмент `compose.proj2.yml`, иначе Compose потребует непустой путь.
- **EACCES при записи в рабочий каталог** — по умолчанию при старте entrypoint делает `chown -R dev:dev` на смонтированные каталоги (`CHOWN_WORK_ON_START=1`). Это меняет владельца файлов и на хосте. Отключить: `CHOWN_WORK_ON_START=0` в `.env` и выровняйте права на хосте вручную (`chown` + `DEV_UID`/`DEV_GID` = `id -u` / `id -g`).
- **`python3` / `pip` не найдены** — пересоберите образ (`docker compose build claude`). `python3` вызывает `uv run python`; `pip` — alias на `uv pip --system` (в интерактивном shell). Вне проекта для установки пакетов используйте `uv pip install --system …` или `uv run` внутри venv проекта.
- **`rustc` / `cargo` не работают** — пересоберите образ; в runtime копируется toolchain из builder (`~/.rustup`).
