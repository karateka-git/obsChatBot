# Минимальный стартовый набор

## На локальной машине

Обязательный минимум:

- Docker Desktop или Docker Engine с Docker Compose.
- Git.
- GitHub account и доступ к репозиторию проекта.
- Python 3.11 или 3.12 для проекта.

Для Windows и Docker Desktop нужен WSL2, чтобы запускать Linux-контейнеры вроде `python:3.12-slim`.

Python 3.14 может быть установлен параллельно, но проектную среду лучше держать на 3.12, пока ключевые зависимости не подтверждены на 3.14.

Проверка после установки:

- `docker --version`;
- `docker compose version`;
- `wsl --status` на Windows;
- `git --version`;
- `python --version` или `py --version`.
- `py -3.12 --version`, если на машине установлено несколько версий Python.

## GitHub для версионирования

Нужно настроить:

- GitHub-репозиторий для проекта.
- Локальный `origin`, указывающий на GitHub-репозиторий.
- Доступ для push: через GitHub CLI, SSH key или HTTPS token.

Полезные проверки:

- `git remote -v`;
- `git status`;
- `git branch --show-current`.

GitHub CLI не обязателен, но удобен для авторизации и будущих pull request:

- `gh auth status`;
- `gh repo view`.

Секреты и настройки, которые понадобятся в `.env`:

- Telegram bot token от BotFather.
- OpenAI-compatible API key.
- OpenAI-compatible base URL.
- Имя модели.

## Внутри Docker-образа

Может понадобиться установить:

- Python runtime.
- Python-зависимости проекта:
  - `aiogram`;
  - `trafilatura`;
  - `openai` или `httpx`;
  - `python-dotenv`.
- Системные пакеты, если их потребуют зависимости для HTML/XML parsing и article extraction.

SQLite отдельно устанавливать не нужно для MVP: используем Python stdlib `sqlite3`, а файл базы хранится в `data/`.
