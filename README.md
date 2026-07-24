**Русский** | [ English ](README.en.md) | [ 中文 ](README.zh.md)

# Pi Docker runtime

Изолированное Docker-окружение для Pi и инструментов разработки. Выбранные версии всех входов, кроме Debian, хранятся в `docker-constructor.toml`; не дублируйте их в README, `.env`, Dockerfile или Compose.

## Требования

- Docker Engine 24+ с BuildKit
- Docker Compose v2
- Python 3 на хосте

## 1. Сборка окружения

Проверьте конфигурацию версий и соберите сервис `pi`:

```bash
./docker/versions.py validate
./docker/versions.py compose build pi
```

Для сборки не нужны путь проекта и `.env`. Диагностика host gateway для rootless Docker:

```bash
python3 docker/build_wrapper.py diagnose
python3 docker/build_wrapper.py apply -y
python3 docker/build_wrapper.py build -y
```

`./docker/versions.py env` печатает безопасные для shell разрешённые входы сборки. Явное переопределение Python:

```bash
./docker/versions.py compose --override stages.toolchain.python.version=X.Y.Z -- build pi
```

Ограничения поддерживают только `==, >, >=, <, <=` и полные версии `X.Y.Z`. Шаблоны, неполные версии, OR и prerelease запрещены, если политика явно не разрешает их. Конфигурация версий фиксирует проверенные входы, кроме Debian, но репозитории Debian и метаданные BuildKit не гарантируют побайтово одинаковый OCI-образ.

## 2. Запуск окружения

Откройте интерактивный выбор проектов:

```bash
./launch-pi.py
```

Основной проект становится рабочим каталогом контейнера и монтируется 1:1 по тому же абсолютному пути. Можно выбрать до двух дополнительных 1:1-монтирований. Хостовый `~/.pi` монтируется в `/home/dev/.pi`. Корень дерева TUI можно задать через `BASE_PROJECT_DIR` в `.env` или `--base-project-dir`.

Низкоуровневый запуск доступен при заданном `PROJECT_PATH_1`:

```bash
./docker/versions.py compose run --rm pi
```

## 3. Обновление компонентов окружения

### Обновление Pi после релиза

1. Проверьте только Pi и запросите предложение:

   ```bash
   ./docker/versions.py check-updates --only stages.pi-tools.pi --suggest
   ```

2. `--suggest` работает в режиме **non-mutating**: проверьте upstream-релиз и вручную внесите принятое значение и связанные метаданные в `stages.pi-tools.pi` файла `docker-constructor.toml`.
3. Проверьте конфигурацию версий и diff:

   ```bash
   ./docker/versions.py validate
   git diff -- docker-constructor.toml
   ```

4. Пересоберите и проверьте runtime-образ:

   ```bash
   ./docker/versions.py compose build pi
   ./docker/verify-runtime.sh pi-cli-pi:latest
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
./docker/versions.py check-updates
```

Она выводит сводный список компонентов и для каждого указывает, доступно ли обновление.

- **Интерактивный просмотр:** `--only <provider-or-path>` сужает поиск, `--suggest` добавляет non-mutating TOML-предложения.
- **Автоматизация и policy:** `--json` выдаёт машинный формат, `--strict` завершает работу при ошибке provider, `--fail-on-outdated` — при найденном обновлении.
- **Расширенный поиск и cache:** `--include-prerelease` включает prerelease; `--cache-ttl`, `--cache-dir` и `--no-cache` управляют HTTP-кэшем поиска.

Обычные сборка, validate, запуск и установка расширений никогда не ищут обновления.

## Обслуживание

### Проверка образа

```bash
./docker/verify-runtime.sh pi-cli-pi:latest
```

### Обновление смонтированных Pi extensions

После изменения `runtime.pi-extensions` запустите контейнер с нужным Pi home и защищённый идемпотентный установщик:

```bash
./docker/versions.py compose run --rm pi /home/dev/install-pi-extensions.sh
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
