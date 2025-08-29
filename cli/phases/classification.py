"""
Phase 2: Course Classification

Klassifiziert den Kurs-Inhalt und bestimmt Fachbereich.
Nutzt die bewährte Logik aus test_complete_system.py.
"""
from logger import get_logger
from typing import Dict
from llm.evaluate.document_manager import DocumentManager
from llm.evaluate.factory import get_evaluator

logger = get_logger(__name__)


def run_classification(doc_manager: DocumentManager, course_name: str, 
                       model: str = "gpt-4o-mini") -> Dict:
    """
    Phase 2: Klassifiziert den Kurs basierend auf Inhalt.
    
    Analysiert die ersten 3 Dokumente um den Fachbereich zu bestimmen.
    Dies ist wichtig für die Auswahl der richtigen Prompts in Phase 3.
    
    Args:
        doc_manager: DocumentManager mit geladenen Dokumenten
        course_name: Name des Kurses
        model: LLM-Modell für Klassifikation
    
    Returns:
        Dict mit classification Ergebnissen:
        - fachbereich: z.B. "Informatik - Programmierung"
        - zielgruppe: z.B. "Bachelor 1. Semester"
        - schwerpunkt: z.B. "Grundlagen der Programmierung"
        - confidence: 0.0-1.0
        - begründung: Erklärung der Klassifikation
    """
    
    # Hole Dokumente des Kurses
    course_docs = doc_manager.get_course_documents(course_name)
    
    if not course_docs:
        logger.warning(f"Keine Dokumente für Kurs {course_name} gefunden!")
        return {}
    
    print(f"  Analysiere {len(course_docs)} Dokumente für Kurs-Klassifikation...")
    
    # Sammle Content aus ersten 3 Dokumenten für bessere Klassifikation
    sample_content = ""
    for doc_info in course_docs[:3]:
        filename = doc_info['filename']
        print(f"    Lade Sample aus: {filename}")
        
        # Hole komplettes Dokument (alle Chunks zusammen)
        doc_content = doc_manager.get_full_document(filename, course_name)
        if doc_content:
            # Nimm nur erste 1500 Zeichen pro Dokument
            sample_content += f"\n--- {filename} ---\n{doc_content[:1500]}\n"
    
    if not sample_content:
        logger.error("Kein Content für Klassifikation gefunden!")
        return {}
    
    # Erstelle Evaluator für Klassifikation
    print(f"  Nutze {model} für Klassifikation")
    evaluator = get_evaluator("kompetenz", model=model)
    
    print(f"\n  Klassifiziere Kursinhalt ({len(sample_content)} Zeichen)...")
    classification = evaluator.classify_course_content(sample_content)
    
    print(f"\n  KURS-KLASSIFIKATION:")
    print(f"    Fachbereich: {classification['fachbereich']}")
    print(f"    Zielgruppe: {classification['zielgruppe']}")
    print(f"    Schwerpunkt: {classification['schwerpunkt']}")
    print(f"    Confidence: {classification['confidence']:.2f}")
    print(f"    Begründung: {classification['begründung'][:200]}...")
    
    return classification