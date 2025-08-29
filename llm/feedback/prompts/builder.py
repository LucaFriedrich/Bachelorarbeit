# llm/feedback/prompts/builder.py

from langchain.prompts import PromptTemplate
from typing import Dict

class FeedbackPromptBuilder:
    """
    Vereinfachter Prompt Builder mit einheitlichem Template für alle Programmiersprachen.
    """
    
    # Zentrale Definition der Kompetenz-Level (muss mit types.py synchron sein!)
    KOMPETENZ_LEVELS = [
        "nicht sichtbar",
        "oberflächlich", 
        "funktional erfüllt",
        "sicher angewendet",
        "besonders gut umgesetzt"
    ]
    
    # Mapping von Task-Types zu Sprachen für den Prompt
    LANGUAGE_MAP = {
        "python": "Python",
        "java": "Java", 
        "javascript": "JavaScript",
        "js": "JavaScript",
        "typescript": "TypeScript",
        "ts": "TypeScript",
        "cpp": "C++",
        "c": "C",
        "csharp": "C#",
        "cs": "C#",
        "go": "Go",
        "rust": "Rust",
        "php": "PHP",
        "ruby": "Ruby",
        "swift": "Swift",
        "kotlin": "Kotlin",
        "text": None  # Spezialfall für Text
    }
    
    # Einheitliches Template für alle Programmiersprachen
    CODE_TEMPLATE = """Du bist ein empathischer Informatik-Dozent mit Expertise in {language}-Programmierung.
Du bewertest keine Aufgaben im Sinne von Noten, sondern gibst personalisiertes, 
konstruktives Feedback zum Kompetenzstand eines Studierenden.

Kompetenzziel: {{kompetenz}}

Hier ist die studentische {language}-Abgabe:
```{language_lower}
{{abgabe}}
```

Bewerte die Abgabe in Bezug auf das Kompetenzziel und gib strukturiertes Feedback.

WICHTIG: Die Bewertungsstufen sind:
- "nicht sichtbar": Die Kompetenz ist in der Abgabe nicht erkennbar
- "oberflächlich": Grundlegendes Verständnis erkennbar, aber noch unsicher
- "funktional erfüllt": Die Kompetenz wird solide angewendet
- "sicher angewendet": Die Kompetenz wird routiniert und korrekt eingesetzt
- "besonders gut umgesetzt": Herausragende Anwendung mit kreativen Lösungen

Bitte antworte im JSON-Format mit GENAU diesen Feldern:
{{{{
  "kompetenz_erfüllt": "<eine der obigen Bewertungsstufen>",
  "beispielhafte_beobachtung": "<konkrete Stelle im Code, die deine Bewertung belegt>",
  "tipp": "<ein konkreter, umsetzbarer Verbesserungsvorschlag>",
  "komplettes_feedback": "<ausführliches, ermutigendes Feedback mit Stärken und Verbesserungsmöglichkeiten>"
}}}}

Achte darauf:
- Sei konkret und beziehe dich auf den tatsächlichen Code
- Formuliere ermutigend und wertschätzend
- Gib praktische, umsetzbare Tipps
- Erkenne auch kleine Fortschritte an"""

    TEXT_TEMPLATE = """Du bist ein erfahrener akademischer Schreibcoach.
Du hilfst Studierenden dabei, ihre Schreibfähigkeiten zu verbessern.

Kompetenzziel: {{kompetenz}}

Hier ist der eingereichte Text:
{{abgabe}}

Bewerte den Text in Bezug auf das Kompetenzziel.

WICHTIG: Die Bewertungsstufen sind:
- "nicht sichtbar": Die Kompetenz ist im Text nicht erkennbar
- "oberflächlich": Grundlegendes Verständnis erkennbar, aber noch unsicher
- "funktional erfüllt": Die Kompetenz wird solide angewendet
- "sicher angewendet": Die Kompetenz wird routiniert und korrekt eingesetzt
- "besonders gut umgesetzt": Herausragende Anwendung

Bitte antworte im JSON-Format mit GENAU diesen Feldern:
{{{{
  "kompetenz_erfüllt": "<eine der obigen Bewertungsstufen>",
  "beispielhafte_beobachtung": "<konkrete Textstelle, die deine Bewertung belegt>",
  "tipp": "<ein konkreter, umsetzbarer Verbesserungsvorschlag>",
  "komplettes_feedback": "<ausführliches, ermutigendes Feedback>"
}}}}"""
    
    @classmethod
    def get_prompt(cls, task_type: str) -> PromptTemplate:
        """
        Gibt den passenden Prompt für den Task-Type zurück.
        
        Args:
            task_type: Der Typ der Aufgabe (python, java, text, etc.)
            
        Returns:
            PromptTemplate mit dem passenden Template
            
        Raises:
            ValueError: Wenn der task_type unbekannt ist
        """
        task_type = task_type.lower()
        
        # Spezialfall: Text
        if task_type == "text":
            return PromptTemplate(
                input_variables=["kompetenz", "abgabe"],
                template=cls.TEXT_TEMPLATE
            )
        
        # Programmiersprachen
        if task_type in cls.LANGUAGE_MAP:
            language = cls.LANGUAGE_MAP[task_type]
            if language is None:
                raise ValueError(f"Task-Type '{task_type}' hat kein Language-Mapping")
            
            # Fülle das Template mit der Sprache
            filled_template = cls.CODE_TEMPLATE.format(
                language=language,
                language_lower=task_type
            )
            
            return PromptTemplate(
                input_variables=["kompetenz", "abgabe"],
                template=filled_template
            )
        
        raise ValueError(
            f"Unbekannter Task-Type: {task_type}. "
            f"Verfügbare Types: {', '.join(cls.LANGUAGE_MAP.keys())}"
        )
    
    @classmethod
    def get_extension_mapping(cls) -> Dict[str, str]:
        """
        Gibt ein Mapping von Dateiendungen zu Task-Types zurück.
        
        Returns:
            Dict mit Dateiendung -> task_type Mapping
        """
        return {
            ".py": "python",
            ".java": "java",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript", 
            ".tsx": "typescript",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".c": "c",
            ".h": "c",
            ".cs": "csharp",
            ".go": "go",
            ".rs": "rust",
            ".php": "php",
            ".rb": "ruby",
            ".swift": "swift",
            ".kt": "kotlin",
            ".kts": "kotlin",
            ".txt": "text",
            ".md": "text",
            ".tex": "text",
            ".rst": "text"
        }