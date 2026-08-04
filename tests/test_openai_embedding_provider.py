"""Тесты OpenAI-compatible embedding adapter Этапа 10.4."""

from types import SimpleNamespace
import unittest

from obs_chat_bot.application.search.errors import EmbeddingProviderError
from obs_chat_bot.data.embeddings.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
)


class _FakeEmbeddingsResource:
    """Возвращает детерминированные SDK-подобные ответы."""

    def __init__(self, responder=None):
        self.calls = []
        self._responder = responder or self._default_response

    def create(self, **values):
        self.calls.append(values)
        return self._responder(values)

    @staticmethod
    def _default_response(values):
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=index, embedding=[float(index), 1.0, 2.0])
                for index, _text in enumerate(values["input"])
            ]
        )


class OpenAICompatibleEmbeddingProviderTest(unittest.TestCase):
    """Проверяет batching, порядок, размерность и ошибки provider."""

    def test_embed_documents_batches_and_preserves_input_order(self) -> None:
        """Большой corpus делится на запросы без перестановки vectors."""
        resource = _FakeEmbeddingsResource(
            responder=lambda values: SimpleNamespace(
                data=list(
                    reversed(
                        [
                            SimpleNamespace(
                                index=index,
                                embedding=[float(len(text)), 1.0],
                            )
                            for index, text in enumerate(values["input"])
                        ]
                    )
                )
            )
        )
        provider = _provider(resource, batch_size=2)

        vectors = provider.embed_documents(("one", "four", "five"))

        self.assertEqual(len(resource.calls), 2)
        self.assertEqual([vector.values[0] for vector in vectors], [3.0, 4.0, 4.0])
        self.assertEqual({vector.model for vector in vectors}, {"test/doc-model"})
        self.assertEqual({vector.dimension for vector in vectors}, {2})

    def test_embed_query_uses_query_model_and_validates_vector(self) -> None:
        """Query векторизуется отдельной моделью парного vector space."""
        resource = _FakeEmbeddingsResource()
        provider = _provider(resource)

        vector = provider.embed_query("semantic query")

        self.assertEqual(vector.model, "test/query-model")
        self.assertEqual(vector.dimension, 3)
        self.assertEqual(resource.calls[0]["model"], "test/query-model")
        self.assertEqual(resource.calls[0]["input"], ["semantic query"])

    def test_document_and_query_dimensions_must_be_compatible(self) -> None:
        """Парные модели не могут возвращать vectors разной dimension."""
        resource = _FakeEmbeddingsResource(
            responder=lambda values: SimpleNamespace(
                data=[
                    SimpleNamespace(
                        index=0,
                        embedding=(
                            [1.0, 2.0]
                            if values["model"] == "test/doc-model"
                            else [1.0, 2.0, 3.0]
                        ),
                    )
                ]
            )
        )
        provider = _provider(resource)

        provider.embed_documents(("document",))

        with self.assertRaisesRegex(EmbeddingProviderError, "incompatible"):
            provider.embed_query("query")

    def test_empty_document_tuple_does_not_call_provider(self) -> None:
        """Отсутствие новых chunks не создаёт платный внешний запрос."""
        resource = _FakeEmbeddingsResource()
        provider = _provider(resource)

        self.assertEqual(provider.embed_documents(()), ())
        self.assertEqual(resource.calls, [])

    def test_empty_text_is_rejected_before_request(self) -> None:
        """Пустой chunk или query считается ошибкой caller."""
        resource = _FakeEmbeddingsResource()
        provider = _provider(resource)

        with self.assertRaises(ValueError):
            provider.embed_documents(("valid", "  "))
        with self.assertRaises(ValueError):
            provider.embed_query("")

        self.assertEqual(resource.calls, [])

    def test_unexpected_indices_are_rejected(self) -> None:
        """Нельзя связать vectors с chunks при неполных response indices."""
        resource = _FakeEmbeddingsResource(
            responder=lambda _values: SimpleNamespace(
                data=[SimpleNamespace(index=1, embedding=[1.0])]
            )
        )

        with self.assertRaisesRegex(EmbeddingProviderError, "unexpected format"):
            _provider(resource).embed_query("query")

    def test_inconsistent_dimensions_are_rejected(self) -> None:
        """Один batch не может содержать несовместимые vector dimensions."""
        resource = _FakeEmbeddingsResource(
            responder=lambda _values: SimpleNamespace(
                data=[
                    SimpleNamespace(index=0, embedding=[1.0]),
                    SimpleNamespace(index=1, embedding=[1.0, 2.0]),
                ]
            )
        )

        with self.assertRaisesRegex(EmbeddingProviderError, "inconsistent"):
            _provider(resource).embed_documents(("one", "two"))

    def test_network_error_exposes_only_error_type(self) -> None:
        """Application error не содержит исходные тексты или credentials."""
        def fail(_values):
            raise RuntimeError("provider detail")

        provider = _provider(_FakeEmbeddingsResource(responder=fail))

        with self.assertRaises(EmbeddingProviderError) as raised:
            provider.embed_query("private vault text")

        self.assertEqual(
            str(raised.exception),
            "Embedding request failed: RuntimeError",
        )
        self.assertNotIn("private vault text", str(raised.exception))


def _provider(
    resource: _FakeEmbeddingsResource,
    *,
    batch_size: int = 64,
) -> OpenAICompatibleEmbeddingProvider:
    """Собирает adapter с fake SDK-клиентом."""
    return OpenAICompatibleEmbeddingProvider(
        base_url="https://embeddings.example/v1",
        api_key="secret",
        document_model="test/doc-model",
        query_model="test/query-model",
        batch_size=batch_size,
        client=SimpleNamespace(embeddings=resource),
    )


if __name__ == "__main__":
    unittest.main()
