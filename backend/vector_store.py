"""
ChromaDB vector store setup, embedding, and retrieval.
Supports OpenAI text-embedding-3-small or Cohere embed-english-v3.0.
"""
import os
from typing import Any

import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_core.documents import Document


COLLECTION_NAME = "aura_runbooks"


def _get_embedding_function():
    """Return the appropriate LangChain embedding model based on available API keys."""
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model="text-embedding-3-small")
    elif os.getenv("COHERE_API_KEY"):
        from langchain_cohere import CohereEmbeddings
        return CohereEmbeddings(model="embed-english-v3.0")
    else:
        raise EnvironmentError(
            "No embedding API key found. Set OPENAI_API_KEY or COHERE_API_KEY."
        )


def get_chroma_client(persist_path: str | None = None) -> chromadb.ClientAPI:
    path = persist_path or os.getenv("CHROMA_PERSIST_PATH", "./chroma_data")
    os.makedirs(path, exist_ok=True)
    return chromadb.PersistentClient(
        path=path,
        settings=Settings(anonymized_telemetry=False),
    )


def get_vector_store(
    collection_name: str = COLLECTION_NAME,
    persist_path: str | None = None,
) -> Chroma:
    """Return a LangChain Chroma vector store backed by a persistent client."""
    client = get_chroma_client(persist_path)
    embeddings = _get_embedding_function()
    return Chroma(
        client=client,
        collection_name=collection_name,
        embedding_function=embeddings,
    )


def add_documents(
    docs: list[Document],
    collection_name: str = COLLECTION_NAME,
    persist_path: str | None = None,
) -> list[str]:
    """Embed and persist a list of LangChain Documents. Returns the generated IDs."""
    store = get_vector_store(collection_name=collection_name, persist_path=persist_path)
    ids = store.add_documents(docs)
    return ids


def similarity_search(
    query: str,
    k: int = 5,
    collection_name: str = COLLECTION_NAME,
    persist_path: str | None = None,
    filter_metadata: dict[str, Any] | None = None,
) -> list[Document]:
    """Return the top-k most relevant documents for *query*."""
    store = get_vector_store(collection_name=collection_name, persist_path=persist_path)
    return store.similarity_search(query, k=k, filter=filter_metadata)


def similarity_search_with_score(
    query: str,
    k: int = 5,
    collection_name: str = COLLECTION_NAME,
    persist_path: str | None = None,
) -> list[tuple[Document, float]]:
    """Return top-k documents with their cosine similarity scores."""
    store = get_vector_store(collection_name=collection_name, persist_path=persist_path)
    return store.similarity_search_with_relevance_scores(query, k=k)


def get_collection_count(
    collection_name: str = COLLECTION_NAME,
    persist_path: str | None = None,
) -> int:
    """Return the number of embedded chunks in the collection."""
    client = get_chroma_client(persist_path)
    try:
        col = client.get_collection(collection_name)
        return col.count()
    except Exception:
        return 0


def delete_by_source(
    source_file: str,
    collection_name: str = COLLECTION_NAME,
    persist_path: str | None = None,
) -> None:
    """Remove all chunks that belong to a specific source file."""
    client = get_chroma_client(persist_path)
    try:
        col = client.get_collection(collection_name)
        col.delete(where={"source_file": source_file})
    except Exception:
        pass
