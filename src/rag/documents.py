import os
from typing import List

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def load_document(file_path: str) -> List[Document]:
    """Loads a document and returns a list of Langchain Document objects."""
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext == '.pdf':
        loader = PyPDFLoader(file_path)
    elif ext in ['.md', '.markdown', '.txt']:
        # Markdown is loaded as raw text rather than via UnstructuredMarkdownLoader:
        # the chunker/embedder doesn't need semantic element parsing, and
        # unstructured's markdown partitioner downloads NLTK data at runtime,
        # which fails in network-restricted environments.
        loader = TextLoader(file_path)
    else:
        raise ValueError(f"Unsupported file extension: {ext}")

    return loader.load()


def split_documents(documents: List[Document], chunk_size: int = 1000, chunk_overlap: int = 200) -> List[Document]:
    """Splits a list of documents into chunks."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        add_start_index=True,
    )
    return text_splitter.split_documents(documents)
