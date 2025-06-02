from pathlib import Path
from livekit.agents import RunContext
from livekit.agents.llm import function_tool
from llama_index.core import StorageContext, load_index_from_storage
from llama_index.llms.openai import OpenAI
from app.utils.vector_store_utils import load_vector_store_from_mongo
import logging

logger = logging.getLogger(__name__)

def build_query_tool(store_id: str):
    # Load store metadata and hydrate index + embed_model
    try:
        vs_info = load_vector_store_from_mongo(store_id)
    except Exception as e:
        logger.error(f"Failed to load vector store for query tool: {e}")
        raise ValueError(f"Vector store '{store_id}' not found or could not be loaded.")

    provider = vs_info["config"].get("provider", "").lower()
    api_key = vs_info["config"].get("api_key", "")

    index = vs_info.get("index")
    if not index:
        raise ValueError(f"Failed to load index for vector store '{store_id}'")

    query_engine = index.as_query_engine(llm=OpenAI(api_key=api_key), use_async=True)

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
