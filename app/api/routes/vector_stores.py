from fastapi import APIRouter, HTTPException, Body, Path, Query, status
from app.core.models import VectorStoreConfig, DocumentUpload
from typing import Optional, List, Dict, Any
import uuid
import logging
import tempfile
import json
import shutil
from pathlib import Path as FsPath  # Rename to avoid conflict with fastapi.Path
from llama_index.core import (
    SimpleDirectoryReader,
    VectorStoreIndex,
    StorageContext,
    load_index_from_storage
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.gemini import GeminiEmbedding

router = APIRouter()

logger = logging.getLogger(__name__)

VECTOR_BASE_DIR = FsPath("vector_stores")
VECTOR_BASE_DIR.mkdir(exist_ok=True)

# In-memory cache of vector stores
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
    
    # Remove non-serializable objects before saving
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
            
            # Load the index from storage
            try:
                storage_context = StorageContext.from_defaults(persist_dir=store_dir)
                index = load_index_from_storage(storage_context, embed_model=embed_model)
                
                # Populate the in-memory cache
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

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_vector_store(config: VectorStoreConfig = Body(...)):
    store_id = config.store_id or str(uuid.uuid4())
    if store_id in vector_stores:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Vector store ID already exists")

    store_path = VECTOR_BASE_DIR / store_id
    
    try:
        # Create directory first
        store_path.mkdir(exist_ok=True, parents=True)
        
        # Create the embed model
        embed_model = get_embed_model(config.provider, config.api_key, config.model_name)
        
        # Create empty nodes list and index directly
        index = VectorStoreIndex(
            nodes=[], 
            embed_model=embed_model
        )
        
        # Save the index to disk
        index.storage_context.persist(persist_dir=str(store_path))
        
        # Store in memory
        store_info = {
            "id": store_id,
            "name": config.name,
            "config": config.dict(),
            "index": index,
            "documents": [],
            "embed_model": embed_model
        }
        
        vector_stores[store_id] = store_info
        save_store_metadata(store_id, store_info)

        return {"store_id": store_id, "name": config.name, "status": "created"}

    except Exception as e:
        logger.exception(f"Error creating vector store: {e}")
        # Clean up if any error occurs
        if store_path.exists():
            try:
                shutil.rmtree(store_path)
            except Exception as cleanup_error:
                logger.error(f"Error cleaning up after failed creation: {cleanup_error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{store_id}/documents", status_code=status.HTTP_201_CREATED)
async def add_document(
    store_id: str = Path(..., description="Vector store ID"),
    document: DocumentUpload = Body(...)
):
    if store_id not in vector_stores:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vector store not found")

    temp_path = None
    try:
        vs_info = vector_stores[store_id]
        config = vs_info.get("config", {})
        chunk_size = config.get("chunk_size", 512)
        chunk_overlap = config.get("chunk_overlap", 100)
        
        embed_model = vs_info["embed_model"]
        store_path = VECTOR_BASE_DIR / store_id

        # Create a temporary file with the document content
        suffix = f".{document.document_type}" if document.document_type else ".txt"
        with tempfile.NamedTemporaryFile(delete=False, mode="w+", suffix=suffix) as temp_file:
            temp_file.write(document.document_content)
            temp_path = FsPath(temp_file.name)

        # Load document from the temporary file
        reader = SimpleDirectoryReader(input_files=[str(temp_path)])
        documents = reader.load_data()

        # Create the node splitter
        splitter = SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        # Get nodes from the document
        nodes = splitter.get_nodes_from_documents(documents)

        # Get the index from memory or create new one if needed
        index = vs_info.get("index")
        if not index:
            try:
                # Try to load from disk
                storage_context = StorageContext.from_defaults(persist_dir=str(store_path))
                index = load_index_from_storage(storage_context, embed_model=embed_model)
            except Exception as e:
                logger.error(f"Error loading index for {store_id}, creating new one: {e}")
                index = VectorStoreIndex(nodes=[], embed_model=embed_model)
                index.storage_context.persist(persist_dir=str(store_path))
        
        # Insert the new nodes
        index.insert_nodes(nodes)
        # Persist to disk
        index.storage_context.persist(persist_dir=str(store_path))
        
        # Update in-memory representation
        vs_info["index"] = index

        # Add document metadata
        doc_id = str(uuid.uuid4())
        doc_info = {
            "id": doc_id,
            "name": document.document_name,
            "type": document.document_type
        }
        vs_info["documents"].append(doc_info)
        
        # Save updated metadata
        save_store_metadata(store_id, vs_info)

        return {"document_id": doc_id, "store_id": store_id, "status": "added"}

    except Exception as e:
        logger.exception(f"Error adding document: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    finally:
        # Clean up temp file
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Error cleaning up temp file: {e}")


@router.get("/", summary="List all vector stores")
async def list_vector_stores():
    return [
        {
            "id": store_id,
            "name": store_info["name"],
            "document_count": len(store_info["documents"])
        } for store_id, store_info in vector_stores.items()
    ]


@router.get("/{store_id}", summary="Get details of a specific vector store")
async def get_vector_store(store_id: str = Path(..., description="Vector store ID")):
    if store_id not in vector_stores:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vector store not found")

    store_info = vector_stores[store_id]
    return {
        "id": store_id,
        "name": store_info["name"],
        "documents": store_info["documents"],
        "config": {k: v for k, v in store_info["config"].items() if k != "api_key"}
    }


@router.delete("/{store_id}", status_code=status.HTTP_200_OK, summary="Delete a vector store")
async def delete_vector_store(store_id: str = Path(..., description="Vector store ID")):
    if store_id not in vector_stores:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vector store not found")

    try:
        store_path = VECTOR_BASE_DIR / store_id
        if store_path.exists():
            shutil.rmtree(store_path)

        del vector_stores[store_id]
        return {"status": "deleted", "store_id": store_id}
    except Exception as e:
        logger.exception(f"Error deleting vector store {store_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# Load existing vector stores during module initialization
load_vector_stores()