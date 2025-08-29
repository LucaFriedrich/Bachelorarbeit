"""
Entwicklungs-Cache für Pipeline-Ergebnisse.

NUR FÜR ENTWICKLUNG! Nicht für Produktion.
Cached das Ergebnis von Phase 1-3 komplett.

Aktivieren mit: DEV_CACHE=true in .env
"""
import pickle
import os
from pathlib import Path
from typing import Any, Optional, Tuple
from logger import get_logger

logger = get_logger(__name__)

CACHE_FILE = Path(".pipeline_cache.pkl")


def is_cache_enabled() -> bool:
    """Prüft ob Dev-Cache aktiviert ist (via Env-Variable)."""
    return os.getenv("DEV_CACHE", "").lower() == "true"


def get_cache_file(course_name: str) -> Path:
    """Gibt den Cache-Dateipfad für einen Kurs zurück."""
    cache_dir = Path(".cache")
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / f"{course_name}_analysis.pkl"


def has_cached_analysis(course_name: str) -> bool:
    """Prüft ob eine gecachte Analyse für den Kurs existiert."""
    if not is_cache_enabled():
        return False
    return get_cache_file(course_name).exists()


def save_pipeline_result(course_name: str, model: str, doc_manager: Any, 
                        classification: dict, analysis_results: list):
    """Speichert nur die serialisierbaren Ergebnisse (ohne DB-Verbindungen)."""
    if not is_cache_enabled():
        return
    
    try:
        # Speichere nur die Daten, nicht die Verbindungen
        data = {
            'course_name': course_name,
            'model': model,
            'classification': classification,
            'analysis_results': analysis_results
            # doc_manager wird NICHT gespeichert (enthält DB-Verbindungen)
        }
        cache_file = get_cache_file(course_name)
        with open(cache_file, 'wb') as f:
            pickle.dump(data, f)
        logger.info(f"Analyse für {course_name} wurde gecached")
    except Exception as e:
        logger.warning(f"Cache-Speicherung fehlgeschlagen: {e}")


def load_cached_analysis(course_name: str) -> Optional[Tuple[Any, dict, list, str]]:
    """Lädt Pipeline-Ergebnis und initialisiert DocumentManager neu."""
    if not is_cache_enabled():
        return None
    
    cache_file = get_cache_file(course_name)
    if not cache_file.exists():
        return None
    
    try:
        with open(cache_file, 'rb') as f:
            data = pickle.load(f)
        
        # DocumentManager neu initialisieren (verbindet sich mit ChromaDB/Neo4j)
        from llm.evaluate.document_manager import DocumentManager
        doc_manager = DocumentManager()
        
        logger.info(f"Gecachte Analyse geladen für {course_name}")
        logger.info(f"DocumentManager neu initialisiert")
        
        return (doc_manager, data['classification'], 
                data['analysis_results'], data['model'])
    except Exception as e:
        logger.warning(f"Cache-Laden fehlgeschlagen: {e}")
        # Bei korruptem Cache: Datei löschen
        if cache_file.exists():
            cache_file.unlink()
            logger.info("Korrupte Cache-Datei gelöscht")
        return None


def clear_cache():
    """Löscht den kompletten Cache."""
    cache_dir = Path(".cache")
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)
        logger.info("Cache-Verzeichnis gelöscht")