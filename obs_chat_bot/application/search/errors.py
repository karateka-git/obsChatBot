"""Типизированные ошибки semantic indexing и retrieval."""


class EmbeddingProviderError(RuntimeError):
    """Ошибка получения или проверки embeddings внешнего провайдера."""
