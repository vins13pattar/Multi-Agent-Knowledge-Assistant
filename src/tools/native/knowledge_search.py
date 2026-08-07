from typing import Any, Dict, List


def search_knowledge_base(query: str, k: int = 4, user_role: str = "employee") -> List[Dict[str, Any]]:
    """Searches the enterprise knowledge base (ChromaDB) for relevant chunks."""
    from src.rag.store import retrieve_documents, access_scope_filter

    results = retrieve_documents(query, k=k, filter_metadata=access_scope_filter(user_role))
    return [{"content": d.page_content, "metadata": d.metadata} for d in results]
