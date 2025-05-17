# app/core/models.py
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel

class ModelParameter(BaseModel):
    key: str
    value: str

class ModelConfig(BaseModel):
    provider: str
    model_name: str
    additionalParameters: List[ModelParameter] = []

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

class NodeRoute(BaseModel):
    tool_name: str
    next_node: str
    condition: Optional[str] = None

class NodeConfig(BaseModel):
    node_id: str
    node_name: str
    type: str
    speak_order: Optional[str] = None
    pause_before_speaking: Optional[int] = None
    prompt: Optional[str] = None
    static_sentence: Optional[str] = None
    skip_response: Optional[bool] = False
    global_node: Optional[bool] = False
    block_interruption: Optional[bool] = False
    routes: Optional[List[NodeRoute]] = None

class SpeechSettings(BaseModel):
    background_sound: Optional[str] = None
    responsiveness: Optional[float] = None
    interruption_sensitivity: Optional[float] = None
    enable_backchanneling: Optional[bool] = None
    transcription_mode: Optional[str] = None
    boosted_keywords: Optional[List[str]] = None
    enable_speech_normalization: Optional[bool] = None
    enable_transcript_formatting: Optional[bool] = None
    reminder_frequency: Optional[Dict[str, Any]] = None
    pronunciation_guidance: Optional[Dict[str, Any]] = None

class CallSettings(BaseModel):
    voicemail_detection: Optional[Dict[str, Any]] = None
    end_call_on_silence: Optional[Dict[str, Any]] = None
    max_call_duration_minutes: Optional[float] = None
    pause_before_speaking: Optional[int] = None
    ring_duration_seconds: Optional[int] = None

class LLMConfig(BaseModel):
    provider: str
    model: str
    api_key:str

class STTConfig(BaseModel):
    provider: str
    model: str
    language: str
    api_key:str

class TTSConfig(BaseModel):
    provider: str
    model: str
    language: str
    api_key: Union[str, dict]

class GlobalSettings(BaseModel):
    vector_store_id: Optional[str] = None 
    global_prompt: str
    llm: LLMConfig
    stt: STTConfig
    tts: TTSConfig
    temperature: Optional[float] = 0.7
    speech_settings: Optional[SpeechSettings] = None
    call_settings: Optional[CallSettings] = None

class AgentConfig(BaseModel):
    # For Flow configs
    entry_node: Optional[str] = None
     # For both Lite and Flow configs
    global_settings: Optional[GlobalSettings] = None
    nodes: Optional[List[NodeConfig]] = None

class AgentResponse(BaseModel):
    agent_id: str
    message: str


class StartAgentRequest(BaseModel):
    agent_id: str
    agent_name: Optional[str] = None

class StopAgentRequest(BaseModel):
    agent_id: str
    room_name: Optional[str] = None

