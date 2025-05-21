from pathlib import Path
from livekit.agents import RunContext
from livekit.agents.llm import function_tool
from llama_index.core import StorageContext, load_index_from_storage
from app.utils.vector_store_utils import vector_stores
import logging
from llama_index.llms.openai import OpenAI


logger = logging.getLogger(__name__)

def build_query_tool(store_id: str):
    vs_info = vector_stores.get(store_id)
    if not vs_info:
        raise ValueError(f"Vector store '{store_id}' not found in memory.")

    provider = vs_info["config"].get("provider", "").lower()
    api_key = vs_info["config"].get("api_key", "")

    index = vs_info.get("index")
    if not index:
        logger.info(f"Loading vector store index from disk for store ID: {store_id}")
        # Ensure the directory exists
        store_path = Path("vector_stores") / store_id
        storage_context = StorageContext.from_defaults(persist_dir=store_path)
        index = load_index_from_storage(storage_context, embed_model=vs_info["embed_model"])
        vs_info["index"] = index  # Cache it for future use

    query_engine = index.as_query_engine(llm=OpenAI(api_key=api_key),use_async=True)

    @function_tool(name="query_info", description="Use this tool to search information from the knowledge base.")
    async def query_info(context: RunContext, query: str) -> str:
        await context.session.generate_reply(
            instructions=f"Searching for: \"{query}\". Please hold on while I fetch the information.",
            allow_interruptions=False
        )
        context.session.input.set_audio_enabled(False)

        try:
            result = await query_engine.aquery(query)
            return str(result)
        finally:
            context.session.input.set_audio_enabled(True)

    return query_info
