# llm/evaluate/relationship_evaluator.py

from typing import List, Dict, Any
from llm.evaluate.base import BaseEvaluator, KompetenzResult
from llm.evaluate.factory import register_evaluator
from llm.shared.llm_factory import get_llm
import json
from logger import get_logger

logger = get_logger(__name__)


@register_evaluator("relationships")
class RelationshipEvaluator(BaseEvaluator):
    """
    Evaluator für die Analyse von Beziehungen zwischen Dokumenten
    basierend auf bereits extrahierten Kompetenzen.
    
    KEIN RAG - nutzt direkt die KompetenzResults aus Phase 3.
    """
    
    def __init__(self, model: str, **kwargs):
        from llm.shared.llm_factory import MODEL_TO_PROVIDER
        provider = MODEL_TO_PROVIDER.get(model, "openai")
        super().__init__(provider, use_rag=False)  # KEIN RAG
        
        self.llm = get_llm(model=model, temperature=0.1)
        logger.info(f"RelationshipEvaluator mit {model} initialisiert (ohne RAG)")
    
    def evaluate(self, content: Any, **kwargs) -> Dict[str, Any]:
        """Dummy evaluate method für BaseEvaluator - nutze analyze_relationships direkt"""
        return self.analyze_relationships(content)
    
    def analyze_relationships(self, kompetenz_results: List[KompetenzResult]) -> Dict[str, Any]:
        """
        Hauptfunktion: Analysiert alle Beziehungen zwischen den Dokumenten.
        
        Args:
            kompetenz_results: Liste von KompetenzResult-Objekten aus Phase 3
            
        Returns:
            Dict mit Beziehungsstatistiken
        """
        logger.info(f" Analysiere Beziehungen zwischen {len(kompetenz_results)} Dokumenten")
        
        # Zeige Input-Daten für Debugging
        logger.info(f" INPUT-DATEN für Beziehungsanalyse:")
        for i, result in enumerate(kompetenz_results, 1):
            logger.info(f"   {i}. {result.filename}: {len(result.kompetenzen)} Kompetenzen, Taxonomie: {result.taxonomiestufe}")
            if result.kompetenzen:
                logger.info(f"      Top-Kompetenzen: {', '.join(result.kompetenzen[:3])}")
        
        relationships = []
        
        # Paarweise Vergleiche
        for i, result1 in enumerate(kompetenz_results):
            for j, result2 in enumerate(kompetenz_results[i + 1:], i + 1):
                
                relationship = self._compare_documents(result1, result2)
                if relationship:
                    relationships.append(relationship)
        
        # Sequenzielle Beziehungen (gdp01 -> gdp02)
        sequential_rels = self._find_sequential_relationships(kompetenz_results)
        relationships.extend(sequential_rels)
        
        # Statistiken
        stats = self._calculate_statistics(relationships)
        
        logger.info(f" {len(relationships)} Beziehungen gefunden")
        
        return {
            "relationships": relationships,
            "statistics": stats
        }
    
    def _compare_documents(self, result1: KompetenzResult, result2: KompetenzResult) -> Dict[str, Any]:
        """Vergleicht zwei Dokumente mit verbessertem LLM-Prompt für maximale Beziehungsanalyse"""
        
        prompt = f"""Analysiere die Beziehung zwischen diesen Vorlesungsdokumenten:

 DOKUMENT 1: {result1.filename}
 Kompetenzen: {', '.join(result1.kompetenzen[:6])}
 Taxonomie: {result1.taxonomiestufe}
 Lernziele: {', '.join(result1.lernziele[:3]) if result1.lernziele else 'Keine'}

 DOKUMENT 2: {result2.filename}
 Kompetenzen: {', '.join(result2.kompetenzen[:6])}
 Taxonomie: {result2.taxonomiestufe}
 Lernziele: {', '.join(result2.lernziele[:3]) if result2.lernziele else 'Keine'}

Bestimme die Beziehung:

1. **Thematische Ähnlichkeit** (0.0-1.0): Behandeln sie verwandte Konzepte?
2. **Voraussetzung** (true/false): Müssen Konzepte aus Dok1 verstanden werden für Dok2?
3. **Kompetenz-Überlappung** (0.0-1.0): Wie stark überlappen die gelehrten Fähigkeiten?
4. **Aufbau-Beziehung** (true/false): Baut Dok2 direkt auf Dok1 auf?
5. **Schwierigkeitssteigerung** (true/false): Ist Dok2 komplexer als Dok1?

Beispiele:
- "Grundlagen Programmierung" → "Kontrollstrukturen": prerequisite=true, builds_upon=true
- "Arrays" ↔ "Schleifen": similarity=0.8, overlap=0.6
- "Java Basics" → "OOP": prerequisite=true, difficulty_increase=true

Antwort als JSON:
{{
    "similarity": 0.0-1.0,
    "prerequisite": true/false,
    "overlap": 0.0-1.0,
    "builds_upon": true/false,
    "difficulty_increase": true/false,
    "relationship_type": "prerequisite|similar|builds_upon|independent",
    "reason": "Detaillierte Begründung der Beziehung"
}}

WICHTIG: Sei großzügig mit Beziehungen - auch schwache Verbindungen sind wertvoll für spätere Queries!"""

        logger.debug(f" Sende Beziehungsvergleich an LLM: {result1.filename} <-> {result2.filename}")
        try:
            response = self.llm.generate(prompt)
            cleaned = response.strip().replace("```json", "").replace("```", "")
            logger.debug(f" LLM Response für {result1.filename}<->{result2.filename}: {cleaned[:200]}...")
            relationship = json.loads(cleaned)
            
            # Erweiterte Kriterien für "interessante" Beziehungen
            is_interesting = (
                relationship.get("similarity", 0) > 0.4 or  # Niedrigere Schwelle
                relationship.get("prerequisite") or
                relationship.get("builds_upon") or
                relationship.get("overlap", 0) > 0.3 or
                relationship.get("difficulty_increase")
            )
            
            if is_interesting:
                return {
                    "doc1": result1.filename,
                    "doc2": result2.filename,
                    **relationship
                }
            
        except Exception as e:
            logger.debug(f"Fehler bei {result1.filename} <-> {result2.filename}: {e}")
        
        return None
    
    def _find_sequential_relationships(self, results: List[KompetenzResult]) -> List[Dict[str, Any]]:
        """Findet aufeinanderfolgende Dateien (gdp01->gdp02)"""
        import re
        
        sequential = []
        sorted_results = sorted(results, key=lambda x: x.filename)
        
        for i in range(len(sorted_results) - 1):
            current = sorted_results[i]
            next_doc = sorted_results[i + 1]
            
            # Extrahiere Nummern
            num1 = re.search(r'(\d+)', current.filename)
            num2 = re.search(r'(\d+)', next_doc.filename)
            
            if num1 and num2 and int(num2.group(1)) == int(num1.group(1)) + 1:
                sequential.append({
                    "doc1": current.filename,
                    "doc2": next_doc.filename,
                    "similarity": 1.0,
                    "prerequisite": True,
                    "overlap": 0.8,
                    "reason": "Aufeinanderfolgende Vorlesungsfolien",
                    "type": "sequential"
                })
        
        return sequential
    
    def _calculate_statistics(self, relationships: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Berechnet erweiterte Statistiken für wilde Queries"""
        if not relationships:
            return {"total": 0}
        
        # Beziehungstypen zählen
        similar_count = sum(1 for r in relationships if r.get("similarity", 0) > 0.6)
        prerequisite_count = sum(1 for r in relationships if r.get("prerequisite"))
        builds_upon_count = sum(1 for r in relationships if r.get("builds_upon"))
        difficulty_increase_count = sum(1 for r in relationships if r.get("difficulty_increase"))
        high_overlap_count = sum(1 for r in relationships if r.get("overlap", 0) > 0.5)
        sequential_count = sum(1 for r in relationships if r.get("type") == "sequential")
        
        # Beziehungstypen gruppieren
        by_type = {}
        for rel in relationships:
            rel_type = rel.get("relationship_type", "unknown")
            by_type[rel_type] = by_type.get(rel_type, 0) + 1
        
        # Durchschnittswerte
        avg_similarity = sum(r.get("similarity", 0) for r in relationships) / len(relationships) if relationships else 0
        avg_overlap = sum(r.get("overlap", 0) for r in relationships) / len(relationships) if relationships else 0
        
        return {
            "total": len(relationships),
            "by_type": by_type,
            "highly_similar": similar_count,
            "prerequisites": prerequisite_count,
            "builds_upon": builds_upon_count,
            "difficulty_increases": difficulty_increase_count,
            "high_overlap": high_overlap_count,
            "sequential": sequential_count,
            "avg_similarity": round(avg_similarity, 2),
            "avg_overlap": round(avg_overlap, 2),
            # Für wilde Queries interessant:
            "strongest_connections": sorted(relationships, key=lambda x: x.get("similarity", 0) + x.get("overlap", 0), reverse=True)[:3],
            "learning_path_nodes": prerequisite_count + builds_upon_count  # Für Lernpfad-Konstruktion
        }