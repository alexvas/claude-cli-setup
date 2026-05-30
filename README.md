Этот проект — среда для запуска агента Claude CLI в изолированном окружении Docker.

Агент использует [DeepSeek Anthropic API](https://api-docs.deepseek.com/guides/anthropic_api) и локальную [Ollama](https://ollama.com/) на хосте.

## Требования

- Docker Engine 24+ с [BuildKit](https://docs.docker.com/build/buildkit/) (включён по умолчанию в современных установках)
- Docker Compose v2 (`docker compose`, не `docker-compose` v1)

## Состав

| Файл | Назначение |
|------|------------|
| [claude.cli.agent.bootstrap.sh](claude.cli.agent.bootstrap.sh) | Установщик Claude Code (используется при сборке образа) |
| [Dockerfile](Dockerfile) | Multi-stage образ: Ubuntu 24.04, Claude, MCP, инструменты |
| [docker-compose.yml](docker-compose.yml) | Сервис `claude`, переменные из `.env` |
| [docker/compose.proj2.yml](docker/compose.proj2.yml) | Опциональный mount `/home/work/proj2` |
| [docker/compose.proj3.yml](docker/compose.proj3.yml) | Опциональный mount `/home/work/proj3` |
| [.env.example](.env.example) | Шаблон конфигурации |

Образ собирается под пользователем `dev` (UID/GID из `DEV_UID` / `DEV_GID`, по умолчанию 1000). SOCKS нужен только на этапе **`docker compose build`**: в builder-стадии поднимается локальный HTTP bridge (`privoxy`), который форвардит в `SOCKS_HOST:SOCKS_PORT`, и уже его адрес передаётся в `HTTP_PROXY`/`HTTPS_PROXY`.

В образ входят: Yarn Berry, `vim`, `git`, MCP для filesystem, ripgrep, fetch, git, Cargo, uv/ty, Astro CLI и удалённая документация Astro.

## Подготовка

1. Скопируйте конфигурацию:

```bash
cp .env.example .env
```

2. Отредактируйте `.env`:

- `SOCKS_PORT` — порт SOCKS-прокси на **хосте** (для скачивания Claude при сборке).
- `SOCKS_HOST` — IP/хост прокси, **доступный из сборочного контейнера** (обычно LAN-IP машины, не `127.0.0.1`). Обязателен при **rootless Docker** (нет `docker0`). Прокси должен слушать `0.0.0.0:${SOCKS_PORT}`.
- `PROJECT_PATH_1` — обязательный путь к первому проекту на хосте.
- `PROJECT_PATH_2`, `PROJECT_PATH_3` — при необходимости; подключите фрагменты через `COMPOSE_FILE` (см. ниже).
- `DEEPSEEK_API_KEY` — **обязательный** ключ DeepSeek (без него `docker compose run` завершится с ошибкой).
- `OLLAMA_PORT` — порт Ollama на хосте (по умолчанию `11434`).
- `NODE_VERSION`, `YARN_VERSION`, `ASTRO_VERSION` — версии при сборке (по умолчанию `22.12.0`, `4.15.0`, `6.4.2`).
- `CLAUDE_TARGET` — цель установщика Claude при сборке: `stable`, `latest` или конкретная версия `X.Y.Z` (по умолчанию `stable`).
- `DEV_UID`, `DEV_GID` — UID/GID пользователя в контейнере; задайте под вашего пользователя на хосте, чтобы bind-mount не ломал права на файлы.
- `ANTHROPIC_MODEL` — модель для Claude Code в контейнере (по умолчанию `deepseek-chat`).

3. На хосте должны быть доступны SOCKS (на время сборки) и Ollama (на время работы контейнера). Для Ollama из контейнера часто нужно слушать все интерфейсы, например `OLLAMA_HOST=0.0.0.0 ollama serve`.

### Проекты на хосте (1–3 каталога)

| Сценарий | `COMPOSE_FILE` в `.env` |
|----------|-------------------------|
| Один проект | `docker-compose.yml` |
| Два проекта | `docker-compose.yml:docker/compose.proj2.yml` (+ `PROJECT_PATH_2`) |
| Три проекта | `…:docker/compose.proj2.yml:docker/compose.proj3.yml` (+ `PROJECT_PATH_3`) |

В контейнере пути: `/home/work/proj1`, `/home/work/proj2`, `/home/work/proj3`.

Проверка итоговой конфигурации (секреты подставляются из `.env`; **не публикуйте вывод**, если в нём есть ключи):

```bash
docker compose config
```

## Безопасность

- Не коммитьте `.env` и не кладите в репозиторий `DEEPSEEK_API_KEY`.
- `docker compose config` раскрывает подставленные значения переменных — не вставляйте этот вывод в тикеты и логи CI.
- Ротируйте ключ DeepSeek при утечке; обновите `.env` и перезапустите контейнер.
- Образ собирается с доступом к SOCKS только на этапе build; runtime-стадия не содержит `privoxy` и build-only пакетов вроде `build-essential`.

## Сборка образа

Требуется работающий SOCKS на хосте (`SOCKS_HOST:SOCKS_PORT` из `.env`). Проверка: `docker run --rm ubuntu:24.04 bash -c 'apt-get update -qq && apt-get install -y -qq netcat-openbsd >/dev/null && nc -zv -w 3 <SOCKS_HOST> <SOCKS_PORT>'`.

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
| `docker compose run --rm claude bash -lc 'curl -s "$OLLAMA_HOST/api/tags"'` | Проверить доступ к Ollama на хосте |

Флаг `--rm` удобен для одноразовых сессий; без него контейнер можно снова запустить через `docker compose start`.

## Переменные в контейнере

При `docker compose run` в контейнер передаются (из `.env`):

- `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`
- `ANTHROPIC_AUTH_TOKEN` ← `DEEPSEEK_API_KEY` (обязателен)
- `ANTHROPIC_MODEL` ← из `.env` (по умолчанию `deepseek-chat`)
- `OLLAMA_HOST=http://host.docker.internal:${OLLAMA_PORT}`

Подробнее: [интеграция Claude Code с DeepSeek](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code).

## Устранение неполадок

- **Сборка падает на bootstrap** — проверьте `SOCKS_HOST` и `SOCKS_PORT`; из контейнера должен проходить `nc -zv -w 3 <SOCKS_HOST> <SOCKS_PORT>`. При rootless Docker `172.17.0.1` обычно неверен.
- **Ошибка `UnsupportedProxyProtocol`** — для шага установки Claude используется `fetch`, который часто не понимает `socks5://` напрямую; в этом образе это обходится через локальный HTTP bridge (`privoxy`).
- **`set DEEPSEEK_API_KEY` при run** — задайте ключ в `.env`; без него Compose не поднимет сервис.
- **Ollama недоступна из контейнера** — убедитесь, что Ollama слушает интерфейс, доступный с `host.docker.internal`, и что порт совпадает с `OLLAMA_PORT`.
- **Нет proj2 в контейнере** — задайте `PROJECT_PATH_2` и добавьте `docker/compose.proj2.yml` в `COMPOSE_FILE`.
- **Пустой `PROJECT_PATH_2` в compose** — не подключайте фрагмент `compose.proj2.yml`, иначе Compose потребует непустой путь.
- **Права на файлы в bind-mount** — выровняйте `DEV_UID` и `DEV_GID` с `id -u` / `id -g` на хосте.
