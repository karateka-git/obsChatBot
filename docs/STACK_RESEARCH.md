# Лёгкое исследование стека

Дата: 2026-06-07

Цель: выбрать стек первой реализации Article Bot без прототипирования.

## Обновление решения

После первичного сравнения принято пользовательское решение: первую версию пишем **целиком на Python** и подключаем **только Telegram**. VK остаётся будущим адаптером и не влияет на MVP.

## Матрица сравнения

| Область | Python вариант | Отложенный вариант | Оценка |
| --- | --- | --- | --- |
| Telegram | `aiogram` для polling, обработки сообщений и отправки ответов. | Прямой Telegram Bot API через HTTP можно использовать точечно, если библиотека мешает. | Для MVP выбрать `aiogram`: быстрее старт, меньше ручной инфраструктуры, естественный async-подход. |
| VK | Не реализуется в первой версии. | Добавить позже как отдельный adapter, вероятно через `vk_api` или прямой VK API/Bots Long Poll. | VK не должен усложнять схему MVP, конфиг и критерии готовности первой версии. |
| HTTP и LLM | OpenAI-совместимый Python SDK или тонкий HTTP-клиент с настраиваемыми `base_url`, `api_key`, `model`. | Можно заменить SDK на прямой HTTP adapter, если совместимый провайдер требует особой формы запроса. | Для MVP выбрать Python LLM adapter с OpenAI-compatible API через env. |
| SQLite | stdlib `sqlite3` + простые SQL-миграции и repository layer. | SQLAlchemy добавить позже, если схема и запросы станут сложнее. | Для MVP выбрать stdlib `sqlite3`: достаточно, прозрачно, без лишнего ORM-слоя. |
| Извлечение текста статей | `trafilatura` для main text/metadata extraction; при необходимости `httpx`/`aiohttp` для загрузки страниц. | `readability-lxml`, BeautifulSoup или кастомная очистка как fallback. | Python сразу закрывает самый рискованный слой: извлечение чистого текста статьи. |
| Будущий RAG | Python-интерфейсы для chunking, embeddings provider и поиска; SQLite остаётся source of truth. | FAISS или другой vector index добавить позже как вторичный индекс. | Python удобнее для RAG/tooling, но RAG не фиксируем рано. |
| Docker-first | Python service в Docker Compose, SQLite в `data/`, конфиг через `.env`. | VPS deployment тем же compose-файлом. | Docker-first сохраняется без изменений. |

## Риски Python-first

- Нужно аккуратно развести async bot polling и потенциально блокирующие операции: загрузку страниц, `trafilatura`, SQLite и LLM-вызовы.
- `sqlite3` синхронный; для MVP допустимо, но долгие network/LLM операции не должны выполняться внутри DB transaction.
- `trafilatura` может быть тяжёлой для некоторых страниц; интерфейс extractor должен позволять fallback.
- Telegram-only MVP проще, но внутреннюю модель сообщений лучше оставить канал-независимой, чтобы VK можно было добавить позже без переписывания pipeline.
- OpenAI-compatible провайдеры могут различаться в деталях API; LLM adapter должен изолировать эти различия.

## Решение

Выбираем **Python как основной и единственный стек первой реализации**.

Первая реализация:

- Python service.
- Telegram-only bot через `aiogram`.
- Docker Compose с начала проекта.
- SQLite через stdlib `sqlite3`, простые SQL-миграции и repository layer.
- Article extraction через `trafilatura`.
- OpenAI-compatible LLM adapter через переменные окружения.
- Интерфейсы для загрузки статьи, извлечения текста, LLM-анализа, storage и будущего RAG.
- VK не реализовывать в MVP; добавить позже отдельным adapter поверх общего article pipeline.

## Использованные источники

- Telegram Bot API: https://core.telegram.org/bots/api
- aiogram: https://aiogram.dev/
- aiogram long-polling: https://docs.aiogram.dev/en/v3.20.0/dispatcher/long_polling.html
- OpenAI Python SDK: https://github.com/openai/openai-python
- Python sqlite3: https://docs.python.org/3/library/sqlite3.html
- trafilatura: https://trafilatura.readthedocs.io/en/stable/
- vk_api Bot Long Poll, как будущий ориентир: https://vk-api.readthedocs.io/en/latest/bot_longpoll.html
