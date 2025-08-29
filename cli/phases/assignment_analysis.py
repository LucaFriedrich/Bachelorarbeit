"""
Phase T: Assignment Analysis
Analysiert Assignments und ordnet benötigte Kompetenzen zu.
"""
from logger import get_logger
import os
from typing import Dict, List, Optional
from llm.moodle import MoodleClient, CourseDownloader
from llm.evaluate.assignment_matcher import AssignmentCompetencyMatcher
import questionary

logger = get_logger(__name__)


def run_assignment_analysis(course_name: str, model: str = "gpt-4o-mini") -> Optional[Dict]:
    """
    Phase T: Analysiert Assignments und matched sie zu Kompetenzen.
    
    Holt Assignments aus Moodle, lässt User eines wählen,
    und ordnet dann passende Kompetenzen aus Neo4j zu.
    
    Args:
        course_name: Name/Shortname des Kurses
        model: LLM-Modell für Matching
    
    Returns:
        Dict mit Assignment-Info und zugeordneten Kompetenzen
    """
    
    # Moodle-Verbindung
    moodle_url = os.getenv('MOODLE_URL')
    moodle_token = os.getenv('MOODLE_TOKEN')
    
    if not moodle_url or not moodle_token:
        logger.error("Moodle-Credentials fehlen in .env!")
        return None
    
    try:
        # Moodle Client
        client = MoodleClient(moodle_url, moodle_token)
        downloader = CourseDownloader(client)
        
        # Kurs finden
        print(f"  Suche Kurs: {course_name}")
        course = downloader.get_course_by_shortname(course_name)
        if not course:
            print(f"  Kurs '{course_name}' nicht gefunden!")
            return None
        
        print(f"Gefunden: {course['fullname']} (ID: {course['id']})")
        
        # Assignments holen
        print(f"\n  Hole Assignments...")
        assignments = downloader.get_course_assignments(course['id'])
        
        if not assignments:
            print("  Keine Assignments gefunden!")
            return None
        
        # Assignments anzeigen
        print(f"{len(assignments)} Assignment(s) gefunden:\n")
        
        # Erstelle Optionen für interaktive Auswahl
        assignment_options = []
        for i, assign in enumerate(assignments, 1):
            name = assign.get('name', 'Unnamed')
            if 'intro_text' in assign and assign['intro_text']:
                preview = assign['intro_text'][:60].replace('\n', ' ')
                assignment_options.append(f"{i}. {name} - {preview}...")
            else:
                assignment_options.append(f"{i}. {name}")
        assignment_options.append("Abbrechen")
        
        # Interaktive Auswahl mit Pfeiltasten
        choice = questionary.select(
            "Welches Assignment analysieren?",
            choices=assignment_options,
            style=questionary.Style([
                ('question', 'bold cyan'),
                ('pointer', 'fg:#ff9d00 bold'),
                ('highlighted', 'fg:#ff9d00 bold'),
                ('selected', 'fg:#5f819d'),
            ])
        ).ask()
        
        if choice == "Abbrechen" or not choice:
            return None
        
        # Extrahiere Index aus der Auswahl
        idx = int(choice.split('.')[0]) - 1
        selected = assignments[idx]
        
        # Assignment analysieren
        print(f"\n  Analysiere: {selected['name']}")
        if selected.get('intro_text'):
            print(f"  Beschreibung: {selected['intro_text'][:200]}...")
        
        # Matcher initialisieren
        print(f"\n  Nutze {model} für Kompetenz-Matching...")
        matcher = AssignmentCompetencyMatcher(model=model)
        
        # Existierende Kompetenzen aus Neo4j holen
        print("  Suche existierende Kompetenzen in Neo4j...")
        existing_competencies = matcher.get_course_competencies(course_name)
        
        if not existing_competencies:
            print("  Keine Kompetenzen in Neo4j gefunden!")
            print("     Tipp: Führe erst Phase 1-3 aus um Kompetenzen zu extrahieren")
            return None
        
        print(f"{len(existing_competencies)} Kompetenzen verfügbar")
        
        # Einige Beispiele zeigen
        print("\n  Beispiel-Kompetenzen aus dem Kurs:")
        for i, comp in enumerate(existing_competencies[:3], 1):
            print(f"    {i}. {comp['name']}")
        if len(existing_competencies) > 3:
            print(f"    ... und {len(existing_competencies) - 3} weitere")
        
        # Intelligentes Matching
        print(f"\n  Lasse {model} passende Kompetenzen auswählen...")
        result = matcher.process_assignment(
            assignment_name=selected['name'],
            assignment_description=selected.get('intro_text', ''),
            course_id=course_name
        )
        
        if result['success']:
            print(f"\n{result['matched_count']} Kompetenzen zugeordnet:")
            for i, comp_name in enumerate(result['matched_competencies'], 1):
                print(f"    {i}. {comp_name}")
            
            print("\n  Neo4j Graph-Struktur erstellt:")
            print(f"    Assignment: {selected['name']}")
            print(f"    └── REQUIRES → {result['matched_count']} Kompetenzen")
            
            return {
                'assignment': selected['name'],
                'assignment_id': selected.get('id'),
                'competencies': result.get('matched_competencies', []),
                'course_id': course_name,
                'moodle_id': selected.get('moodle_id')
            }
        else:
            print(f"\n  Matching fehlgeschlagen: {result.get('message', 'Unbekannter Fehler')}")
            return None
            
    except Exception as e:
        logger.error(f"Fehler bei Assignment-Analyse: {e}")
        print(f"  Fehler: {e}")
        return None


def list_assignments(course_name: str) -> List[Dict]:
    """
    Hilfsfunktion: Listet alle Assignments eines Kurses.
    
    Nützlich für API/Batch-Processing.
    
    Args:
        course_name: Kurs-Shortname
    
    Returns:
        Liste von Assignment-Dictionaries
    """
    moodle_url = os.getenv('MOODLE_URL')
    moodle_token = os.getenv('MOODLE_TOKEN')
    
    if not moodle_url or not moodle_token:
        return []
    
    try:
        client = MoodleClient(moodle_url, moodle_token)
        downloader = CourseDownloader(client)
        
        course = downloader.get_course_by_shortname(course_name)
        if not course:
            return []
        
        return downloader.get_course_assignments(course['id'])
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Assignments: {e}")
        return []