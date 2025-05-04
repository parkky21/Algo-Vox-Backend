# app/core/models.py
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class ModelParameter(BaseModel):
    key: str
    value: str

class ModelConfig(BaseModel):
    provider: str
    model_name: str
    additionalParameters: List[ModelParameter] = []

class AgentConfig(BaseModel):
    agent_id: Optional[str] = None
    name: str
    instructions: str
    vector_store_ids: List[str]
    STT: Optional[ModelConfig] = None
    TTS: Optional[ModelConfig] = None
    LLM: ModelConfig

class ConnectAgentRequest(BaseModel):
    agent_id: str
    room_name:Optional [str]=None
    token: Optional [str]= None
    config: Optional[Dict[str, Any]] = None

class VectorStoreConfig(BaseModel):
    name: str
    provider: str
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    store_id: Optional[str] = None

class DocumentUpload(BaseModel):
    store_id: str
    document_name: str
    document_content: str
    document_type: str = "text"
