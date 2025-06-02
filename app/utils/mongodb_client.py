from pymongo import MongoClient
from bson import ObjectId
from typing import Optional, Dict, Any, List, Union
import logging
from dotenv import load_dotenv
from app.core.config import Settings

load_dotenv()
logger = logging.getLogger(__name__)


class MongoDBClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.client = None
            cls._instance.db = None
        return cls._instance

    def connect(self):
        try:
            mongo_uri = Settings.MONGODB_URI
            db_name = Settings.MONGODB_NAME
            self.client = MongoClient(mongo_uri)
            self.db = self.client[db_name]
            logger.info(f"Connected to MongoDB at {mongo_uri}, DB: {db_name}")
            return True
        except Exception as e:
            logger.exception("Failed to connect to MongoDB")
            return False

    def _ensure_connection(self):
        if not self.client:
            self.connect()

    def _normalize_id(self, id_str: Union[str, ObjectId]) -> Union[str, ObjectId]:
        if isinstance(id_str, ObjectId):
            return id_str
        try:
            return ObjectId(id_str)
        except Exception:
            return id_str

    # ---------------- Flows ---------------- #
    def get_flow_by_id(self, flow_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_connection()
        try:
            key = self._normalize_id(flow_id)
            return self.db["flows"].find_one({"_id": key})
        except Exception as e:
            logger.error(f"Error retrieving flow {flow_id}: {e}")
            return None

    def get_all_flows(self) -> List[Dict[str, Any]]:
        self._ensure_connection()
        try:
            return list(self.db["flows"].find())
        except Exception as e:
            logger.error("Error retrieving all flows")
            return []

    def update_flow(self, flow_id: str, updates: Dict[str, Any]) -> bool:
        self._ensure_connection()
        try:
            key = self._normalize_id(flow_id)
            result = self.db["flows"].update_one({"_id": key}, {"$set": updates})
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating flow {flow_id}: {e}")
            return False

    def create_flow(self, flow_data: Dict[str, Any]) -> Optional[str]:
        self._ensure_connection()
        try:
            result = self.db["flows"].insert_one(flow_data)
            return str(result.inserted_id)
        except Exception as e:
            logger.error("Error creating flow")
            return None

    def delete_flow(self, flow_id: str) -> bool:
        self._ensure_connection()
        try:
            key = self._normalize_id(flow_id)
            result = self.db["flows"].delete_one({"_id": key})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting flow {flow_id}: {e}")
            return False

    # ---------------- Knowledgebases ---------------- #
    def get_knowledgebase_by_id(self, kb_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_connection()
        try:
            key = self._normalize_id(kb_id)
            return self.db["knowledgebases"].find_one({"_id": key})
        except Exception as e:
            logger.error(f"Error retrieving knowledgebase {kb_id}: {e}")
            return None

    def list_knowledgebases(self, owner_id: Optional[str] = None) -> List[Dict[str, Any]]:
        self._ensure_connection()
        try:
            query = {"owner": self._normalize_id(owner_id)} if owner_id else {}
            return list(self.db["knowledgebases"].find(query))
        except Exception as e:
            logger.error("Error listing knowledgebases")
            return []

    # ---------------- Vector Stores ---------------- #
    def save_vector_store(self, store_data: Dict[str, Any]) -> bool:
        """Insert or update a vector store using `_id` as ObjectId"""
        self._ensure_connection()
        try:
            store_id = store_data.get("id")
            object_id = self._normalize_id(store_id)
            store_data["_id"] = object_id
            result = self.db["vector_stores"].update_one(
                {"_id": object_id},
                {"$set": store_data},
                upsert=True
            )
            return result.acknowledged
        except Exception as e:
            logger.error(f"Error saving vector store {store_data.get('id')}: {e}")
            return False

    def get_vector_store(self, store_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        self._ensure_connection()
        try:
            key = self._normalize_id(store_id)
            return self.db["vector_stores"].find_one({"_id": key})
        except Exception as e:
            logger.error(f"Error retrieving vector store {store_id}: {e}")
            return None

    def get_vector_store_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        self._ensure_connection()
        try:
            return self.db["vector_stores"].find_one({"name": name})
        except Exception as e:
            logger.error(f"Error finding vector store by name: {name}")
            return None

    def delete_vector_store(self, store_id: Union[str, ObjectId]) -> bool:
        self._ensure_connection()
        try:
            key = self._normalize_id(store_id)
            result = self.db["vector_stores"].delete_one({"_id": key})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting vector store {store_id}: {e}")
            return False

    def list_vector_stores(self) -> List[Dict[str, Any]]:
        self._ensure_connection()
        try:
            cursor = self.db["vector_stores"].find({}, {"_id": 1, "name": 1, "documents": 1})
            return list(cursor)
        except Exception as e:
            logger.error("Error listing vector stores")
            return []

    # ---------------- Teardown ---------------- #
    def close(self):
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            logger.info("MongoDB connection closed")
