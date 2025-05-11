import os
from pathlib import Path
from typing import Dict
from llama_index.core import StorageContext, load_index_from_storage
from livekit.agents import function_tool

BASE_PATH = Path(os.getcwd()) / "vector_stores"

@function_tool(name="query_vector_store", description="Query a knowledge base by store ID and ask a question")
async def query_vector_store(store_id: str, question: str) -> Dict[str, str]:
    """
    Tool to query a specific vector store using its ID.

    Args:
        store_id: The unique vector store ID.
        question: The user question to search against that store.

    Returns:
        A dictionary with the response or error message.
    """
    store_path = BASE_PATH / store_id

    if not store_path.exists():
        return {"status": "error", "message": f"Vector store '{store_id}' not found."}

    try:
        storage_context = StorageContext.from_defaults(persist_dir=store_path)
        index = load_index_from_storage(storage_context)
        query_engine = index.as_query_engine(use_async=True)
        response = await query_engine.aquery(question)

        return {"status": "success", "answer": str(response)}
    except Exception as e:
        return {"status": "error", "message": str(e)}
