"""Типизированные ошибки semantic indexing и retrieval."""


class EmbeddingProviderError(RuntimeError):
    """Ошибка получения или проверки embeddings внешнего провайдера."""


class SearchIndexUnavailableError(RuntimeError):
    """Текущее поколение поискового индекса отсутствует или несовместимо."""
