# llm/evaluate/summarize_evaluator.py

from typing import Any, Dict
from langchain_core.messages import HumanMessage, SystemMessage
from llm.evaluate.base import BaseEvaluator, SummaryResult
from llm.evaluate.factory import register_evaluator
from llm.shared.llm_factory import get_llm
from llm.shared.json_utils import clean_json_response
import json


@register_evaluator("summarize")
class SummarizeEvaluator(BaseEvaluator):
    """
    Evaluator für Zusammenfassungen von Kursinhalten.
    Erster Schritt in der Chain: Reduziert umfangreiche Inhalte auf das Wesentliche.
    """
    
    def __init__(self, provider: str = "openai", use_rag: bool = False, model_type: str = "fast", **kwargs):
        super().__init__(provider, use_rag)
        
        # LLM über zentrale Factory
        self.llm = get_llm(
            provider=provider,
            model_type=model_type,
            temperature=kwargs.get("temperature", 0.1)
        )
        self.logger.info(f"SummarizeEvaluator mit {provider}/{model_type} initialisiert")
    
    def _clean_json_response(self, response_content: str) -> str:
        """
        Bereinigt LLM-Antworten von Markdown-Code-Blöcken für JSON-Parsing.
        Nutzt die zentrale json_utils Funktion.
        
        Args:
            response_content: Rohe LLM-Antwort
            
        Returns:
            Bereinigter JSON-String
        """
        # Nutze zentrale Funktion ohne provider (Standard-Bereinigung)
        return clean_json_response(response_content)
    
    def evaluate(self, content: Any, **kwargs) -> SummaryResult:
        """
        Erstellt eine strukturierte Zusammenfassung des Inhalts.
        
        Args:
            content: Der zu zusammenfassende Text
            **kwargs: 
                - focus: Worauf soll der Fokus liegen? (z.B. "Lernziele", "Methodik")
                - max_length: Maximale Länge der Zusammenfassung
        """
        focus = kwargs.get("focus", "Lernziele und vermittelte Kompetenzen")
        max_length = kwargs.get("max_length", 500)
        
        system_prompt = f"""Du bist ein Experte für Bildungsinhalte und Curriculumsentwicklung.
Deine Aufgabe ist es, Kursinhalte präzise zusammenzufassen mit Fokus auf: {focus}

Erstelle eine strukturierte Zusammenfassung und extrahiere die wichtigsten Punkte.
Die Zusammenfassung sollte nicht länger als {max_length} Wörter sein.

Antworte im JSON-Format:
{{
    "summary": "Die Zusammenfassung des Inhalts",
    "key_points": ["Wichtiger Punkt 1", "Wichtiger Punkt 2", ...]
}}"""

        user_prompt = f"Fasse folgenden Kursinhalt zusammen:\n\n{content}"
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        try:
            response = self.llm.invoke(messages)
            self.logger.debug(f"LLM-Response erhalten, Länge: {len(response.content)}")
            
            # Bereinige die Antwort von Markdown-Code-Blöcken
            cleaned_content = self._clean_json_response(response.content)
            result_json = json.loads(cleaned_content)
            
            return SummaryResult(
                summary=result_json.get("summary", ""),
                key_points=result_json.get("key_points", []),
                raw_output=response.content,
                metadata={
                    "provider": self.provider,
                    "focus": focus,
                    "content_length": len(str(content)),
                    "model": self.llm.model_name if hasattr(self.llm, 'model_name') else 'unknown'
                }
            )
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON-Parsing-Fehler: {e}")
            # Fallback: Nutze die Rohantwort
            return SummaryResult(
                summary=response.content if response else "Fehler bei Zusammenfassung",
                key_points=[],
                raw_output=response.content if response else "",
                metadata={"error": str(e), "provider": self.provider}
            )