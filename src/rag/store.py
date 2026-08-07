import os
from typing import Any, Dict, List

import chromadb
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))  # Assuming local mapped port
COLLECTION_NAME = "enterprise_knowledge"


def get_embeddings() -> OpenAIEmbeddings:
    """Returns the configured OpenAI Embeddings instance."""
    return OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=os.getenv("OPENAI_API_KEY", "mock-key-for-local")
    )


def get_chroma_client():
    return chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)


def get_vector_store() -> Chroma:
    """Returns the Chroma vector store instance."""
    client = get_chroma_client()
    return Chroma(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings(),
    )


def add_documents_to_store(documents: List[Document]):
    """Adds chunked documents to the Chroma vector store."""
    vector_store = get_vector_store()
    vector_store.add_documents(documents)


def retrieve_documents(query: str, k: int = 4, filter_metadata: Dict[str, Any] = None) -> List[Document]:
    """Retrieves documents based on semantic similarity and optional metadata filters."""
    vector_store = get_vector_store()
    return vector_store.similarity_search(query, k=k, filter=filter_metadata)


def access_scope_filter(user_role: str) -> Dict[str, Any] | None:
    """Chroma metadata filter restricting retrieval to chunks the caller may see.

    Admins see every chunk (no filter); everyone else only sees chunks from
    documents ingested with access_scope="shared" (the default for uploads).
    """
    return None if user_role == "admin" else {"access_scope": "shared"}


def format_citations(documents: List[Document]) -> str:
    """Formats a list of documents into a citation string."""
    citations = []
    for idx, doc in enumerate(documents, start=1):
        source = doc.metadata.get("source", "Unknown Source")
        page = doc.metadata.get("page", "N/A")
        citations.append(f"[{idx}] {source}, Page: {page}")

    return "\n".join(citations)
