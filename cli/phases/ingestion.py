"""
Phase 1: Document Ingestion

Lädt Dokumente aus Moodle und bereitet sie für die Analyse vor.
Nutzt die bewährte Logik aus test_complete_system.py.

"""
import os
from logger import get_logger
from typing import Tuple, List, Dict
from pathlib import Path

from llm.evaluate.document_manager import DocumentManager
from llm.moodle import MoodleClient, CourseDownloader

logger = get_logger(__name__)


def run_ingestion(shortname: str) -> Tuple[DocumentManager, str, str]:
    """
    Phase 1: Lädt Dokumente aus Moodle für die Analyse.
    
    Diese Hauptfunktion orchestriert den gesamten Ingestion-Prozess:
    1. Verbindung zu Moodle aufbauen
    2. Kurs finden
    3. Dateien herunterladen
    4. In ChromaDB laden
    
    Args:
        shortname: Kurs-Shortname (z.B. "tk1")
    
    Returns:
        Tuple aus (DocumentManager, course_name, course_id)
    """
    # Moodle-Verbindung aufbauen
    client, downloader = get_moodle_client()
    
    # Kurs finden
    course = find_course(downloader, shortname)
    course_id = course['id']
    course_name = shortname
    
    # Download-Ordner vorbereiten
    download_dir = f"downloads/{course_name}"
    Path(download_dir).mkdir(parents=True, exist_ok=True)
    logger.info(f"Download-Verzeichnis: {download_dir}")
    
    # Kursinhalte herunterladen
    files, assignments = download_course_content(downloader, course_id, download_dir)
    
    # DocumentManager initialisieren
    logger.info("Initialisiere DocumentManager...")
    doc_manager = DocumentManager()
    
    # Dokumente in ChromaDB laden
    ingestion_results = ingest_to_chromadb(doc_manager, files, course_name)
    
    # Zusammenfassung
    print(f"{len(ingestion_results)} von {len(files)} Dokumenten erfolgreich geladen")
    
    if ingestion_results:
        total_chunks = sum(r['chunks_created'] for r in ingestion_results)
        print(f"{total_chunks} Chunks in ChromaDB erstellt")
    
    # Verifizierung
    course_docs = doc_manager.get_course_documents(course_name)
    logger.info(f"Verifiziert: {len(course_docs)} Dokumente in ChromaDB")
    
    return doc_manager, course_name, str(course_id)


def get_moodle_client() -> Tuple[MoodleClient, CourseDownloader]:
    """
    Initialisiert Moodle Client und Downloader.
    
    Returns:
        Tuple aus (MoodleClient, CourseDownloader)
    
    Raises:
        ValueError: Wenn Credentials fehlen
    """
    moodle_url = os.getenv('MOODLE_URL')
    moodle_token = os.getenv('MOODLE_TOKEN')
    
    if not moodle_url or not moodle_token:
        raise ValueError("MOODLE_URL und MOODLE_TOKEN müssen in .env gesetzt sein")
    
    logger.info(f"Verbinde mit Moodle: {moodle_url}")
    client = MoodleClient(moodle_url, moodle_token)
    downloader = CourseDownloader(client)
    
    return client, downloader


def find_course(downloader: CourseDownloader, shortname: str) -> Dict:
    """
    Findet einen Kurs per Shortname.
    
    Args:
        downloader: Moodle CourseDownloader
        shortname: Kurs-Shortname (z.B. "tk1")
    
    Returns:
        Kurs-Dictionary mit id, fullname, etc.
    
    Raises:
        ValueError: Wenn Kurs nicht gefunden
    """
    logger.info(f"Suche Kurs mit Shortname: {shortname}")
    course = downloader.get_course_by_shortname(shortname)
    
    if not course:
        raise ValueError(f"Kurs '{shortname}' nicht gefunden")
    
    return course


def download_course_content(downloader: CourseDownloader, course_id: int, 
                           download_dir: str) -> Tuple[List[str], List[Dict]]:
    """
    Lädt Kursmaterialien und Assignments herunter.
    
    Args:
        downloader: Moodle CourseDownloader
        course_id: Moodle Kurs-ID
        download_dir: Zielverzeichnis für Downloads
    
    Returns:
        Tuple aus (files, assignments)
    """
    # Kursmaterialien herunterladen
    print("Lade Kursmaterialien...")
    files = downloader.download_course_files(course_id, download_dir)
    print(f"{len(files)} Dateien heruntergeladen")
    
    # Assignments laden (für spätere Analyse)
    print("Lade Assignments...")
    assignments = downloader.get_course_assignments(course_id)
    print(f"{len(assignments)} Assignments gefunden")
    
    return files, assignments


def ingest_to_chromadb(doc_manager: DocumentManager, files: List[str], 
                       course_name: str) -> List[Dict]:
    """
    Lädt alle Dateien in ChromaDB.
    
    Args:
        doc_manager: DocumentManager Instanz
        files: Liste der Dateipfade
        course_name: Kursname für ChromaDB
    
    Returns:
        Liste der Ingestion-Ergebnisse
    """
    logger.info(f"Lade {len(files)} Dokumente in ChromaDB...")
    ingestion_results = []
    
    for i, filepath in enumerate(files, 1):
        filename = os.path.basename(filepath)
        logger.debug(f"[{i}/{len(files)}] Verarbeite {filename}")
        
        try:
            # Prüfe ob Datei existiert und nicht leer ist
            if not os.path.exists(filepath):
                logger.warning(f"Datei existiert nicht: {filename}")
                continue
            
            file_size = os.path.getsize(filepath)
            if file_size == 0:
                logger.warning(f"Datei ist leer (0 bytes): {filename}")
                continue
            
            result = doc_manager.ingest_course_document(
                file_path=filepath,
                course_id=course_name,
                chunk_size=1000,
                chunk_overlap=200
            )
            ingestion_results.append(result)
            logger.info(f"{filename}: {result['chunks_created']} chunks erstellt")
            
        except Exception as e:
            logger.error(f"Fehler bei {filename}: {e}")
    
    return ingestion_results