"""
JSON Utility Functions für LLM Response Parsing
================================================
Zentrale Funktionen zur Bereinigung und Parsing von LLM JSON-Antworten.
"""

import json
from logger import get_logger
from typing import Any, Dict, Optional

logger = get_logger(__name__)


def clean_json_response(content: str, provider: Optional[str] = None) -> str:
    """
    Bereinigt LLM-Antworten von Markdown-Code-Blöcken für JSON-Parsing.
    
    Unterstützt sowohl Standard-Bereinigung (für alle Modelle) als auch
    provider-spezifische Anpassungen (z.B. für Claude).
    
    Args:
        content: Rohe LLM-Antwort
        provider: Optional - LLM Provider ('claude', 'openai', etc.)
                 Wenn None, wird nur Standard-Bereinigung durchgeführt
        
    Returns:
        Bereinigter JSON-String
    """
    content = content.strip()
    
    # Standard-Bereinigung für alle Modelle
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    
    if content.endswith("```"):
        content = content[:-3]
    
    content = content.strip()
    
    # CLAUDE-SPEZIFISCHE Bereinigung nur bei Claude-Modellen
    if provider == "claude":
        logger.debug(" Claude-spezifische JSON-Bereinigung aktiv")
        
        # Robuste JSON-Extraktion: Finde JSON-Block wenn vorhanden
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        
        if json_start != -1 and json_end > json_start:
            extracted = content[json_start:json_end]
            logger.debug(f" JSON extrahiert: {len(extracted)} Zeichen (Original: {len(content)})")
            content = extracted
    
    # WICHTIG: Escape newlines in String-Werten für valides JSON
    # Dies behebt das Problem mit mehrzeiligen Feedback-Texten
    try:
        # Versuche erst zu parsen - wenn es klappt, ist alles gut
        json.loads(content)
    except json.JSONDecodeError:
        # Claude-spezifisch: Aggressiveres Newline-Escaping
        if provider == "claude":
            import re
            # Finde alle String-Werte zwischen Quotes und escape Newlines darin
            def escape_newlines_in_strings(match):
                # Escape alle Newlines innerhalb des gefundenen Strings
                return match.group(0).replace('\n', '\\n')
            
            # Pattern für JSON String-Werte: "..." aber nicht bereits escaped \"
            content = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', escape_newlines_in_strings, content)
            logger.debug(" Claude: Newlines in allen JSON-Strings escaped")
        else:
            # Standard-Ansatz für andere Provider
            import re
            content = re.sub(r'(?<!\\)\n(?!["\s]*[,}])', r'\\n', content)
            logger.debug(" Newlines in JSON-Strings escaped")
    
    return content


def parse_llm_json(content: str, provider: Optional[str] = None) -> Dict[str, Any]:
    """
    Parst JSON aus LLM-Antworten mit automatischer Bereinigung.
    
    Args:
        content: Rohe LLM-Antwort
        provider: Optional - LLM Provider für spezifische Bereinigung
        
    Returns:
        Geparste JSON als Dictionary
        
    Raises:
        json.JSONDecodeError: Wenn JSON nicht geparst werden kann
        ValueError: Wenn bereinigter Content kein valides JSON ist
    """
    cleaned = clean_json_response(content, provider)
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"JSON Parse Error: {e}")
        logger.debug(f"Bereinigte Antwort war: {cleaned[:500]}...")
        raise ValueError(f"Fehler beim Parsen der LLM-Antwort: {e}")