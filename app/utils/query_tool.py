import os
from pathlib import Path
from typing import Optional
from livekit.agents import RunContext
from livekit.agents.llm import function_tool
from llama_index.core import StorageContext, load_index_from_storage

# Import vector_stores from wherever it's defined
from app.api.routes.vector_stores import vector_stores  # Adjust the import path as needed

def build_query_tool(store_id: str):
    # Get embed_model from memory if loaded in `vector_stores` dict
    vs_info = vector_stores.get(store_id)
    if not vs_info:
        raise ValueError(f"Vector store {store_id} not found in memory.")

    provider = vs_info["config"].get("provider", "")
    if provider.lower() == "openai":
        os.environ["OPENAI_API_KEY"] = vs_info["config"].get("api_key", "")

    store_path = Path("vector_stores") / store_id
    storage_context = StorageContext.from_defaults(persist_dir=store_path)

    index = load_index_from_storage(storage_context, embed_model=vs_info["embed_model"])
    query_engine = index.as_query_engine(use_async=True)

    @function_tool()
    async def query_info(context: RunContext, query: str) -> str:
        """Use this tool to know about a specific topic or information"""
        await context.session.generate_reply(
            instructions="Tell the user you're searching for \"{query}\"  and that you'll provide results momentarily. Ask them to wait.",
            allow_interruptions=False
        )
        
        context.session.input.set_audio_enabled(False)
        
        try:
            result = await query_engine.aquery(query)
            return str(result)
        finally:
            context.session.input.set_audio_enabled(True)

    return query_info