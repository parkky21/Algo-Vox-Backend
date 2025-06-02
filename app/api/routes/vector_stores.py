from fastapi import APIRouter, HTTPException, Body, Path, status, UploadFile, File, Query, Request
from app.core.models import VectorStoreConfig
import logging
import tempfile
import shutil
from pathlib import Path as FsPath
from bson import ObjectId
from llama_index.core import (
    SimpleDirectoryReader,
    VectorStoreIndex,
    StorageContext,
    load_index_from_storage
)
from llama_index.core.node_parser import SentenceSplitter
from datetime import datetime
from app.utils.vector_store_utils import (
    get_embed_model,
    VECTOR_BASE_DIR,
    load_vector_store_from_mongo,
)
from app.utils.mongodb_client import MongoDBClient
from io import BytesIO
import requests
import uuid

router = APIRouter()
logger = logging.getLogger(__name__)
mongo_client = MongoDBClient()


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_vector_store(config: VectorStoreConfig = Body(...)):
    try:
        # Check if name already exists (optional uniqueness enforcement)
        existing = mongo_client.get_vector_store_by_name(config.name)
        if existing:
            raise HTTPException(status_code=409, detail="A vector store with this name already exists.")

        embed_model = get_embed_model(config.provider, config.api_key, config.model_name)
        index = VectorStoreIndex(nodes=[], embed_model=embed_model)

        # Save index to disk after inserting metadata
        metadata = {
            "name": config.name,
            "config": config.dict(),
            "documents": [],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        result = mongo_client.db["vector_stores"].insert_one(metadata)
        store_id = str(result.inserted_id)

        store_path = VECTOR_BASE_DIR / store_id
        store_path.mkdir(parents=True, exist_ok=True)
        index.storage_context.persist(persist_dir=str(store_path))

        return {"store_id": store_id, "name": config.name, "status": "created"}

    except Exception as e:
        logger.exception("Error creating vector store")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", summary="List all vector stores")
async def list_vector_stores():
    stores = mongo_client.list_vector_stores()
    return [
        {
            "id": str(s["_id"]),
            "name": s.get("name", "Unnamed"),
            "document_count": len(s.get("documents", []))
        }
        for s in stores
    ]


@router.get("/{store_id}", summary="Get details of a specific vector store")
async def get_vector_store(store_id: str = Path(..., description="Vector store ID")):
    try:
        key = ObjectId(store_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid vector store ID")

    store_info = mongo_client.get_vector_store(key)
    if not store_info:
        raise HTTPException(status_code=404, detail="Vector store not found")

    return {
        "id": str(store_info["_id"]),
        "name": store_info["name"],
        "documents": store_info["documents"],
        "config": {k: v for k, v in store_info["config"].items() if k != "api_key"}
    }


@router.delete("/{store_id}", summary="Delete a vector store")
async def delete_vector_store(store_id: str = Path(..., description="Vector store ID")):
    try:
        key = ObjectId(store_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid vector store ID")

    store_info = mongo_client.get_vector_store(key)
    if not store_info:
        raise HTTPException(status_code=404, detail="Vector store not found")

    try:
        store_path = VECTOR_BASE_DIR / store_id
        if store_path.exists():
            shutil.rmtree(store_path)

        mongo_client.delete_vector_store(key)
        return {"status": "deleted", "store_id": store_id}
    except Exception as e:
        logger.exception(f"Error deleting vector store {store_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{store_id}/load_from_knowledgebase", status_code=status.HTTP_201_CREATED)
async def load_documents_from_mongo(
    store_id: str = Path(..., description="Vector store ID"),
    knowledgebase_id: str = Query(..., description="Knowledgebase MongoDB document ID")
):
    try:
        vs_info = load_vector_store_from_mongo(store_id)

        config = vs_info["config"]
        chunk_size = config.get("chunk_size", 512)
        chunk_overlap = config.get("chunk_overlap", 100)
        embed_model = vs_info["embed_model"]
        index = vs_info["index"]
        store_path = VECTOR_BASE_DIR / store_id

        kb = mongo_client.get_knowledgebase_by_id(knowledgebase_id)
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledgebase not found")

        documents = kb.get("documents", [])
        if not documents:
            raise HTTPException(status_code=404, detail="No documents in knowledgebase")

        added_docs = []

        for doc in documents:
            file_url = doc.get("filepath")
            filename = doc.get("filename")

            if not file_url or not filename:
                logger.warning(f"Skipping document with missing data: {doc}")
                continue

            response = requests.get(file_url)
            if response.status_code != 200:
                logger.warning(f"Failed to download: {file_url}")
                continue

            file_bytes = BytesIO(response.content)
            suffix = FsPath(filename).suffix or ".pdf"
            temp_path = FsPath(tempfile.gettempdir()) / f"{uuid.uuid4()}{suffix}"

            with open(temp_path, "wb") as f:
                f.write(file_bytes.read())

            try:
                reader = SimpleDirectoryReader(input_files=[str(temp_path)])
                loaded_docs = reader.load_data()
                splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                nodes = splitter.get_nodes_from_documents(loaded_docs)
                index.insert_nodes(nodes)

                doc_id = str(uuid.uuid4())
                added_docs.append({
                    "id": doc_id,
                    "name": filename,
                    "source": "cloudinary",
                    "uploaded_at": datetime.utcnow().isoformat()
                })

            finally:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    logger.warning(f"Failed to delete temp file: {temp_path}")

        index.storage_context.persist(persist_dir=str(store_path))

        vs_info["documents"].extend(added_docs)
        vs_info["updated_at"] = datetime.utcnow().isoformat()
        update_payload = {k: v for k, v in vs_info.items() if k not in ("index", "embed_model")}
        update_payload["id"] = str(vs_info["_id"])
        mongo_client.save_vector_store(update_payload)

        return {
            "status": "success",
            "store_id": store_id,
            "message": f"Added {len(added_docs)} documents from knowledgebase",
            "document_names": [d["name"] for d in added_docs]
        }

    except HTTPException as http_exc:
        raise http_exc  # Let FastAPI handle known exceptions cleanly
    except Exception as e:
        logger.exception("Failed to load documents from MongoDB")
        raise HTTPException(status_code=500, detail="Internal server error while loading documents")
