# app/core/models.py
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel

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

class NodeRoute(BaseModel):
    tool_name: str
    next_node: str
    condition: str

class CustomFunction(BaseModel):
    name: str
    description: str
    code: str

class NodeConfig(BaseModel):
    node_id: str
    label: Optional[str] = None
    type: str
    speak_order: Optional[str] = None
    pause_before_speaking: Optional[int] = None
    prompt: Optional[str] = None
    static_sentence: Optional[str] = None
    skip_response: Optional[bool] = False
    global_node: Optional[bool] = False
    block_interruption: Optional[bool] = False
    routes: Optional[List[NodeRoute]] = None
    custom_function: Optional[CustomFunction] = None
    is_end_node : Optional[bool] = False
    detected_answering_machine: Optional[bool] = False

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

class BackgroundAudioConfig(BaseModel):
    enabled: bool = False
    ambient_volume: float = 0.8
    thinking_volume: float = 0.2

class GlobalSettings(BaseModel):
    vector_store_id: Optional[str] = None 
    global_prompt: str
    llm: LLMConfig
    stt: STTConfig
    tts: TTSConfig
    timeout_seconds: Optional[int] = None
    temperature: Optional[float] = 0.7
    speech_settings: Optional[SpeechSettings] = None
    call_settings: Optional[CallSettings] = None
    background_audio : Optional[BackgroundAudioConfig] = None

class AgentConfig(BaseModel):
    entry_node: Optional[str] = None
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

