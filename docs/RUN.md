# Запуск и проверка проекта

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
