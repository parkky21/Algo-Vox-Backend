import json
import logging
from pathlib import Path as FsPath
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from bson import ObjectId
from llama_index.core import StorageContext, load_index_from_storage, VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.gemini import GeminiEmbedding

from app.utils.mongodb_client import MongoDBClient

logger = logging.getLogger(__name__)

VECTOR_BASE_DIR = FsPath("vector_stores")
VECTOR_BASE_DIR.mkdir(exist_ok=True)

mongo_client = MongoDBClient()


def get_embed_model(provider: str, api_key: str, model_name: Optional[str] = None):
    provider = provider.lower()
    if provider == "openai":
        return OpenAIEmbedding(api_key=api_key)
    elif provider in {"google", "gemini"}:
        return GeminiEmbedding(api_key=api_key, model=model_name or "models/embedding-001")
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported provider: {provider}")


def get_vector_store_dir(store_id: str) -> FsPath:
    return VECTOR_BASE_DIR / store_id


def parse_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid vector store ID format")


def load_vector_store_from_mongo(store_id: str) -> Dict[str, Any]:
    """
    Load vector store metadata from MongoDB and hydrate index/embed_model into memory.
    If the index is missing from disk, a new empty index is created and persisted.
    """
    key = parse_object_id(store_id)
    metadata = mongo_client.get_vector_store(key)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Vector store '{store_id}' not found in database")

    # Build config from root-level fields
    config = {
        "provider": metadata.get("provider", "openai"),
        "model_name": metadata.get("model_name"),
        "api_key": metadata.get("api_key"),
        "knowledgeBase_id": metadata.get("knowledgeBase_id"),
        "chunk_size": metadata.get("chunk_size", 512),
        "chunk_overlap": metadata.get("chunk_overlap", 100),
    }

    store_path = get_vector_store_dir(store_id)

    try:
        embed_model = get_embed_model(
            config["provider"],
            config["api_key"],
            config.get("model_name")
        )
    except Exception as e:
        logger.error(f"Failed to initialize embed model for store {store_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to initialize embedding model")

    # Check if index directory exists
    if store_path.exists() and (store_path / "docstore.json").exists():
        try:
            storage_context = StorageContext.from_defaults(persist_dir=store_path)
            index = load_index_from_storage(storage_context, embed_model=embed_model)
        except Exception as e:
            logger.error(f"Error loading index from disk for store {store_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to load vector index")
    else:
        logger.warning(f"Index not found for store {store_id}. Creating new empty index.")
        index = VectorStoreIndex(nodes=[], embed_model=embed_model)
        index.storage_context.persist(persist_dir=str(store_path))

    metadata["index"] = index
    metadata["embed_model"] = embed_model
    metadata["config"] = config  # Provide constructed config

    return metadata
