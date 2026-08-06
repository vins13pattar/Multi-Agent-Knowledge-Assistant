import os
import chromadb
from typing import List, Dict, Any
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from src.rag.embeddings.openai_embeddings import get_embeddings

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001")) # Assuming local mapped port
COLLECTION_NAME = "enterprise_knowledge"

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
