from langchain_core.documents import Document
from typing import List

def format_citations(documents: List[Document]) -> str:
    """Formats a list of documents into a citation string."""
    citations = []
    for idx, doc in enumerate(documents, start=1):
        source = doc.metadata.get("source", "Unknown Source")
        page = doc.metadata.get("page", "N/A")
        citations.append(f"[{idx}] {source}, Page: {page}")
    
    return "\n".join(citations)
