# Запуск и проверка проекта

## Быстрый запуск через скрипты

Скрипты `open-*.cmd` открывают отдельное окно PowerShell, выполняют нужные команды и оставляют окно открытым после завершения.

Запустить сборку и обычный старт проекта:

```powershell
.\scripts\open-dev-start.cmd
```

Проверить все текущие smoke-сценарии:

```powershell
.\scripts\open-check-all.cmd
```

Проверить реальную ссылку:

```powershell
.\scripts\open-process-url.cmd "https://habr.com/ru/articles/198682/"
```

Если отдельное окно не нужно, можно запускать `.ps1`-версии в текущей консоли:

```powershell
.\scripts\check-all.ps1
```

## Запуск через Codex

Можно написать Codex одну из команд ниже, и он запустит соответствующий `open-*.cmd`-скрипт в отдельном окне PowerShell:

- `запусти проект`;
- `проверь healthcheck`;
- `проверь pipeline`;
- `проверь всё`;
- `проверь ссылку https://habr.com/ru/articles/198682/`.

Окно PowerShell останется открытым после завершения команды.

## 1. Перейти в папку проекта

```powershell
cd C:\Users\compadre\Downloads\Projects\obsChatBot
```

Все следующие команды выполняются из этой папки.

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

Команда собирает или обновляет образ, создаёт контейнер и запускает приложение. Текущая версия приложения проверяет конфигурацию и завершается с кодом `0`.

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
Attaching to catcher-1
```

Строки с префиксом `catcher-1 |` и именем `obs_chat_bot` выводит уже наше Python-приложение:

```text
catcher-1 | ... INFO obs_chat_bot: Starting obsChatBot 0.1.0
catcher-1 | ... INFO obs_chat_bot: Configuration is ready
```

Сообщение `exited with code 0` означает, что приложение завершилось без ошибки.

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

## 6. Выполнить healthcheck

```powershell
docker compose run --rm catcher python -m obs_chat_bot --healthcheck
```

Команда проверяет конфигурацию, доступность папки `data/` для записи и подключение к SQLite с обязательными настройками. После проверки временный контейнер удаляется.

## 7. Проверить SQLite-контур

```powershell
docker compose run --rm catcher python -m obs_chat_bot --sqlite-smoke
```

Команда создаёт временную базу, применяет миграции, повторно проверяет их идемпотентность, записывает тестовую статью через `ArticleRepository` и читает её обратно. Рабочая база `data/app.db` не изменяется.

## 8. Проверить обработку URL

```powershell
docker compose run --rm catcher python -m obs_chat_bot --process-url "https://example.com/article"
```

Команда запускает текущий article pipeline: нормализует URL, создаёт или переиспользует статью в SQLite, загружает HTML, извлекает чистый текст и сохраняет результат в `data/app.db`.

## 9. Проверить pipeline без интернета

```powershell
docker compose run --rm catcher python -m obs_chat_bot --pipeline-smoke
```

Команда создаёт временную базу, применяет миграции и проверяет article pipeline на fake HTML-загрузчике и fake extractor. Рабочая база `data/app.db` не изменяется.
