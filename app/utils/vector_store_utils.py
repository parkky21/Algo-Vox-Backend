import json
import logging
from pathlib import Path as FsPath
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from llama_index.core import StorageContext, load_index_from_storage
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.gemini import GeminiEmbedding

logger = logging.getLogger(__name__)

VECTOR_BASE_DIR = FsPath("vector_stores")
VECTOR_BASE_DIR.mkdir(exist_ok=True)

# In-memory vector store cache
vector_stores: Dict[str, Dict[str, Any]] = {}

def get_embed_model(provider: str, api_key: str, model_name: Optional[str] = None):
    provider = provider.lower()
    if provider == "openai":
        return OpenAIEmbedding(api_key=api_key)
    elif provider in {"google", "gemini"}:
        return GeminiEmbedding(api_key=api_key, model=model_name or "models/embedding-001")
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported provider: {provider}")

def save_store_metadata(store_id: str, metadata: dict):
    """Save vector store metadata to disk"""
    store_path = VECTOR_BASE_DIR / store_id
    metadata_path = store_path / "metadata.json"

    save_data = {k: v for k, v in metadata.items() if k not in ["index", "embed_model"]}

    with open(metadata_path, "w") as f:
        json.dump(save_data, f)

def load_vector_stores():
    """Load all vector stores from disk during startup"""
    for store_dir in VECTOR_BASE_DIR.iterdir():
        if not store_dir.is_dir():
            continue

        store_id = store_dir.name
        metadata_path = store_dir / "metadata.json"

        if not metadata_path.exists():
            logger.warning(f"No metadata found for store {store_id}, skipping")
            continue

        try:
            with open(metadata_path, "r") as f:
                metadata = json.load(f)

            config = metadata.get("config", {})
            embed_model = get_embed_model(
                config.get("provider", "openai"),
                config.get("api_key", ""),
                config.get("model_name")
            )

            try:
                storage_context = StorageContext.from_defaults(persist_dir=store_dir)
                index = load_index_from_storage(storage_context, embed_model=embed_model)

                vector_stores[store_id] = {
                    "id": store_id,
                    "name": metadata.get("name", "Unnamed Store"),
                    "config": config,
                    "index": index,
                    "documents": metadata.get("documents", []),
                    "embed_model": embed_model
                }
                logger.info(f"Loaded vector store {store_id}")
            except Exception as e:
                logger.error(f"Error loading index for store {store_id}: {e}")
        except Exception as e:
            logger.error(f"Error loading metadata for store {store_id}: {e}")

load_vector_stores()