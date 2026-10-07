"""Долговременная память пользовательских сообщений в Pinecone."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from threading import Lock
from typing import Protocol

from haystack import Document
from haystack.components.embedders import OpenAIDocumentEmbedder, OpenAITextEmbedder
from haystack.document_stores.types import DuplicatePolicy
from haystack.utils import Secret
from haystack_integrations.components.retrievers.pinecone import PineconeEmbeddingRetriever
from haystack_integrations.document_stores.pinecone import PineconeDocumentStore
from loguru import logger

from app.config import Settings


class ConversationMemory(Protocol):
    """Контракт памяти, который использует сервис ассистента."""

    def search(self, user_id: int, query: str) -> list[str]: ...

    def save_user_message(self, user_id: int, message_id: int, text: str) -> None: ...

    def count(self, user_id: int) -> int: ...

    def clear(self, user_id: int) -> None: ...


class PineconeConversationMemory:
    """Хранить только исходные тексты пользователя в его namespace."""

    def __init__(
        self,
        settings: Settings,
        *,
        document_embedder: OpenAIDocumentEmbedder,
        text_embedder: OpenAITextEmbedder,
        store_factory: Callable[[str], PineconeDocumentStore] | None = None,
    ) -> None:
        self._settings = settings
        self._document_embedder = document_embedder
        self._text_embedder = text_embedder
        self._store_factory = store_factory or self._create_store
        self._stores: dict[str, PineconeDocumentStore] = {}
        self._stores_lock = Lock()

    @staticmethod
    def namespace_for(user_id: int | str) -> str:
        """Скрыть открытый Telegram ID в названии пространства Pinecone."""

        digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:24]
        return f"user-{digest}"

    @staticmethod
    def document_id(namespace: str, message_id: int) -> str:
        """Создать стабильный ID, чтобы повторная обработка не дала дубликат."""

        raw_id = f"{namespace}:{message_id}"
        return hashlib.sha256(raw_id.encode("utf-8")).hexdigest()

    def search(self, user_id: int, query: str) -> list[str]:
        """Найти прошлые пользовательские сообщения, близкие по смыслу."""

        normalized_query = query.strip()
        if not normalized_query:
            return []

        store = self._store_for(user_id)
        embedding_result = self._text_embedder.run(text=normalized_query)
        retriever = PineconeEmbeddingRetriever(
            document_store=store,
            top_k=self._settings.memory_top_k,
        )
        result = retriever.run(query_embedding=embedding_result["embedding"])
        messages = [
            document.content.strip()
            for document in result["documents"]
            if document.content and document.meta.get("type") == "user_message"
        ]
        logger.info(
            "Pinecone: найден контекст user_namespace={} count={}",
            self.namespace_for(user_id),
            len(messages),
        )
        return messages

    def save_user_message(self, user_id: int, message_id: int, text: str) -> None:
        """Создать embedding и сохранить только текст сообщения пользователя."""

        normalized_text = text.strip()
        if not normalized_text:
            return

        namespace = self.namespace_for(user_id)
        document = Document(
            id=self.document_id(namespace, message_id),
            content=normalized_text,
            meta={
                "type": "user_message",
                "telegram_message_id": message_id,
            },
        )
        embedded = self._document_embedder.run(documents=[document])["documents"]
        self._store_for(user_id).write_documents(
            embedded,
            policy=DuplicatePolicy.OVERWRITE,
        )
        logger.info(
            "Pinecone: сохранено пользовательское сообщение user_namespace={} message_id={}",
            namespace,
            message_id,
        )

    def count(self, user_id: int) -> int:
        """Вернуть число сообщений в памяти текущего пользователя."""

        return self._store_for(user_id).count_documents()

    def clear(self, user_id: int) -> None:
        """Удалить только namespace текущего пользователя."""

        namespace = self.namespace_for(user_id)
        self._store_for(user_id).delete_all_documents()
        logger.info("Pinecone: память очищена user_namespace={}", namespace)

    def _store_for(self, user_id: int) -> PineconeDocumentStore:
        namespace = self.namespace_for(user_id)
        with self._stores_lock:
            if namespace not in self._stores:
                self._stores[namespace] = self._store_factory(namespace)
            return self._stores[namespace]

    def _create_store(self, namespace: str) -> PineconeDocumentStore:
        return PineconeDocumentStore(
            api_key=Secret.from_token(self._settings.pinecone_api_key),
            index=self._settings.pinecone_index,
            namespace=namespace,
            dimension=self._settings.embedding_dimension,
            metric="cosine",
            spec={
                "serverless": {
                    "cloud": self._settings.pinecone_cloud,
                    "region": self._settings.pinecone_region,
                }
            },
            show_progress=False,
        )

