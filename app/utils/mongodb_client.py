from pymongo import MongoClient
from typing import Optional, Dict, Any, List
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class MongoDBClient:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBClient, cls).__new__(cls)
            # Initialize with None - we'll connect lazily when needed
            cls._instance.client = None
            cls._instance.db = None
        return cls._instance
    
    def connect(self):
        """Connect to MongoDB using connection string from environment variables"""
        try:
            mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
            db_name = os.getenv("MONGODB_NAME", "ai-agent")
            
            print(f"Connecting to MongoDB at {mongo_uri} with database {db_name}")
            
            self.client = MongoClient(mongo_uri)
            self.db = self.client[db_name]
            logger.info(f"Connected to MongoDB database: {db_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            return False
    
    def get_flow_by_id(self, flow_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a flow document by its ID"""
        if not self.client:
            self.connect()
            
        try:
            # Get the flows collection
            flows_collection = self.db["flows"]
            
            # Query for the flow with the specified ID
            flow = flows_collection.find_one({"_id": flow_id})
            
            return flow
        except Exception as e:
            logger.error(f"Error retrieving flow with ID {flow_id}: {e}")
            return None
    
    def get_all_flows(self) -> List[Dict[str, Any]]:
        """Retrieve all flow documents"""
        if not self.client:
            self.connect()
            
        try:
            flows_collection = self.db["flows"]
            flows = list(flows_collection.find())
            return flows
        except Exception as e:
            logger.error(f"Error retrieving all flows: {e}")
            return []
    
    def update_flow(self, flow_id: str, updates: Dict[str, Any]) -> bool:
        """Update a flow document"""
        if not self.client:
            self.connect()
            
        try:
            flows_collection = self.db["flows"]
            result = flows_collection.update_one(
                {"_id": flow_id},
                {"$set": updates}
            )
            
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating flow with ID {flow_id}: {e}")
            return False
    
    def create_flow(self, flow_data: Dict[str, Any]) -> Optional[str]:
        """Create a new flow document"""
        if not self.client:
            self.connect()
            
        try:
            flows_collection = self.db["flows"]
            
            # If _id is not provided, MongoDB will generate one
            result = flows_collection.insert_one(flow_data)
            
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Error creating flow: {e}")
            return None
    
    def delete_flow(self, flow_id: str) -> bool:
        """Delete a flow document"""
        if not self.client:
            self.connect()
            
        try:
            flows_collection = self.db["flows"]
            result = flows_collection.delete_one({"_id": flow_id})
            
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting flow with ID {flow_id}: {e}")
            return False
    
    def close(self):
        """Close the MongoDB connection"""
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            logger.info("MongoDB connection closed")
