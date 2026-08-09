**Русский** | [ English ](README.en.md) | [ 中文 ](README.zh.md)

# Pi Docker runtime

Изолированное Docker-окружение для Pi и инструментов разработки. Выбранные версии всех входов, кроме Debian, хранятся в `docker-constructor.toml`; не дублируйте их в README, `.env`, Dockerfile или Compose.

## Требования

- Docker Engine 24+ с BuildKit
- Python 3 на хосте

## 1. Сборка окружения

Проверьте конфигурацию версий и соберите образ:

```bash
./docker/docker-constructor.py validate
./docker/docker-constructor.py build -y
```

Для сборки не нужны путь проекта, `.env` и доступность host gateway. Диагностика gateway нужна только для соединения запущенного контейнера с хостом. Для rootless Docker запускайте `doctor` отдельно, когда это соединение нужно проверить или исправить:

```bash
./docker/docker-constructor.py doctor
./docker/docker-constructor.py doctor --apply-rootless-override -y
```

Явное переопределение версии Python:

```bash
./docker/docker-constructor.py build --override build.stages.toolchain.python.version=X.Y.Z
```

Ограничения поддерживают только `==, >, >=, <, <=` и полные версии `X.Y.Z`. Шаблоны, неполные версии, OR и prerelease запрещены, если политика явно не разрешает их. Конфигурация версий фиксирует проверенные входы, кроме Debian, но репозитории Debian и метаданные BuildKit не гарантируют побайтово одинаковый OCI-образ.

## Доступ к хосту (необязательно)

Обычные сборки и запуски не требуют соединения с хостом. Доступ к хосту **отключён по умолчанию**: не добавляйте `[runtime.host-access]` и не создавайте локальный компаньон, если не нужен собственный каталог кэша.

Чтобы контейнер мог обращаться к сервису на хосте, включите одну из двух проверяемых политик в `docker-constructor.toml`:

```toml
[runtime.host-access]
enabled = true
mode = "docker-gateway" # или "external-address"
# proxy-port = 1080      # необязательно; целое число 1–65535
```

Оба режима делают настроенный адрес доступным как `host.docker.internal` и `HOST_ACCESS_ADDRESS`. После настройки запускайте контейнер обычной командой `run`; отдельный параметр `run` не нужен.

### docker-gateway: doctor выбирает gateway Docker

Выберите этот режим, если gateway Docker — правильный маршрут к хосту. Один раз запустите doctor, чтобы диагностировать gateway и сохранить выбранный конкретный адрес:

```bash
./docker/docker-constructor.py doctor --inventory docker-constructor.toml
```

Doctor записывает `[host-access].address` в `docker-constructor.local.toml` рядом с `docker-constructor.toml`. Если адрес устарел после изменения сети, запустите doctor снова. При отсутствии адреса `run` завершится с инструкцией запустить doctor; обычный `run` никогда не опрашивает Docker и не меняет локальное состояние. Диагностику gateway, сохранение и исправление doctor выполняет только в режиме `docker-gateway`: для `external-address` и отключённого (`disabled`) доступа к хосту он не диагностирует, не перезаписывает, не сохраняет и не исправляет состояние.

### external-address: укажите адрес самостоятельно

Выберите этот режим, когда сервис хоста доступен по известному IP-адресу интерфейса хоста. Пользователь должен самостоятельно указать этот IP в локальном компаньоне; doctor не обнаруживает, не заменяет, не сохраняет и не исправляет состояние external-address:

```toml
# docker-constructor.toml
[runtime.host-access]
enabled = true
mode = "external-address"

# docker-constructor.local.toml
[host-access]
address = "192.0.2.10"
```

В этом режиме `address` должен быть IP-адресом; `host-gateway` не допускается. Сервис, доступный через `HOST_ACCESS_ADDRESS`, должен слушать интерфейс, доступный с этого адреса. Сервис, привязанный только к loopback, может остаться недоступным; правила брандмауэра также применяются.

### Локальный компаньон и пользовательские инвентари

Локальный компаньон содержит только машинно-зависимое состояние; он не может переопределять проверяемую политику, зависимости или `cache.ttl`. Канонический инвентарь `docker-constructor.toml` использует `docker-constructor.local.toml`. Выбранный пользовательский инвентарь, например `--inventory /work/custom.toml`, использует `/work/custom.local.toml` рядом с ним; возврата к локальному состоянию в корне репозитория нет.

### Необязательный прокси-порт и переменные окружения

Задавайте `proxy-port` только если приложениям нужен номер порта на хосте. Тогда конструктор устанавливает `HOST_PROXY_PORT=<port>`; оба режима устанавливают `HOST_ACCESS_ADDRESS=<address>`. Это нейтральные переменные адреса и порта: конструктор не выбирает протокол прокси, не строит proxy URL и не устанавливает `PI_PROXY_URL`, `HTTP_PROXY`, `HTTPS_PROXY` или `ALL_PROXY`.

### Настройки кэша

Храните переносимую политику кэша в проверяемом инвентаре, а машинно-зависимые пути — в локальном компаньоне:

```toml
# docker-constructor.toml
[cache]
ttl = 3600

# docker-constructor.local.toml
[cache]
dir = "/home/dev/.cache/pi-docker"
```

`cache.ttl` относится к `docker-constructor.toml`; `cache.dir` допускается только в `docker-constructor.local.toml`. Если `[cache].dir` отсутствует, используется существующий XDG-каталог кэша по умолчанию. Для локального каталога кэша доступ к хосту включать не требуется.

## 2. Запуск окружения

Откройте интерактивный выбор проектов:

```bash
./docker/docker-constructor.py run --tui
```

Основной проект становится рабочим каталогом контейнера и монтируется 1:1 по тому же абсолютному пути. Дополнительные проекты монтируются 1:1 с последовательной нумерацией `PROJECT_PATH_2`, `PROJECT_PATH_3`, … без ограничения количества. Хостовый `~/.pi` монтируется в `/home/dev/.pi`. Корень дерева TUI можно задать через `BASE_PROJECT_DIR` в `.env` или `--base-project-dir`.

Прямой запуск с явно заданными проектами:

```bash
./docker/docker-constructor.py run -m /path/to/main --project /path/to/additional
```

### Runtime-артефакты расширений

До запуска Docker команда `run` выбирает проверенные runtime-расширения на хосте и материализует каждый выбранный tarball в приватный content-addressed cache. При первом запуске с отсутствующим артефактом сеть может понадобиться только для загрузки проверенных артефактов. Последующие запуски повторно используют верифицированные cache hits и не требуют сети для артефактов расширений, поэтому могут работать offline.

Контейнер не получает ни URL артефактов, ни каталог cache. Он получает только узкую runtime-проекцию и один read-only file mount для каждого выбранного верифицированного артефакта под `/run/pi-cli/runtime-artifacts`; невыбранное содержимое cache никогда не монтируется. Если cache miss не удаётся загрузить, проверить или опубликовать, `run` завершается до запуска Docker. Публичной команды prefetch нет: материализация cache выполняется при подготовке `run`.

## 3. Обновление компонентов окружения

### Обновление Pi после релиза

1. Проверьте только Pi и запросите предложение:

   ```bash
   ./docker/docker-constructor.py check-updates --only build.stages.pi-tools.pi --suggest
   ```

2. `--suggest` работает в режиме **non-mutating**: проверьте upstream-релиз и вручную внесите принятое значение и связанные метаданные в `build.stages.pi-tools.pi` файла `docker-constructor.toml`.
3. Проверьте конфигурацию версий и diff:

   ```bash
   ./docker/docker-constructor.py validate
   git diff -- docker-constructor.toml
   ```

4. Пересоберите и проверьте runtime-образ:

   ```bash
   ./docker/docker-constructor.py build
   ./docker/docker-constructor.py verify
   ```

### Жизненный цикл компонентов

| Категория | Примеры | Место установки / владелец | Источник обновления |
|---|---|---|---|
| Base image | Базовый Node | OCI-слои образа | Docker registry в `docker-constructor.toml` |
| Toolchain | Rust, uv, Python, ty | Пути builder/образа | Rust channel, GitHub, uv, PyPI |
| Node CLIs | Pi, OpenSpec | Глобальные инструменты образа | npm |
| Prebuilt binaries | rtk, fd | Runtime-бинарники образа | GitHub releases и checksums |
| Shell runtime | Oh My Zsh | Содержимое `/home/dev` в образе | Git revision |
| Pi extensions | pi-read, usage, proxy, регистрация rtk | Хостовое состояние `/home/dev/.pi` | npm-метаданные `runtime.pi-extensions` |
| Debian packages | Системные утилиты и библиотеки | Системные пути образа | APT; вне поиска обновлений `docker-constructor.toml` |

Для другого управляемого компонента найдите путь параметра в конфигурации, выполните `check-updates --only <path> --suggest`, вручную проверьте и примените изменение, затем запустите validate, просмотр diff, сборку и проверку. Для `runtime.pi-extensions` сборка обновляет итоговую конфигурацию версий образа, но не смонтированное состояние; обновите его в разделе «Обслуживание».

### Опции проверки обновлений

Чтобы проверить все управляемые компоненты, запустите команду без дополнительных опций:

```bash
./docker/docker-constructor.py check-updates
```

Она выводит сводный список компонентов и для каждого указывает, доступно ли обновление.

- **Интерактивный просмотр:** `--only <provider-or-path>` сужает поиск, `--suggest` добавляет non-mutating TOML-предложения.
- **Автоматизация и policy:** `--json` выдаёт машинный формат, `--strict` завершает работу при ошибке provider, `--fail-on-outdated` — при найденном обновлении.
- **Расширенный поиск и cache:** `--include-prerelease` включает prerelease; `--cache-ttl`, `--cache-dir` и `--no-cache` управляют HTTP-кэшем поиска.

Обычные сборка, validate, запуск и установка расширений никогда не ищут обновления.

## Обслуживание

### Проверка образа

```bash
./docker/docker-constructor.py verify
```

### Обновление смонтированных Pi extensions

После изменения `runtime.pi-extensions` запустите контейнер с примонтированным Pi home — точка входа автоматически выполнит идемпотентную установку через `docker.runtime_installer`:

```bash
./docker/docker-constructor.py run
```

### Исправление владельца и прав на хосте

При использовании rootless Docker ошибка `EACCES` может возникнуть в двух случаях:

1. Агент внутри контейнера не может изменить файл, созданный пользователем на хосте.
2. Пользователь на хосте не может изменить или прочитать файл, созданный внутри контейнера.

Чтобы предоставить обеим сторонам необходимые права, назначьте владельцем целевого каталога пользователя и группу `docker-dev`, а затем разрешите владельцу и группе чтение и запись:

```bash
sudo chown -R <docker-dev>:<docker-dev> /path/you-intend-to-own
chmod -R ug+rwX /path/you-intend-to-own
```

В конфигурации rootless Docker пользователю и группе `docker-dev`, как правило, соответствуют UID/GID `100999`. Пользователя хоста также необходимо добавить в группу `docker-dev`:

```bash
sudo usermod -aG <docker-dev> "$USER"
```

Перед выполнением команд проверьте фактические UID/GID и ограничьте рекурсивное изменение прав только каталогом, которым намерены владеть.

### Очистка Docker storage и кэша

Сначала проверьте использование, затем удаляйте только одноразовый build cache:

```bash
docker system df -v
docker builder prune
```

Используйте `docker builder prune -af` или `docker image prune -a` только для намеренного полного сброса. Не добавляйте `--volumes`, пока не убедитесь, что все данные одноразовые.

## Устранение неполадок

- **EACCES в смонтированном проекте или Pi home:** сравните владельца на хосте с runtime UID/GID. Разрешите `CHOWN_WORK_ON_START=1` исправить реальные mount points либо отключите его и примените узкую процедуру из «Обслуживания».
- **Provider обновлений недоступен:** повторите позже или проверьте кэш; включайте `--strict`, только если доступность provider обязательна.
