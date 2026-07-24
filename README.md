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
python3 docker/versions.py compose config
```

## Управление версиями

`versions.toml` — единственный поддерживаемый источник выбранных версий,
ревизий, URL и digest для non-Debian инструментов. Не задавайте эти значения в
`.env`, Dockerfile или Compose. Перед сборкой можно выполнить локальную проверку:

```bash
python3 docker/versions.py validate
```

Canonical build всегда запускается через `python3 docker/versions.py compose`.
Для низкоуровневой интеграции команда ниже печатает shell-safe `export`-строки;
их можно загрузить в текущий shell перед ручным вызовом Compose:

```bash
python3 docker/versions.py env
```

Допустимые overrides передаются явно в resolver:

```bash
python3 docker/versions.py compose --override stages.toolchain.python.version=X.Y.Z -- build pi
```

Политика override хранится отдельно от выбранной версии в `versions.toml`.
Грамматика ограничена операторами `==, >, >=, <, <=` над полными числовыми
версиями `X.Y.Z`; clauses через запятую означают AND. Wildcards, OR, неполные
версии и prerelease запрещены, если policy явно не разрешает их.

Проверка обновлений выполняется только по явной команде и не участвует в
обычных build, launch, validate или runtime setup:

```bash
python3 docker/versions.py check-updates
python3 docker/versions.py check-updates --only stages.toolchain.python --json
python3 docker/versions.py check-updates --suggest
python3 docker/versions.py check-updates --strict
python3 docker/versions.py check-updates --fail-on-outdated
```

Обычный режим best-effort сообщает недоступные providers, но не делает сборку
зависимой от них. `--strict` превращает provider failures в ошибку;
`--fail-on-outdated` нужен для policy checks. `--suggest` — **non-mutating**:
он печатает reviewable candidate values, URL и опубликованные checksums, но не
редактирует репозиторий. Переносите предложение в `versions.toml` вручную,
проверяйте upstream release/checksum, запускайте `validate`, тесты и canonical
build, затем проверяйте effective inventory в образе.

Границы воспроизводимости: inventory фиксирует non-Debian inputs, но не
замораживает Debian repositories, BuildKit metadata и не гарантирует
byte-identical OCI image. Установка prebuilt `rtk`/`fd` остаётся в области
завершённого изменения `split-rtk-fd-prebuilt`, а установка npm-расширений в
смонтированный Pi home — `pin-pi-read-npm`; общий inventory не меняет ownership
этих workflows.

## Сборка

Rootful Docker:

```bash
python3 docker/versions.py compose build pi
```

Rootless Docker:

```bash
python3 docker/build_wrapper.py diagnose
python3 docker/build_wrapper.py apply -y
python3 docker/build_wrapper.py build -y
```

Wrapper записывает обнаруженный `HOST_GATEWAY_IP` в `.env`, сохраняет runtime mapping и собирает именно сервис `pi`.

Образ предоставляет прямые исполняемые файлы `python` и `python3` для настроенного CPython под управлением uv из любого каталога. Они не запускают `uv run` и не синхронизируют окружение проекта. Отдельных команд `pip` и `pip3` нет; устанавливайте пакеты явно, например `uv pip install --python "$(command -v python3)" <package>`.

Версию Python можно явно переопределить при сборке:

```bash
python3 docker/versions.py compose --override stages.toolchain.python.version=X.Y.Z -- build pi
```

Для полного rebuild:

```bash
python3 docker/versions.py compose build --no-cache pi
```

### Проверка кеширования BuildKit

Используйте обычный вывод прогресса, чтобы отличать кешированные шаги от выполненных:

```bash
python3 docker/versions.py compose -- --progress plain build pi 2>&1 | tee /tmp/pi-build-1.log
python3 docker/versions.py compose -- --progress plain build pi 2>&1 | tee /tmp/pi-build-2.log
```

Вторая сборка должна использовать кеш. Для тестирования инвалидации кеша —
измените версию в ``versions.toml`` (например, Pi или OpenSpec),
пересоберите и откатите правку:

```bash
python3 docker/versions.py compose -- --progress plain build pi 2>&1 | tee /tmp/pi-cache-test.log
```

Сборка с изменённым Pi должна пересобрать только установку Pi (сохраняя кеш
OpenSpec). Сборка с изменённым OpenSpec инвалидирует слой OpenSpec,
но сохраняет кеш установки Pi.
Проверка runtime-инструментов от имени `dev`:

```bash
./docker/verify-runtime.sh pi-cli-pi:latest
```

### Установка расширений Pi и регистрация rtk

Расширения Pi и интеграция rtk устанавливаются не в образ, а в смонтированную
хостовую директорию `/home/dev/.pi` через защищённый скрипт. После первого
запуска контейнера выполните:

```bash
python3 docker/versions.py compose run --rm pi /home/dev/install-pi-extensions.sh
```

Скрипт устанавливает закреплённые версии `@arcanemachine/pi-read`,
`@llblab/pi-codex-usage`, `pi-proxy` и регистрирует
`rtk` для Pi. Повторный запуск безопасен — установка идемпотентна.
Без смонтированной `/home/dev/.pi` скрипт завершится с ошибкой.

Кеш BuildKit можно освобождать командой `docker builder prune`; используйте
`-af` только для полного сброса кеша.

## Запуск

```bash
python3 docker/versions.py compose run --rm pi

python3 docker/versions.py compose run --rm pi pi --version
python3 docker/versions.py compose run --rm pi bash -lc 'openspec --help'
./docker/verify-runtime.sh pi-cli-pi:latest
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
- **EACCES** — `CHOWN_WORK_ON_START` исправляет права на смонтированных путях `PROJECT_PATH_*` и `/home/dev/.pi` (`mountpoint -q`). Проверьте `DEV_UID`/`DEV_GID` или установите `CHOWN_WORK_ON_START=0` и исправьте права вручную. Проверка прав образа: `./docker/verify-runtime.sh pi-cli-pi:latest`.
- **Неожиданные старые имена** — обновите wrapper и README; сервис и команды имеют имя `pi`.
