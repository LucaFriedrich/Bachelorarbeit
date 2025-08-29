# llm/evaluate/base.py

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from logger import get_logger


class EvaluationResult(BaseModel):
    """Basis-Klasse für alle Evaluierungs-Ergebnisse"""
    raw_output: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SummaryResult(EvaluationResult):
    """Ergebnis einer Zusammenfassung"""
    summary: str
    key_points: List[str] = Field(default_factory=list)


class KompetenzResult(EvaluationResult):
    """Ergebnis der Kompetenzextraktion"""
    kompetenzen: List[str] = Field(default_factory=list)
    lernziele: List[str] = Field(default_factory=list)
    taxonomiestufe: str = "Nicht klassifiziert"
    begründung: str = ""
    kontext_chunks: List[Dict[str, Any]] = Field(default_factory=list)
    filename: Optional[str] = None
    topic_title: Optional[str] = None  # NEU: Prägnanter Titel für das Topic
    
    def get_summary(self) -> str:
        """Erstellt kompakte Zusammenfassung für Logging"""
        return f"{self.filename or 'Dokument'}: {len(self.kompetenzen)} Kompetenzen, {len(self.lernziele)} Lernziele, Taxonomie: {self.taxonomiestufe}"


class AggregatedResult(EvaluationResult):
    """Ergebnis einer Aggregation/Konsolidierung"""
    consolidated_items: List[str] = Field(default_factory=list)
    # NEU: Detaillierte Konsolidierungsinformationen mit Source-Tracking
    consolidated_items_detailed: List[Dict[str, Any]] = Field(default_factory=list)
    groupings: Dict[str, List[str]] = Field(default_factory=dict)
    statistics: Dict[str, Any] = Field(default_factory=dict)
    
    def get_summary(self) -> str:
        """Erstellt kompakte Zusammenfassung für Logging"""
        # Nutze detailed items wenn vorhanden, sonst alte Liste
        item_count = len(self.consolidated_items_detailed) if self.consolidated_items_detailed else len(self.consolidated_items)
        return f"Aggregation: {item_count} Kompetenzen, {len(self.groupings)} Bereiche"


class BaseEvaluator(ABC):
    """
    Abstrakte Basis-Klasse für alle Evaluatoren.
    Unterstützt verschiedene Evaluierungs-Typen und RAG mit ChromaDB.
    """
    
    def __init__(self, provider: str = "openai", use_rag: bool = True):
        self.logger = get_logger(self.__class__.__module__)
        self.provider = provider
        self.use_rag = use_rag
        self.logger.debug(f"{self.__class__.__name__} initialisiert mit {provider}, RAG: {use_rag}")
    
    @abstractmethod
    def evaluate(self, content: Any, **kwargs) -> EvaluationResult:
        """
        Hauptmethode für die Evaluierung.
        
        Args:
            content: Der zu evaluierende Inhalt (String, Liste, Dict, etc.)
            **kwargs: Zusätzliche Parameter
            
        Returns:
            EvaluationResult oder Subklasse davon
        """
        pass
    
    def get_rag_context(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Holt relevante Dokumente aus ChromaDB für RAG.
        
        Args:
            query: Suchanfrage
            k: Anzahl der Dokumente
            
        Returns:
            Liste von Kontext-Dokumenten
        """
        if not self.use_rag:
            return []
            
        try:
            from llm.chroma.chroma_ingest import get_vectorstore
            vectorstore = get_vectorstore()
            
            self.logger.debug(f"Suche {k} relevante Dokumente für RAG...")
            similar_docs = vectorstore.similarity_search(query, k=k)
            
            context_docs = []
            for doc in similar_docs:
                context_docs.append({
                    "content": doc.page_content,
                    "metadata": doc.metadata
                })
            
            self.logger.debug(f"Gefunden: {len(context_docs)} Dokumente")
            return context_docs
            
        except Exception as e:
            self.logger.error(f"Fehler beim RAG-Kontext abrufen: {e}")
            return []