from fastapi import APIRouter, HTTPException, Body, Path, status,UploadFile, File,Query
from app.core.models import VectorStoreConfig
import uuid
import logging
import tempfile
import shutil
from pathlib import Path as FsPath  # Rename to avoid conflict with fastapi.Path
from llama_index.core import (
    SimpleDirectoryReader,
    VectorStoreIndex,
    StorageContext,
    load_index_from_storage
)
from llama_index.core.node_parser import SentenceSplitter
from datetime import datetime
import shutil
from app.utils.vector_store_utils import (
    vector_stores,
    get_embed_model,
    save_store_metadata,
    VECTOR_BASE_DIR
)
from app.utils.mongodb_client import MongoDBClient
from io import BytesIO
import requests

router = APIRouter()

logger = logging.getLogger(__name__)

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
    file: UploadFile = File(...)
):
    if store_id not in vector_stores:
        raise HTTPException(status_code=404, detail="Vector store not found")

    temp_path = None
    try:
        vs_info = vector_stores[store_id]
        config = vs_info.get("config", {})
        chunk_size = config.get("chunk_size", 512)
        chunk_overlap = config.get("chunk_overlap", 100)

        embed_model = vs_info["embed_model"]
        store_path = VECTOR_BASE_DIR / store_id

        suffix = FsPath(file.filename).suffix or ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_path = FsPath(temp_file.name)

        reader = SimpleDirectoryReader(input_files=[str(temp_path)])
        documents = reader.load_data()

        splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        nodes = splitter.get_nodes_from_documents(documents)

        index = vs_info.get("index")
        if not index:
            try:
                storage_context = StorageContext.from_defaults(persist_dir=str(store_path))
                index = load_index_from_storage(storage_context, embed_model=embed_model)
            except Exception as e:
                logger.warning(f"Could not load index from disk: {e}, creating a new one.")
                index = VectorStoreIndex(nodes=[], embed_model=embed_model)

        index.insert_nodes(nodes)
        index.storage_context.persist(persist_dir=str(store_path))
        vs_info["index"] = index

        doc_id = str(uuid.uuid4())
        doc_info = {
            "id": doc_id,
            "name": file.filename,
            "type": suffix.lstrip("."),
            "uploaded_at": datetime.utcnow().isoformat()
        }
        vs_info["documents"].append(doc_info)
        save_store_metadata(store_id, vs_info)

        return {
            "status": "success",
            "store_id": store_id,
            "document_id": doc_id,
            "filename": file.filename,
            "message": "Document added and indexed"
        }

    except Exception as e:
        logger.exception(f"Error adding document to vector store {store_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process and embed the document")

    finally:
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to clean up temp file: {e}")


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


@router.post("/{store_id}/load_from_knowledgebase", status_code=status.HTTP_201_CREATED)
async def load_documents_from_mongo(
    store_id: str = Path(..., description="Vector store ID"),
    knowledgebase_id: str = Query(..., description="Knowledgebase MongoDB document ID")
):
    if store_id not in vector_stores:
        raise HTTPException(status_code=404, detail="Vector store not found")

    try:
        # Fetch vector store info
        vs_info = vector_stores[store_id]
        config = vs_info.get("config", {})
        chunk_size = config.get("chunk_size", 512)
        chunk_overlap = config.get("chunk_overlap", 100)
        embed_model = vs_info["embed_model"]
        store_path = VECTOR_BASE_DIR / store_id

        # Load documents from MongoDB
        mongo_client = MongoDBClient()
        kb = mongo_client.get_knowledgebase_by_id(knowledgebase_id)
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledgebase not found")

        documents = kb.get("documents", [])
        if not documents:
            raise HTTPException(status_code=404, detail="No documents in knowledgebase")

        # Load or initialize index
        index = vs_info.get("index")
        if not index:
            try:
                storage_context = StorageContext.from_defaults(persist_dir=str(store_path))
                index = load_index_from_storage(storage_context, embed_model=embed_model)
            except Exception as e:
                logger.warning(f"Could not load index from disk: {e}, creating a new one.")
                index = VectorStoreIndex(nodes=[], embed_model=embed_model)

        added_docs = []

        for doc in documents:
            file_url = doc.get("filepath")
            filename = doc.get("filename")

            if not file_url or not filename:
                logger.warning(f"Skipping document with missing data: {doc}")
                continue

            # Download file from Cloudinary
            response = requests.get(file_url)
            if response.status_code != 200:
                logger.warning(f"Failed to download: {file_url}")
                continue

            file_bytes = BytesIO(response.content)

            # Save to temp file
            suffix = FsPath(filename).suffix or ".pdf"
            import tempfile
            # Create cross-platform temp file path
            temp_dir = tempfile.gettempdir()
            temp_path = FsPath(temp_dir) / f"{uuid.uuid4()}{suffix}"
            with open(temp_path, "wb") as f:
                f.write(file_bytes.read())

            # Load and parse
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

            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                logger.warning(f"Failed to delete temp file: {temp_path}")

        index.storage_context.persist(persist_dir=str(store_path))
        vs_info["index"] = index
        vs_info["documents"].extend(added_docs)
        save_store_metadata(store_id, vs_info)

        return {
            "status": "success",
            "store_id": store_id,
            "message": f"Added {len(added_docs)} documents from knowledgebase",
            "document_names": [d["name"] for d in added_docs]
        }

    except Exception as e:
        logger.exception("Failed to load documents from MongoDB")
        raise HTTPException(status_code=500, detail=str(e))