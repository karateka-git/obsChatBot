# Operational checklist локального Telegram MVP

Короткий чеклист для ежедневного запуска и проверки Telegram-only версии.

## Перед запуском

1. Убедиться, что Docker Desktop запущен.
2. Проверить `.env`:
   - `TELEGRAM_BOT_TOKEN` задан;
   - `OPENAI_BASE_URL` указывает на базовый URL AI-агента;
   - `OPENAI_API_KEY` содержит только токен, без `Bearer`;
   - `OPENAI_MODEL` заполнен, даже если провайдер игнорирует это поле;
   - `APP_DEBUG=true` включать только для диагностики, когда нужны подробные
     безопасные логи incoming-flow.
3. Убедиться, что нет второго polling-экземпляра Telegram-бота:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'obs_chat_bot|--telegram-bot' } |
  Select-Object ProcessId,Name,CommandLine
```

Если старое окно Telegram-бота открыто, закрыть его перед новым запуском.

## Проверки перед работой

```powershell
.\scripts\open-check-all.cmd
```

Эта команда пересобирает Docker-образ и проверяет:

- healthcheck;
- SQLite migrations и repository;
- article pipeline без интернета;
- analysis pipeline без реального LLM.

Для быстрой проверки без отдельного окна:

```powershell
python -m unittest discover -s tests
python -m obs_chat_bot --pipeline-smoke
python -m obs_chat_bot --analysis-smoke
```

## Запуск бота

```powershell
.\scripts\open-dev-start.cmd
```

Окно PowerShell должно остаться открытым. Скрипт запускает Docker Compose через
`docker compose up --build`, поднимает Telegram polling и держит контейнер
активным до остановки через `Ctrl+C`. В логах ожидается старт polling без
`TelegramConflictError`.

## Проверка пользовательского сценария

1. Отправить боту HTTP/HTTPS-ссылку на статью.
2. Ожидаемый ответ:
   - новая или уже сохранённая статья;
   - строка `Анализ готов.` или `Использую сохраненный анализ.`;
   - Markdown-блок LLM-сводки.
3. Повторно отправить ту же ссылку. Бот должен переиспользовать сохранённый
   анализ и не создавать новую статью.

## Диагностика SQLite

## Debug-режим

Для расширенных логов в консоли сервера добавить в `.env`:

```dotenv
APP_DEBUG=true
```

В debug-режиме приложение пишет безопасные события обработки: тип входящего
сообщения, результат flow, `app_user_id`, `incoming_message_id`, `article_id`,
`analysis_id`, данные внешней identity при регистрации/привязке. Секреты,
полный текст статей, LLM prompt и API keys не логируются.

После проверки вернуть:

```dotenv
APP_DEBUG=false
```

Если бот отвечает ошибкой, посмотреть последние диагностические записи:

```powershell
@'
import sqlite3

con = sqlite3.connect("data/app.db")
con.row_factory = sqlite3.Row
for row in con.execute("""
    SELECT id, article_id, incoming_message_id, stage, error_type, error_message, created_at
    FROM processing_errors
    ORDER BY id DESC
    LIMIT 10
"""):
    print(dict(row))
con.close()
'@ | python -
```

Ожидаемые таблицы MVP:

- `articles` — сохранённые статьи и их статус;
- `incoming_messages` — Telegram-сообщения со ссылками;
- `analysis_results` — сохранённые LLM-сводки;
- `processing_errors` — диагностика ошибок загрузки, извлечения и анализа.

## Частые проблемы

- `TelegramConflictError`: уже запущен другой экземпляр бота с тем же token.
  Закрыть старое окно и запустить заново.
- `401 Unauthorized access` на stage `analysis`: неверный AI-agent API key или
  ключ вставлен в `.env` вместе с `Bearer`.
- Ошибка загрузки страницы: сайт недоступен, вернул неуспешный HTTP-статус или
  блокирует загрузку.
- Ошибка извлечения текста: HTML загрузился, но extractor не нашёл содержательный
  текст статьи.
