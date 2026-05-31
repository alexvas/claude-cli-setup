# inf-splitter

Тонкий HTTP-роутер Anthropic Messages API для [claude-cli](../README.md): локальные модели → Ollama, остальные → DeepSeek Anthropic API.

Заменяет `anyllm-proxy`: без LiteLLM YAML, admin UI и SSRF-обходов через `/etc/hosts`.

**Прокси не управляет API-ключами.** В remote-режиме auth-заголовки клиента (`x-api-key`, `Authorization`, `anthropic-version` и др.) передаются в DeepSeek транзитом. Локальным моделям ключи не нужны. Ключ `DEEPSEEK_API_KEY` нужен только контейнеру `claude` (как `ANTHROPIC_AUTH_TOKEN`).

## Интеграция с docker-compose

Контейнер `claude` использует роутер как upstream Anthropic API:

- `ANTHROPIC_BASE_URL=http://inf-splitter:${PROXY_PORT:-3000}` (внутри Docker-сети)
- `ANTHROPIC_AUTH_TOKEN` ← `DEEPSEEK_API_KEY` из `.env` (задаётся в `claude`, не в `inf-splitter`)

Контейнер `claude` **не ждёт** health `inf-splitter`: `claude --version` и `claude mcp list` работают без запущенного роутера. Для полноценных API-запросов Claude Code роутер должен быть запущен:

```bash
docker compose up -d inf-splitter
docker compose run --rm claude claude
```

По умолчанию `ANTHROPIC_DEFAULT_HAIKU_MODEL` и `CLAUDE_CODE_SUBAGENT_MODEL` указывают на локальную модель (`gemma4:31b`), остальные профили Claude Code — на DeepSeek.

## Маршрутизация

```
Claude Code  --POST /v1/messages-->  inf-splitter
                                         |
                    model in LOCAL_MODELS |
                                         v
                                      Ollama (OpenAI-compatible /v1/chat/completions)
                                         |
                    иначе                v
                                         DeepSeek (/anthropic/v1/messages, passthrough)
```

| Модель | Куда |
|--------|------|
| из `LOCAL_MODELS` | Ollama (`anyllm_client` + `anyllm_translate`), без auth |
| любая другая | DeepSeek Anthropic API (байтовый passthrough + SSE relay) |

Remote-запросы: auth-заголовки клиента (`x-api-key`, `Authorization`) передаются как есть, без подмены на стороне прокси.

## HTTP API

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/health` | `{"status":"ok"}` |
| `GET` | `/v1/models` | Anthropic-совместимый список моделей (стабильный лексикографический порядок) |
| `POST` | `/v1/messages` | Anthropic Messages API (основной endpoint) |

### `GET /v1/models`

Ответ совместим с Anthropic Models API:

```json
{
  "data": [
    {
      "type": "model",
      "id": "deepseek-v4-pro[1m]",
      "display_name": "deepseek-v4-pro[1m]",
      "created_at": "2024-01-01T00:00:00.000Z"
    }
  ],
  "first_id": "deepseek-v4-pro[1m]",
  "last_id": "gemma4:31b",
  "has_more": false
}
```

Поля: `type`, `id`, `display_name`, `created_at`, envelope `first_id`, `last_id`, `has_more`. Порядок моделей детерминирован (лексикографическая сортировка по `id`).

## Переменные окружения

Конфигурация берётся из `.env` в корне проекта — см. [`.env.example`](../.env.example).

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `PROXY_PORT` | `3000` | Порт API роутера (внутри Docker-сети; задаётся в compose для `LISTEN_ADDR`) |
| `LOCAL_MODELS` | `gemma4:31b` | CSV whitelist моделей для Ollama |
| `LISTEN_ADDR` | `0.0.0.0:3000` | Адрес прослушивания (или из `PROXY_PORT` / `LISTEN_PORT`) |
| `DEEPSEEK_ANTHROPIC_BASE_URL` | `https://api.deepseek.com/anthropic` | Base URL DeepSeek Anthropic API |
| `DOCKER_NETWORK_MODE` | `rootful` | `rootful` или `rootless` — как достичь Ollama на хосте |
| `EXTERNAL_IP` | — | LAN-IP хоста (rootless Docker) |
| `SOCKS_HOST` | — | Fallback для `EXTERNAL_IP` в rootless-режиме |
| `OLLAMA_HOST_IP` | — | Deprecated alias для `EXTERNAL_IP` |
| `OLLAMA_PORT` | `11434` | Порт Ollama на хосте |
| `OLLAMA_BASE_URL` | — | Явный override URL Ollama (имеет приоритет над fallback) |
| `OMIT_STREAM_OPTIONS` | `true` (в compose) | Убрать `stream_options` из streaming-запросов к Ollama |
| `REMOTE_MODEL_IDS` | `deepseek-v4-pro[1m],…` | Модели для `GET /v1/models` (не влияет на роутинг) |

`DEEPSEEK_API_KEY` **не нужен** для `inf-splitter`.

### Вычисление URL Ollama

| Условие | URL |
|---------|-----|
| `OLLAMA_BASE_URL` задан | используется как есть |
| `DOCKER_NETWORK_MODE=rootful` | `http://host.docker.internal:${OLLAMA_PORT}` |
| `DOCKER_NETWORK_MODE=rootless` | `http://${EXTERNAL_IP:-$SOCKS_HOST}:${OLLAMA_PORT}` |
| rootless, IP не задан | сервис не стартует (fail-fast) |

При `rootless` без `EXTERNAL_IP`, `SOCKS_HOST` и `OLLAMA_BASE_URL` контейнер не стартует.

## Сборка и запуск

### Через Docker Compose (рекомендуется)

Из корня репозитория:

```bash
docker compose build inf-splitter
docker compose up -d inf-splitter
docker compose exec inf-splitter wget -qO- http://127.0.0.1:3000/health
docker compose exec inf-splitter wget -qO- http://127.0.0.1:3000/v1/models
```

### Локально (cargo)

```bash
cd inf-splitter
cargo build --release

export DOCKER_NETWORK_MODE=rootful
export LOCAL_MODELS=gemma4:31b
./target/release/inf-splitter
```

### Docker-образ отдельно

```bash
docker build -t inf-splitter .
docker run --rm -p 3000:3000 \
  -e DOCKER_NETWORK_MODE=rootful \
  --add-host=host.docker.internal:host-gateway \
  inf-splitter
```

## Структура кода

```
src/
├── main.rs      # точка входа, graceful shutdown
├── config.rs    # env, вычисление Ollama URL
├── router.rs    # маршруты axum, /v1/models
├── local.rs     # Ollama через anyllm_client (SSRF off)
├── remote.rs    # DeepSeek passthrough
└── error.rs     # ошибки в формате Anthropic API
```

## Зависимости

- [anyllm_client](https://crates.io/crates/anyllm_client) / [anyllm_translate](https://crates.io/crates/anyllm_translate) — перевод Anthropic ↔ OpenAI для Ollama
- [axum](https://crates.io/crates/axum) — HTTP-сервер
- [reqwest](https://crates.io/crates/reqwest) — passthrough к DeepSeek

## Тесты

```bash
cargo test
```

Unit-тесты для `config.rs` покрывают rootful/rootless/override сценарии вычисления `ollama_base_url`. Тесты `router.rs` проверяют формат и стабильный порядок `/v1/models`.

## Устранение неполадок

- **inf-splitter не стартует (rootless)** — задайте `DOCKER_NETWORK_MODE=rootless` и `EXTERNAL_IP` (или полагайтесь на `SOCKS_HOST`), либо явный `OLLAMA_BASE_URL`.
- **Локальная модель не маршрутизируется** — проверьте `LOCAL_MODELS` в `.env`, перезапустите `inf-splitter`. Health: `docker compose exec inf-splitter wget -qO- http://127.0.0.1:3000/health`.
- **DeepSeek-запросы не проходят** — проверьте `DEEPSEEK_API_KEY` в контейнере `claude`, `DEEPSEEK_ANTHROPIC_BASE_URL` и доступность API из контейнера `inf-splitter`.
- **Ollama недоступна из inf-splitter** — убедитесь, что Ollama слушает `0.0.0.0:${OLLAMA_PORT}` на хосте; для rootful проверьте `host.docker.internal`, для rootless — `EXTERNAL_IP`/`SOCKS_HOST`.
