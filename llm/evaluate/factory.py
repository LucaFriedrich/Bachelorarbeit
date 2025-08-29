# llm/evaluate/factory.py

from llm.evaluate.base import BaseEvaluator
from typing import Dict, Type
from logger import get_logger

logger = get_logger(__name__)

# Registry für verfügbare Evaluator-Typen
EVALUATOR_REGISTRY: Dict[str, Type[BaseEvaluator]] = {}


def register_evaluator(eval_type: str):
    """Decorator zum Registrieren neuer Evaluator-Typen"""
    def decorator(cls):
        EVALUATOR_REGISTRY[eval_type] = cls
        # Registrierung nur bei Debug-Level
        logger.debug(f"Evaluator registriert: {eval_type} -> {cls.__name__}")
        return cls
    return decorator


def get_evaluator(eval_type: str, model: str, **kwargs) -> BaseEvaluator:
    """
    Factory-Funktion zum Erstellen von Evaluatoren.
    
    Args:
        eval_type: Typ des Evaluators (z.B. "summarize", "kompetenz", "aggregate")
        model: Modellname (z.B. "claude-3-5-sonnet-20241022", "gpt-4o")
        **kwargs: Zusätzliche Parameter für den Evaluator
        
    Returns:
        Instanz eines BaseEvaluator
        
    Raises:
        ValueError: Bei unbekanntem eval_type
    """
    # Lazy imports um zirkuläre Abhängigkeiten zu vermeiden
    if not EVALUATOR_REGISTRY:
        _load_evaluators()
    
    if eval_type not in EVALUATOR_REGISTRY:
        available = ", ".join(EVALUATOR_REGISTRY.keys())
        raise ValueError(f"Unbekannter Evaluator-Typ: {eval_type}. Verfügbar: {available}")
    
    evaluator_class = EVALUATOR_REGISTRY[eval_type]
    
    logger.debug(f"Erstelle {eval_type} Evaluator mit {model}")
    return evaluator_class(model=model, **kwargs)


def _load_evaluators():
    """Lädt alle verfügbaren Evaluator-Implementierungen"""
    # Imports hier, um zirkuläre Abhängigkeiten zu vermeiden
    from llm.evaluate.summarize_evaluator import SummarizeEvaluator
    from llm.evaluate.kompetenz_evaluator import KompetenzEvaluator
    from llm.evaluate.aggregate_evaluator import AggregateEvaluator
    from llm.evaluate.relationship_evaluator import RelationshipEvaluator
    # Weitere Evaluatoren können hier hinzugefügt werden