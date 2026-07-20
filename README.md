**Русский** | [ English ](README.en.md) | [ 中文 ](README.zh.md)

# Pi Docker runtime

Изолированная Docker-среда для запуска π coding agent и инструментов разработки.

## Требования

- Docker Engine 24+ с BuildKit
- Docker Compose v2 (`docker compose`)

## Состав

| Файл | Назначение |
|------|------------|
| `Dockerfile` | Multi-stage образ Pi и инструментов |
| `docker-compose.yml` | Compose-сервис `pi` |
| `docker/compose.proj2.yml`, `docker/compose.proj3.yml` | Дополнительные mounts проектов |
| `docker/build_wrapper.py` | Диагностика host gateway и сборка |
| `launch-pi.py` | TUI-выбор проектов и запуск контейнера |
| `.env.example` | Шаблон конфигурации |

В образ входят `pi`, OpenSpec, Rust, `uv`, `ty`, `rtk`, `fd`, Yarn Berry, MCP, git, zsh, vim, jq, ripgrep и другие инструменты. Контейнер работает от пользователя `dev`; `DEV_UID`/`DEV_GID` должны соответствовать владельцу файлов на хосте.

## Настройка

```bash
cp .env.example .env
```

Задайте в `.env`:

- `PROJECT_PATH_1` — обязательный путь к первому проекту;
- `PROJECT_PATH_2`, `PROJECT_PATH_3` — дополнительные проекты;
- `COMPOSE_FILE` — базовый compose и необходимые fragments;
- `HOST_GATEWAY_IP` — адрес хоста для rootless Docker, обычно задаётся wrapper;
- `DEV_UID`, `DEV_GID` — UID/GID пользователя `dev`.

Параметры `SOCKS_PORT`, `SOCKS_HOST` и `EXTERNAL_IP` больше не используются для сборки и удалены из поддерживаемого интерфейса. Доступ к host services во время работы контейнера обеспечивается через `host.docker.internal`.

Проверьте итоговую конфигурацию (вывод может содержать секреты):

```bash
docker compose config
```

## Сборка

Rootful Docker:

```bash
docker compose build pi
```

Rootless Docker:

```bash
python3 docker/build_wrapper.py diagnose
python3 docker/build_wrapper.py apply -y
python3 docker/build_wrapper.py build -y
```

Wrapper записывает обнаруженный `HOST_GATEWAY_IP` в `.env`, сохраняет runtime mapping и собирает именно сервис `pi`.

Для полного rebuild:

```bash
docker compose build --no-cache pi
```

## Запуск

```bash
docker compose run --rm pi

docker compose run --rm pi pi --version
docker compose run --rm pi bash -lc 'openspec --help'
python3 launch-pi.py
```

`launch-pi.py` позволяет выбрать до трёх проектов и запускает `docker compose run ... pi`. Дополнительные проекты подключаются fragments из `docker/`.

## Shell prompt

Единственный поддерживаемый prompt-файл — `/home/dev/.pi-zsh-prompt`. Другие prompt-файлы не загружаются.

## Очистка Docker storage

Старые имена prompt могут находиться в слоях старых rootless Docker images. Не удаляйте файлы вручную из `~/.local/share/docker/containerd/`. Сначала проверьте использование:

```bash
docker system df -v
```

Затем при необходимости очистите build cache или неиспользуемые образы:

```bash
docker builder prune
# более агрессивно:
# docker builder prune -af
# docker image prune -a
```

Не используйте `--volumes`, если не проверили, что volumes не содержат нужные данные.

## Устранение неполадок

- **Нет host gateway** — запустите `python3 docker/build_wrapper.py diagnose`, для rootless при необходимости `apply -y`.
- **Нет дополнительного проекта** — задайте `PROJECT_PATH_2`/`PROJECT_PATH_3` и добавьте соответствующий fragment в `COMPOSE_FILE`.
- **EACCES** — проверьте `DEV_UID`/`DEV_GID` или отключите `CHOWN_WORK_ON_START=0` и исправьте права вручную.
- **Неожиданные старые имена** — обновите wrapper и README; сервис и команды имеют имя `pi`.
