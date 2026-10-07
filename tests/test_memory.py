"""Проверки состава данных, дубликатов и изоляции памяти."""

from __future__ import annotations

from typing import Any

from haystack import Document

from app.config import Settings
from app.memory import PineconeConversationMemory


class FakeDocumentEmbedder:
    def run(self, *, documents: list[Document]) -> dict[str, list[Document]]:
        return {"documents": documents}


class FakeTextEmbedder:
    def run(self, *, text: str) -> dict[str, list[float]]:
        return {"embedding": [float(len(text))]}


class FakeStore:
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self.documents: dict[str, Document] = {}

    def write_documents(self, documents: list[Document], *, policy: Any) -> int:
        for document in documents:
            self.documents[document.id] = document
        return len(documents)

    def count_documents(self) -> int:
        return len(self.documents)

    def delete_all_documents(self) -> None:
        self.documents.clear()


def make_settings() -> Settings:
    return Settings(
        telegram_bot_token="telegram-token-test",
        proxyapi_key="proxyapi-key-test",
        pinecone_api_key="pinecone-key-test",
    )


def test_namespaces_are_stable_and_isolated() -> None:
    first_namespace = PineconeConversationMemory.namespace_for(10)

    assert first_namespace == PineconeConversationMemory.namespace_for(10)
    assert first_namespace != PineconeConversationMemory.namespace_for(11)
    assert "10" not in PineconeConversationMemory.namespace_for(10)


def test_memory_saves_only_user_text_and_overwrites_duplicate() -> None:
    stores: dict[str, FakeStore] = {}

    def factory(namespace: str) -> FakeStore:
        stores[namespace] = FakeStore(namespace)
        return stores[namespace]

    memory = PineconeConversationMemory(
        make_settings(),
        document_embedder=FakeDocumentEmbedder(),  # type: ignore[arg-type]
        text_embedder=FakeTextEmbedder(),  # type: ignore[arg-type]
        store_factory=factory,  # type: ignore[arg-type]
    )
    memory.save_user_message(77, 5, "  Я живу в Казани.  ")
    memory.save_user_message(77, 5, "Я живу в Казани.")

    store = stores[PineconeConversationMemory.namespace_for(77)]
    assert store.count_documents() == 1
    document = next(iter(store.documents.values()))
    assert document.content == "Я живу в Казани."
    assert document.meta == {"type": "user_message", "telegram_message_id": 5}
    assert set(document.meta) == {"type", "telegram_message_id"}


def test_clear_affects_only_selected_user() -> None:
    stores: dict[str, FakeStore] = {}

    def factory(namespace: str) -> FakeStore:
        stores[namespace] = FakeStore(namespace)
        return stores[namespace]

    memory = PineconeConversationMemory(
        make_settings(),
        document_embedder=FakeDocumentEmbedder(),  # type: ignore[arg-type]
        text_embedder=FakeTextEmbedder(),  # type: ignore[arg-type]
        store_factory=factory,  # type: ignore[arg-type]
    )
    memory.save_user_message(1, 1, "Первый пользователь")
    memory.save_user_message(2, 1, "Второй пользователь")

    memory.clear(1)

    assert memory.count(1) == 0
    assert memory.count(2) == 1


def test_search_returns_only_user_messages(monkeypatch: Any) -> None:
    store = FakeStore("test")

    class FakeRetriever:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def run(self, *, query_embedding: list[float]) -> dict[str, list[Document]]:
            assert query_embedding
            return {
                "documents": [
                    Document(content="Люблю гулять вечером", meta={"type": "user_message"}),
                    Document(content="Ответ бота", meta={"type": "assistant_message"}),
                ]
            }

    monkeypatch.setattr("app.memory.PineconeEmbeddingRetriever", FakeRetriever)
    memory = PineconeConversationMemory(
        make_settings(),
        document_embedder=FakeDocumentEmbedder(),  # type: ignore[arg-type]
        text_embedder=FakeTextEmbedder(),  # type: ignore[arg-type]
        store_factory=lambda _namespace: store,  # type: ignore[arg-type]
    )

    assert memory.search(1, "Когда мне гулять?") == ["Люблю гулять вечером"]
