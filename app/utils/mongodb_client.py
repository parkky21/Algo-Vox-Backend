from pymongo import MongoClient
from bson import ObjectId
from typing import Optional, Dict, Any, List, Union
import logging
import os
from dotenv import load_dotenv

# Load env vars
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
        """Establish MongoDB connection"""
        try:
            mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
            db_name = os.getenv("MONGODB_NAME", "ai-agent")
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

    def _normalize_id(self, id_str: str) -> Union[str, ObjectId]:
        """Attempt to parse an ID string as ObjectId; fallback to raw string"""
        try:
            return ObjectId(id_str)
        except Exception:
            return id_str  # Fallback if not a valid ObjectId

    def get_flow_by_id(self, flow_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_connection()
        try:
            key = self._normalize_id(flow_id)
            return self.db["flows"].find_one({"_id": key})
        except Exception as e:
            logger.error(f"Error retrieving flow {_id}: {e}")
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

    def close(self):
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            logger.info("MongoDB connection closed")
