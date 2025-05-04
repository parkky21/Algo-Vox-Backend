# app/api/routes/vector_stores.py
from fastapi import APIRouter, HTTPException, Body
from app.core.models import VectorStoreConfig, DocumentUpload
from typing import Optional, List
import uuid
import logging
import tempfile
from pathlib import Path
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
# from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.gemini import GeminiEmbedding
from llama_index.core.node_parser import SentenceSplitter

router = APIRouter()

logger = logging.getLogger(__name__)

vector_stores = {}
embed_model = ""

@router.post("/")
async def create_vector_store(config: VectorStoreConfig = Body(...)):
    store_id = config.store_id or str(uuid.uuid4())
    if store_id in vector_stores:
        raise HTTPException(status_code=400, detail="Vector store ID already exists")

    try:
        if config.provider.lower() == "openai":
            embeddings = OpenAIEmbedding(api_key=config.api_key)
        # elif config.provider.lower() == "huggingface":
        #     model_name = config.model_name or "sentence-transformers/all-mpnet-base-v2"
        #     embeddings = HuggingFaceEmbedding(model_name=model_name)
        elif config.provider.lower() in {"google", "gemini"}:
            model_name = config.model_name or "models/embedding-001"
            embeddings = GeminiEmbedding(api_key=config.api_key, model=model_name)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported embeddings provider: {config.provider}")

        global embed_model
        embed_model = embeddings

        index = VectorStoreIndex(nodes=[], embed_model=embeddings)
        vector_stores[store_id] = {
            "id": store_id,
            "name": config.name,
            "config": config.dict(),
            "index": index,
            "documents": []
        }
        return {"store_id": store_id, "name": config.name, "status": "created"}

    except Exception as e:
        logger.error(f"Error creating vector store: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create vector store: {str(e)}")

@router.post("/{store_id}/documents")
async def add_document(store_id: str, document: DocumentUpload):
    if store_id not in vector_stores:
        raise HTTPException(status_code=404, detail="Vector store not found")
    
    try:
        vs_info = vector_stores[store_id]
        config = vs_info.get("config", {"chunk_size": 512, "chunk_overlap": 100})
        index = vs_info["index"]

        suffix = f".{document.document_type}" if document.document_type else ".txt"
        with tempfile.NamedTemporaryFile(delete=False, mode="w+", suffix=suffix) as temp_file:
            temp_file.write(document.document_content)
            temp_path = Path(temp_file.name)

        reader = SimpleDirectoryReader(input_files=[str(temp_path)])
        documents = reader.load_data()

        splitter = SentenceSplitter(
            chunk_size=config.get("chunk_size", 512),
            chunk_overlap=config.get("chunk_overlap", 100)
        )
        nodes = splitter.get_nodes_from_documents(documents)

        index.insert_nodes(nodes)

        doc_id = str(uuid.uuid4())
        vs_info.setdefault("documents", []).append({
            "id": doc_id,
            "name": document.document_name,
            "type": document.document_type
        })

        temp_path.unlink(missing_ok=True)
        return {"document_id": doc_id, "store_id": store_id, "status": "added"}

    except Exception as e:
        logger.exception("Error adding document")
        raise HTTPException(status_code=500, detail=f"Failed to add document: {str(e)}")

@router.get("")
async def list_vector_stores():
    return [
        {
            "id": store_id,
            "name": store_info["name"],
            "document_count": len(store_info["documents"])
        } for store_id, store_info in vector_stores.items()
    ]

@router.get("/{store_id}")
async def get_vector_store(store_id: str):
    if store_id not in vector_stores:
        raise HTTPException(status_code=404, detail="Vector store not found")

    store_info = vector_stores[store_id]
    return {
        "id": store_id,
        "name": store_info["name"],
        "documents": store_info["documents"],
        "config": {k: v for k, v in store_info["config"].items() if k != "api_key"}
    }

@router.delete("/{store_id}")
async def delete_vector_store(store_id: str):
    if store_id not in vector_stores:
        raise HTTPException(status_code=404, detail="Vector store not found")

    del vector_stores[store_id]
    return {"status": "deleted", "store_id": store_id}
