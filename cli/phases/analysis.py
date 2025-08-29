"""
Phase 3: Individual Document Analysis

Analysiert einzelne Dokumente und extrahiert Kompetenzen.
Nutzt die bewährte Logik aus test_complete_system.py.
"""
from logger import get_logger
from typing import List, Dict
from llm.evaluate.document_manager import DocumentManager
from llm.evaluate.factory import get_evaluator

logger = get_logger(__name__)


def run_analysis(doc_manager: DocumentManager, classification: Dict, 
                course_name: str, model: str = "gpt-4o-mini") -> List:
    """
    Phase 3: Analysiert einzelne Dokumente mit spezialisierten Prompts.
    
    Nutzt die Klassifikation aus Phase 2 um die richtigen Prompts zu wählen.
    Jedes Dokument wird einzeln analysiert und Kompetenzen extrahiert.
    
    Args:
        doc_manager: DocumentManager mit geladenen Dokumenten
        classification: Klassifikation aus Phase 2
        course_name: Name des Kurses
        model: LLM-Modell für Analyse
    
    Returns:
        Liste von KompetenzResult Objekten für alle Dokumente
    """
    print(f"\n{'='*70}")
    print(f"  PHASE 3: EINZELDOKUMENT-ANALYSE")
    print(f"{'='*70}")
    
    fachbereich = classification.get('fachbereich', 'Sonstiges Informatik')
    print(f"  Nutze Prompts für Fachbereich: {fachbereich}")
    
    # Hole alle Dokumente des Kurses
    course_docs = doc_manager.get_course_documents(course_name)
    
    if not course_docs:
        logger.warning(f"Keine Dokumente für Kurs {course_name} gefunden!")
        return []
    
    print(f"  Nutze {model} für Einzelanalyse")
    print(f"  Analysiere {len(course_docs)} Dokumente...")
    
    # Erstelle Evaluator
    evaluator = get_evaluator("kompetenz", model=model)
    
    all_results = []
    
    # Analysiere jedes Dokument einzeln
    for i, doc_info in enumerate(course_docs, 1):
        filename = doc_info['filename']
        print(f"\n  [{i}/{len(course_docs)}] Analysiere: {filename}")
        
        try:
            # Nutze die intelligente Analyse mit Kontext
            result = evaluator.evaluate_full_document(
                source_file=filename,
                course_id=course_name,
                use_related_context=True  # Nutze andere Dokumente als Kontext
            )
            
            # Konsolidiere wenn zu viele Kompetenzen (>3)
            if result.kompetenzen and len(result.kompetenzen) > 3:
                print(f"    Konsolidiere {len(result.kompetenzen)} Kompetenzen...")
                consolidated = evaluator.consolidate_document_competencies(
                    result.kompetenzen, 
                    filename
                )
                result.kompetenzen = consolidated
                print(f"    → {len(consolidated)} konsolidierte Kompetenzen")
                
                # Optional: Speichere in Neo4j (wenn Graph-Integration aktiv)
                if hasattr(evaluator, 'save_competencies_to_neo4j'):
                    try:
                        node_mapping = evaluator.save_competencies_to_neo4j(
                            consolidated,
                            filename,
                            course_name
                        )
                        logger.debug(f"Kompetenzen in Neo4j gespeichert: {len(node_mapping)} Nodes")
                    except Exception as e:
                        logger.warning(f"Neo4j-Speicherung fehlgeschlagen: {e}")
                
                # Speichere auch Lernziele in Neo4j
                if hasattr(evaluator, 'save_lernziele_to_neo4j') and result.lernziele:
                    try:
                        lernziel_ids = evaluator.save_lernziele_to_neo4j(
                            result.lernziele,
                            filename,
                            course_name
                        )
                        logger.debug(f"Lernziele in Neo4j gespeichert: {len(lernziel_ids)} Nodes")
                    except Exception as e:
                        logger.warning(f"Neo4j Lernziel-Speicherung fehlgeschlagen: {e}")
                
                # Speichere Topic-Titel in Neo4j
                if hasattr(evaluator, 'save_topic_title_to_neo4j') and hasattr(result, 'topic_title') and result.topic_title:
                    try:
                        evaluator.save_topic_title_to_neo4j(
                            result.topic_title,
                            filename,
                            course_name
                        )
                        logger.debug(f"Topic-Titel in Neo4j gespeichert: {result.topic_title}")
                    except Exception as e:
                        logger.warning(f"Neo4j Topic-Titel-Speicherung fehlgeschlagen: {e}")
            
            if result.kompetenzen:
                print(f"{len(result.kompetenzen)} Kompetenzen extrahiert")
            else:
                print(f"Keine Kompetenzen extrahiert")
            
            all_results.append(result)
            
        except Exception as e:
            logger.error(f"Fehler bei {filename}: {e}")
            print(f"Fehler: {e}")
    
    # Zusammenfassung
    print(f"\n  ANALYSE-ZUSAMMENFASSUNG:")
    successful_analyses = [r for r in all_results if r.kompetenzen]
    total_kompetenzen = sum(len(r.kompetenzen) for r in successful_analyses)
    print(f"    Erfolgreiche Analysen: {len(successful_analyses)}/{len(course_docs)}")
    print(f"    Gesamt extrahierte Kompetenzen: {total_kompetenzen}")
    
    return all_results