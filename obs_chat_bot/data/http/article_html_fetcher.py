from __future__ import annotations

import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from obs_chat_bot.application.articles.errors import ArticleFetchError
from obs_chat_bot.application.articles.html import ArticleHtml


DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_USER_AGENT = "obsChatBot/0.1"


class UrllibArticleHtmlFetcher:
    """Загружает HTML страницы статьи через стандартный HTTP-клиент Python.

    Args:
        timeout_seconds: Максимальное время ожидания ответа.
        user_agent: Значение HTTP-заголовка `User-Agent`.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not user_agent.strip():
            raise ValueError("user_agent must not be empty")

        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent

    def fetch(self, url: str) -> ArticleHtml:
        """Загружает HTML по URL.

        Args:
            url: URL страницы статьи.

        Returns:
            Загруженный HTML и метаданные ответа.

        Raises:
            ArticleFetchError: Если сервер вернул ошибку, ответ не похож на HTML
                или произошла сетевая ошибка.
        """
        request = Request(url, headers={"User-Agent": self._user_agent})

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                status = response.getcode()
                if status < 200 or status >= 300:
                    raise ArticleFetchError(f"Unexpected HTTP status: {status}")

                content_type = response.headers.get("Content-Type")
                if not _is_html_content_type(content_type):
                    raise ArticleFetchError(
                        f"Response is not HTML: {content_type or 'unknown'}"
                    )

                charset = response.headers.get_content_charset() or "utf-8"
                content = response.read().decode(charset, errors="replace")
                final_url = response.geturl()
        except HTTPError as error:
            raise ArticleFetchError(f"HTTP error while fetching article: {error.code}") from error
        except (URLError, TimeoutError, socket.timeout) as error:
            raise ArticleFetchError(f"Network error while fetching article: {error}") from error

        if not content.strip():
            raise ArticleFetchError("Fetched HTML is empty")

        return ArticleHtml(
            source_url=url,
            final_url=final_url,
            content=content,
            content_type=content_type,
        )


def _is_html_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return True
    return "html" in content_type.lower()
