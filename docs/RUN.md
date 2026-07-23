# Запуск и проверка проекта

## Быстрый запуск через скрипты

Скрипты `open-*.cmd` открывают отдельное окно PowerShell, выполняют нужные команды и оставляют окно открытым после завершения. Скрипты проверок и запуска команд внутри контейнера сначала пересобирают образ `obs-chat-bot:dev`, чтобы Docker использовал свежий код проекта.

Запустить сборку и обычный старт Telegram- и VK-ботов:

```powershell
.\scripts\open-dev-start.cmd
```

Запустить проект с debug-логами только для текущего окна:

```powershell
.\scripts\open-dev-start.cmd debug
```

Проверить все текущие smoke-сценарии:

```powershell
.\scripts\open-check-all.cmd
```

Минимальный operational checklist для ежедневного запуска описан в
`docs/OPERATIONS.md`.

Проверить реальную ссылку:

```powershell
.\scripts\open-process-url.cmd "https://habr.com/ru/articles/198682/"
```

Текущий Telegram-сценарий:

- сообщение без ссылки получает просьбу прислать ссылку и не сохраняется в `incoming_messages`;
- сообщение с HTTP/HTTPS-ссылкой сохраняется в `incoming_messages`;
- после успешной обработки URL сохранённое сообщение связывается со статьёй через `incoming_messages.article_id`;
- после извлечения текста статья анализируется через OpenAI-compatible LLM, результат сохраняется в `analysis_results` и возвращается пользователю Markdown-сводкой;
- повторная ссылка переиспользует сохранённую статью и последний сохранённый анализ;
- если обработка ссылки завершилась ошибкой, диагностическая запись связывается с сообщением через `processing_errors.incoming_message_id`;
- если анализ завершился ошибкой, диагностическая запись также связывается с сообщением через `processing_errors.incoming_message_id`;
- повтор того же Telegram message id не создаёт дубль сообщения.
- ошибки загрузки, извлечения и анализа получают разные пользовательские ответы;
- диагностические ошибки можно смотреть в `processing_errors`.

Если отдельное окно не нужно, можно запускать `.ps1`-версии в текущей консоли:

```powershell
.\scripts\check-all.ps1
```

## Запуск через Codex

Можно написать Codex одну из команд ниже, и он запустит соответствующий `open-*.cmd`-скрипт в отдельном окне PowerShell:

- `запусти проект`;
- `запусти проект в дебаг`;
- `проверь healthcheck`;
- `проверь pipeline`;
- `проверь всё`;
- `проверь ссылку` (если URL не указан, используется `https://habr.com/ru/articles/198682/`);
- `проверь ссылку https://habr.com/ru/articles/198682/`.

Окно PowerShell останется открытым после завершения команды.

## Debug-логи

Если нужно видеть больше деталей в консоли сервера, включить в `.env`:

```dotenv
APP_DEBUG=true
```

После перезапуска проекта в логах появятся безопасные debug-события incoming-flow:
регистрация/привязка пользователя, сохранение входящего сообщения, ID статьи,
ID анализа и итоговый тип результата. Секреты и длинные тексты не выводятся.

## 1. Перейти в папку проекта

```powershell
cd C:\Users\compadre\Downloads\Projects\obsChatBot
```

Все следующие команды выполняются из этой папки.

## Пересоздание базы после изменения схемы

Пока проект находится в активной разработке, актуальная схема целиком хранится в
`obs_chat_bot/data/sqlite/migrations/0001_initial_schema.sql`. Новые миграции
`0002`, `0003` и далее не создаются.

После изменения схемы остановить контейнеры, удалить локальный файл
`data/app.db` и запустить приложение снова. При старте приложение создаст новую
базу и применит актуальную начальную схему.

Новая база не содержит технических пользователей. Первый успешный `/register`
создаёт `app_user_id=1`.

Удаление `data/app.db` полностью удаляет локальные данные разработки, включая
пользователей, привязки Telegram/VK, статьи, анализы и данные Obsidian vault.

## 2. Запустить Docker Desktop

```powershell
docker desktop start
```

Команда запускает Docker Desktop и Docker Engine.

## 3. Проверить готовность Docker

```powershell
docker info
```

Команда должна вывести информацию о `Client` и `Server`. Если раздел `Server` ещё недоступен, нужно немного подождать и повторить команду.

## 4. Собрать и запустить проект

```powershell
docker compose up --build
```

Команда собирает или обновляет образ, создаёт контейнер и запускает Telegram-бота и VK-бота в polling-режиме. Окно нужно оставить открытым, пока бот должен принимать сообщения.

В выводе команды сначала показывается сборка образа:

- строки с `#1`, `#2` и другими номерами шагов выполняет Docker;
- `[internal]` означает внутренние действия сборщика;
- установка пакетов через `pip` относится к зависимостям из `requirements.txt`;
- `CACHED` означает, что готовый слой взят из кэша и не выполнялся заново.

Затем Docker Compose подготавливает и запускает контейнер:

```text
Image obs-chat-bot:dev Built
Network ... Created
Container ... Created
Attaching to tg_catcher-1, vk_catcher-1
```

Строки с префиксом `tg_catcher-1 |` / `vk_catcher-1 |` и именем `obs_chat_bot` выводит уже наше Python-приложение:

```text
tg_catcher-1 | ... INFO obs_chat_bot: Starting obsChatBot 0.1.0
tg_catcher-1 | ... INFO obs_chat_bot: Telegram bot polling started
```

Остановить бота можно через `Ctrl+C` в окне, где запущен `docker compose up`.

Для повторного запуска уже собранного образа без проверки пересборки используется:

```powershell
docker compose up
```

Эта команда запускает существующий образ. После изменения `Dockerfile`, `requirements.txt` или кода проекта нужно снова использовать `docker compose up --build`, чтобы изменения попали в образ.

## 5. Проверить результат запуска

```powershell
docker compose ps -a
```

Команда показывает контейнер проекта. Статус `Exited (0)` означает, что приложение завершилось без ошибки.
Для запущенного бота ожидается статус `Up`.

## 6. Выполнить healthcheck

```powershell
docker compose run --rm tg_catcher python -m obs_chat_bot --healthcheck
```

Команда проверяет конфигурацию, доступность папки `data/` для записи и подключение к SQLite с обязательными настройками. После проверки временный контейнер удаляется.

## 7. Проверить SQLite-контур

```powershell
docker compose run --rm tg_catcher python -m obs_chat_bot --sqlite-smoke
```

Команда создаёт временную базу, применяет миграции, повторно проверяет их идемпотентность, записывает тестовую статью через `ArticleRepository` и читает её обратно. Рабочая база `data/app.db` не изменяется.

## 8. Проверить обработку URL

```powershell
docker compose run --rm tg_catcher python -m obs_chat_bot --process-url "https://example.com/article"
```

Команда запускает текущий article pipeline: нормализует URL, создаёт или переиспользует статью в SQLite, загружает HTML, извлекает чистый текст и сохраняет результат в `data/app.db`.

## 9. Проверить pipeline без интернета

```powershell
docker compose run --rm tg_catcher python -m obs_chat_bot --pipeline-smoke
```

Команда создаёт временную базу, применяет миграции и проверяет article pipeline на fake HTML-загрузчике и fake extractor. Рабочая база `data/app.db` не изменяется.

## 10. Проверить анализ без LLM

```powershell
docker compose run --rm tg_catcher python -m obs_chat_bot --analysis-smoke
```

Команда создаёт временную базу, применяет миграции, создаёт статью с извлечённым текстом и проверяет analysis pipeline на fake LLM-анализаторе. Рабочая база `data/app.db` не изменяется.

## 11. Проверить VK adapter отдельно

Для VK нужны настройки в `.env`:

```dotenv
VK_BOT_TOKEN=...
VK_GROUP_ID=...
```

При обычном запуске `docker compose up --build` VK long polling стартует
вместе с Telegram. Отдельная команда ниже нужна для изолированной проверки VK:

```powershell
docker compose run --rm --entrypoint python vk_catcher -m obs_chat_bot --vk-bot
```

VK adapter использует тот же incoming-flow, регистрацию, привязку каналов,
сохранение статей и LLM-анализ, что и Telegram.

## 12. Подключить GitHub App

Регистрация App, минимальные write permissions, Device Flow и PEM описаны в
`docs/GITHUB_APP.md`. После заполнения GitHub-группы настроек в `.env` и
перезапуска ботов зарегистрированный пользователь отправляет в Telegram или VK:

```text
/github_connect
```

Бот возвращает installation URL, Device Flow URL и одноразовый код. Polling
авторизации выполняется в background thread и не хранит временные tokens в
SQLite. При аварийном перезапуске до завершения авторизации команду нужно повторить
после истечения SQLite-защиты активной попытки (не более 20 минут от её начала).

После успешного подключения GitHub пользователь выбирает repository и
необязательный каталог Obsidian vault:

```text
/github_vault https://github.com/owner/repository
/github_vault https://github.com/owner/repository path/to/vault
```

Бот проверяет, что repository разрешён установленной GitHub App, читает его
default branch и проверяет каталог через GitHub Contents API. Корень repository
используется, если второй аргумент отсутствует. Первый vault сохраняется сразу;
замена существующего требует ответа `да` или `нет` в любом канале, привязанном к
тому же пользователю. На этом подэтапе Markdown ещё не скачивается: первая
синхронизация добавляется следующим шагом Этапа 9.
