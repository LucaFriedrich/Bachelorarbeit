
# llm/shared/llm_factory.py

import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_community.chat_models import ChatOllama
from langchain_core.language_models import BaseChatModel
from openai import max_retries

from logger import get_logger

# Lade .env Datei BEVOR wir Umgebungsvariablen lesen
load_dotenv()

logger = get_logger(__name__)

# Embedding-Modell konfigurierbar über Umgebungsvariable
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")

# Ollama Base URL konfigurierbar über Umgebungsvariable
# Für HTW-Cluster: OLLAMA_BASE_URL=https://f2ki-h100-1.f2.htw-berlin.de:11435
# OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# print(f"{OLLAMA_BASE_URL} wird als Ollama Base URL verwendet.")
# Modell → Provider Mapping mit Beschreibungen
MODEL_TO_PROVIDER = {
    # OpenAI Modelle
    "gpt-4o": "openai",                       # Standard Modell von OpenAI, ausgewogen
    "gpt-4o-mini": "openai",                  # Günstiges Modell von OpenAI, schnell
    "gpt-5": "openai",                        # Neuestes unified Modell (August 2025), beste Performance
    "o3": "openai",                           # Neuestes Reasoning Modell, stark bei komplexen Aufgaben
    
    # Claude Modelle  
    "claude-3-5-sonnet-20241022": "claude",  # Claude 3.5 Sonnet - sehr gut bei Analyse
    "claude-3-5-haiku-20241022": "claude",   # Claude 3.5 Haiku - günstig und schnell
    "claude-3-7-sonnet-20250219": "claude",  # Claude 3.7 Sonnet - Hybrid mit Reasoning
    "claude-sonnet-4-20250514": "claude",    # Claude Sonnet 4 - Hybrid, 64K Output
    "claude-opus-4-20250514": "claude",      # Claude Opus 4 - bestes Coding Modell
    "claude-opus-4-1-20250805": "claude",    # Claude Opus 4.1 - neueste Version, 74.5% SWE-bench
    
    # Ollama Modelle (HTW-Cluster via OLLAMA_BASE_URL)
    "qwen:110b": "ollama",                    # Qwen 110B - STÄRKSTES Modell! 
    "llama3.3:70b": "ollama",                 # Llama 3.3 70B - Neueste Llama
    "deepseek-r1:70b": "ollama",              # DeepSeek R1 70B - Reasoning-Spezialist
    "qwen3:32b": "ollama",                    # Qwen 3 32B - Schneller & gut
}



def get_llm(model: str,temperature: float = 0.1,**kwargs) -> BaseChatModel:
    """
    Zentrale Factory für LLM-Instanzen.
    
    Args:
        model: Modellname (z.B. "claude-3-5-sonnet-20241022", "gpt-4o")
        temperature: Temperatur für die Generierung
        **kwargs: Zusätzliche Parameter für das Modell
        
    Returns:
        BaseChatModel: Konfigurierte LLM-Instanz
        
    Raises:
        ValueError: Bei unbekanntem Modell
    """
    
    if model not in MODEL_TO_PROVIDER:
        raise ValueError(f"Unbekanntes Modell: {model}. Verfügbare: {list(MODEL_TO_PROVIDER.keys())}")
    
    provider = MODEL_TO_PROVIDER[model]
    logger.debug(f"Erstelle LLM: model={model}, provider={provider}")
    
    # LLM erstellen
    if provider == "openai":
        # o1, o3 und gpt-5 Modelle unterstützen keine temperature
        if model.startswith("o1") or model in ["o3", "gpt-5"]:
            llm = ChatOpenAI(
                model=model,
                **kwargs  # Keine temperature!
            )
        else:
            llm = ChatOpenAI(
                model=model,
                temperature=temperature,
                **kwargs
            )
    elif provider == "claude":
        llm = ChatAnthropic(
            model=model,
            temperature=temperature,
            **kwargs
        )
    
    elif provider == "ollama":
        # Ollama verwendet das Modell direkt ohne Präfix
        ollama_model = model.replace("ollama/", "") if model.startswith("ollama/") else model
        
        # HTW-Cluster nutzt HTTPS, lokale Installation HTTP
        # ChatOllama akzeptiert SSL-Verbindungen automatisch
        llm = ChatOllama(
            model=ollama_model,
            base_url=OLLAMA_BASE_URL,
            temperature=temperature,
            **kwargs
        )
        logger.info(f" Ollama LLM erstellt: {ollama_model} @ {OLLAMA_BASE_URL}")
        
        # Hinweis wenn HTW-URL verwendet wird
        if "htw-berlin" in OLLAMA_BASE_URL:
            logger.info("    Nutze HTW Berlin GPU-Cluster (VPN erforderlich!)")
        
    else:
        raise ValueError(f"Unbekannter LLM-Provider: {provider}")
    
    return llm


def get_embedding_model(provider: str = "openai"):
    """
    Gibt das Embedding-Modell für den Provider zurück.
    
    Args:
        provider: "openai" (Claude hat keine Embeddings)
        
    Returns:
        OpenAIEmbeddings oder None
        
    Raises:
        ValueError: Wenn Provider keine Embeddings unterstützt
    """
    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings
        logger.debug(f" Embedding-Modell: {EMBEDDING_MODEL}")
        return OpenAIEmbeddings(model=EMBEDDING_MODEL)
    else:
        raise ValueError(f"Provider {provider} unterstützt keine Embeddings")

if __name__ == "__main__":
    print("You tried to run the LLM factory directly. This is not allowed.")