from typing import Any, Dict, List


def search_knowledge_base(query: str, k: int = 4) -> List[Dict[str, Any]]:
    """Searches the enterprise knowledge base (ChromaDB) for relevant chunks."""
    from src.rag.retrieval.chroma_store import retrieve_documents

    results = retrieve_documents(query, k=k)
    return [{"content": d.page_content, "metadata": d.metadata} for d in results]
