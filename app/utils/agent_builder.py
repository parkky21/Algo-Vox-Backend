from livekit.plugins import openai, google, deepgram, groq
from google.cloud.texttospeech import VoiceSelectionParams
from typing import Optional

def build_llm_instance(provider: str, model: str, api_key: str, temperature: Optional[float]=None):
    if provider == "gemini":
        return google.LLM(model=model, api_key=api_key,temperature=temperature)
    elif provider == "groq":
        return groq.LLM(model=model, api_key=api_key,temperature=temperature)
    return openai.LLM(model=model, api_key=api_key,temperature=temperature)

def build_stt_instance(provider: str, model: str, language: str, api_key: str):
    if provider == "deepgram":
        return deepgram.STT(model=model, language=language, api_key=api_key)
    return deepgram.STT(model="nova-3", language="en", api_key=api_key)

def build_tts_instance(provider: str, model: str, language: str, credentials_info: dict | str = None):
    if provider == "google":
        return google.TTS(voice=VoiceSelectionParams(name=model, language_code=language),credentials_info=credentials_info)
    elif provider == "deepgram":
        return deepgram.TTS(model=model, language=language, credentials_info=credentials_info)
    return google.TTS(voice=VoiceSelectionParams(name="en-IN-Chirp3-HD-Charon", language_code="en-IN"),credentials_info=credentials_info)