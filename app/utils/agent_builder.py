from livekit.plugins import openai, google, deepgram, groq
from google.cloud.texttospeech import VoiceSelectionParams
from livekit.agents.llm import function_tool

def build_llm_instance(provider: str, model: str, api_key: str):
    if provider == "gemini":
        return google.LLM(model=model, api_key=api_key)
    elif provider == "groq":
        return groq.LLM(model=model, api_key=api_key)
    return openai.LLM(model=model, api_key=api_key)

def build_stt_instance(provider: str, model: str, language: str, api_key: str):
    if provider == "deepgram":
        return deepgram.STT(model=model, language=language, api_key=api_key)
    return deepgram.STT(model="nova-3", language="en", api_key=api_key)

def build_tts_instance(provider: str, model: str, language: str):
    if provider == "google":
        return google.TTS(voice=VoiceSelectionParams(name=model, language_code=language))
    return google.TTS(voice=VoiceSelectionParams(name="en-IN-Chirp3-HD-Charon", language_code="en-IN"))
