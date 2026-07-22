# Настройка GitHub App для Obsidian vault

GitHub connector читает выбранный repository и после явного подтверждения
пользователя записывает изменения Obsidian vault прямым commit в default branch.
Пользователь проходит Device Flow в браузере, а приложение сохраняет в SQLite
только разрешённые installation IDs. Device code, user access token, App JWT и
installation access token существуют только в памяти процесса.

## 1. Зарегистрировать GitHub App

Открыть настройки GitHub account:

1. `Settings` → `Developer settings` → `GitHub Apps` → `New GitHub App`.
2. Задать уникальное имя и Homepage URL проекта.
3. В `Webhook` отключить `Active`: webhook отложен в backlog.
4. В Repository permissions выбрать:
   - `Contents: Read and write`;
   - `Metadata: Read-only` — обязательное разрешение GitHub.
5. Остальные permissions оставить `No access`.
6. В `Where can this GitHub App be installed?` разрешить установку на любой
   account, если connector будет использоваться несколькими GitHub accounts.
7. Создать приложение.

Если `Contents` изменён с read-only после установки App, владелец installation
должен отдельно одобрить новые permissions. Пока запрос не одобрен, существующая
installation продолжает возвращать `Contents: read`.

На странице созданного App включить Device Flow. Client secret для выбранного
Device Flow не требуется.

## 2. Получить идентификаторы и PEM

На странице App сохранить:

- App ID;
- Client ID — он отличается от App ID;
- app slug из URL `https://github.com/apps/<app-slug>`.

В разделе private keys создать приватный ключ. Скачанный PEM поместить локально
в `data/github-app.pem`. Папка `data/` исключена из Git, но файл всё равно нельзя
публиковать, отправлять в чат или выводить в логи.

## 3. Настроить `.env`

```dotenv
GITHUB_APP_ID=123456
GITHUB_CLIENT_ID=Iv1.example
GITHUB_APP_SLUG=obs-chat-bot-example
GITHUB_PRIVATE_KEY_PATH=data/github-app.pem
```

GitHub connector считается выключенным, если все четыре значения отсутствуют.
Частично заполненная группа считается ошибкой конфигурации.

## 4. Установить App и подключить пользователя

После запуска Telegram или VK adapter зарегистрированный пользователь отправляет:

```text
/github_connect
```

Бот возвращает две ссылки и одноразовый код:

1. по installation URL нужно установить App и выбрать repository с vault;
2. по Device Flow URL нужно авторизоваться и ввести одноразовый код;
3. фоновый worker получит доступные installation IDs и сохранит только их;
4. бот сообщит в исходный чат об успехе, отсутствии доступных installations,
   отказе, истечении кода или ошибке.

Если процесс перезапущен до завершения Device Flow, временная сессия исчезает и
команду нужно отправить заново.

## Официальная документация

- [Регистрация GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app)
- [Device Flow для GitHub App](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app)
- [JWT GitHub App](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app)
- [Installation access token](https://docs.github.com/en/rest/apps/apps#create-an-installation-access-token-for-an-app)
- [Одобрение новых permissions установленного GitHub App](https://docs.github.com/en/apps/using-github-apps/approving-updated-permissions-for-a-github-app)
