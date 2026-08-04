"""OpenAI-compatible adapter embeddings для Timeweb AI Gateway."""

from __future__ import annotations

from numbers import Real
from typing import Any

from obs_chat_bot.application.search.errors import EmbeddingProviderError
from obs_chat_bot.application.search.ports import EmbeddingProvider
from obs_chat_bot.data.embeddings.dtos import EmbeddingResponseItemDto
from obs_chat_bot.data.embeddings.mappers import embedding_vector_from_dto
from obs_chat_bot.domain.search.entities import EmbeddingVector


DEFAULT_EMBEDDING_BATCH_SIZE = 64
DEFAULT_EMBEDDING_TIMEOUT_SECONDS = 30.0


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    """Получает embeddings пакетами через совместимый `/v1/embeddings`.

    Args:
        base_url: Базовый URL API без завершающего `/`.
        api_key: Отдельный ключ embedding provider.
        model: ID модели, общий для документов и поисковых запросов.
        batch_size: Максимальное число текстов в одном HTTP-запросе.
        timeout_seconds: Timeout одного запроса в секундах.
        client: Необязательный готовый SDK-клиент для тестов.

    Raises:
        ValueError: Если конфигурация adapter некорректна.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
        timeout_seconds: float = DEFAULT_EMBEDDING_TIMEOUT_SECONDS,
        client: Any | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url must not be empty")
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        if not model.strip():
            raise ValueError("model must not be empty")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._base_url = base_url.strip().rstrip("/")
        self._api_key = api_key
        self._model = model.strip()
        self._batch_size = batch_size
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def model(self) -> str:
        """Возвращает настроенный ID модели Timeweb AI Gateway."""
        return self._model

    def embed_documents(
        self,
        texts: tuple[str, ...],
    ) -> tuple[EmbeddingVector, ...]:
        """Векторизует corpus chunks пакетами, сохраняя исходный порядок.

        Args:
            texts: Тексты chunks; пустой tuple не создаёт HTTP-запрос.

        Returns:
            Векторы той же длины, модели и размерности.

        Raises:
            ValueError: Если какой-либо текст пуст.
            EmbeddingProviderError: Если запрос или проверка ответа неуспешны.
        """
        _validate_texts(texts)
        if not texts:
            return ()
        vectors: list[EmbeddingVector] = []
        expected_dimension: int | None = None
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            batch_vectors = self._request(batch)
            for vector in batch_vectors:
                if expected_dimension is None:
                    expected_dimension = vector.dimension
                elif vector.dimension != expected_dimension:
                    raise EmbeddingProviderError(
                        "Embedding response contains inconsistent dimensions"
                    )
            vectors.extend(batch_vectors)
        return tuple(vectors)

    def embed_query(self, text: str) -> EmbeddingVector:
        """Векторизует один поисковый запрос совместимой моделью.

        Args:
            text: Непустой поисковый запрос.

        Returns:
            Проверенный semantic-вектор.

        Raises:
            ValueError: Если запрос пуст.
            EmbeddingProviderError: Если provider недоступен или ответ неверен.
        """
        _validate_texts((text,))
        return self._request((text,))[0]

    def _request(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        """Выполняет один HTTP-запрос и проверяет порядок response items."""
        try:
            response = self._get_client().embeddings.create(
                model=self._model,
                input=list(texts),
            )
        except EmbeddingProviderError:
            raise
        except Exception as error:
            raise EmbeddingProviderError(
                f"Embedding request failed: {type(error).__name__}"
            ) from error
        try:
            items = _response_items(response)
            if len(items) != len(texts):
                raise ValueError("response item count does not match input count")
            ordered = sorted(items, key=lambda item: item.index)
            if [item.index for item in ordered] != list(range(len(texts))):
                raise ValueError("response indices do not match input order")
            return tuple(
                embedding_vector_from_dto(item, model=self._model)
                for item in ordered
            )
        except (AttributeError, TypeError, ValueError) as error:
            raise EmbeddingProviderError(
                "Embedding response has unexpected format"
            ) from error

    def _get_client(self) -> Any:
        """Лениво создаёт SDK-клиент с ограниченным timeout и retry."""
        if self._client is None:
            try:
                from openai import OpenAI
            except ModuleNotFoundError as error:
                raise EmbeddingProviderError(
                    "openai package is not installed"
                ) from error
            self._client = OpenAI(
                base_url=self._base_url,
                api_key=self._api_key,
                timeout=self._timeout_seconds,
                max_retries=2,
            )
        return self._client


def _validate_texts(texts: tuple[str, ...]) -> None:
    """Не допускает запросов с пустыми или нестроковыми элементами."""
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("embedding texts must contain only non-empty strings")


def _response_items(response: Any) -> tuple[EmbeddingResponseItemDto, ...]:
    """Извлекает и типизирует items SDK-ответа без утечки исходных текстов."""
    raw_items = response.data
    items: list[EmbeddingResponseItemDto] = []
    for raw_item in raw_items:
        index = raw_item.index
        raw_values = raw_item.embedding
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("embedding index must be a non-negative integer")
        if not isinstance(raw_values, (list, tuple)) or not raw_values:
            raise ValueError("embedding values must be a non-empty sequence")
        if any(
            isinstance(value, bool) or not isinstance(value, Real)
            for value in raw_values
        ):
            raise ValueError("embedding values must be numeric")
        items.append(
            EmbeddingResponseItemDto(
                index=index,
                values=tuple(float(value) for value in raw_values),
            )
        )
    return tuple(items)
