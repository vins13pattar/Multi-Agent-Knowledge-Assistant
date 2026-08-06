import os
from langchain_openai import OpenAIEmbeddings

def get_embeddings():
    """Returns the configured OpenAI Embeddings instance."""
    return OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=os.getenv("OPENAI_API_KEY", "mock-key-for-local")
    )
