"""
Phase G: Submission Grading

Bewertet Student Submissions gegen die Kompetenzen eines Assignments.
Nutzt die bewährte Logik aus test_submission_evaluation_proper.py.
"""
import os
from logger import get_logger
from pathlib import Path
from typing import Dict, List, Optional
from llm.moodle import MoodleClient, CourseDownloader
from llm.graph.neo4j_client import GraphDatabase
from llm.feedback.factory import get_llm as get_feedback_llm
import questionary
from llm.feedback.prompts.builder import FeedbackPromptBuilder
from llm.feedback.types import (
    SubmissionBewertung,
    KompetenzBewertung,
    BewertungsZusammenfassung
)

logger = get_logger(__name__)


def run_submission_grading(course_name: str, model: str = "gpt-4o") -> Optional[Dict]:
    """
    Phase G: Bewertet Student Submissions.
    
    1. Holt Assignments aus Moodle
    2. Zeigt Submissions für gewähltes Assignment
    3. Bewertet gegen Assignment-Kompetenzen aus Neo4j
    4. Fügt Feedback in Moodle hinzu
    5. Updated Kompetenzstatus in Moodle
    
    Args:
        course_name: Shortname des Kurses
        model: LLM-Modell für Bewertung
    
    Returns:
        Dict mit Bewertungsergebnis oder None
    """

    # Moodle-Verbindung
    moodle_url = os.getenv('MOODLE_URL')
    moodle_token = os.getenv('MOODLE_TOKEN')
    
    if not moodle_url or not moodle_token:
        logger.error("Moodle-Credentials fehlen in .env!")
        print("  MOODLE_URL und MOODLE_TOKEN müssen in .env gesetzt sein")
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
        
        course_id = course['id']
        print(f"Gefunden: {course['fullname']} (ID: {course_id})")
        
        # Submissions downloaden
        print(f"\n  Lade Submissions...")
        submissions_dict = downloader.download_assignment_submissions(
            course_id=course_id,
            target_dir="test_submissions",
            only_submitted=True
        )
        
        if not submissions_dict:
            print("  Keine Submissions gefunden!")
            print("     Stelle sicher, dass Studenten Lösungen eingereicht haben")
            return None
        
        # Assignment wählen
        print(f"\n  Assignments mit Submissions:")
        assignments = list(submissions_dict.keys())
        
        # Erstelle Optionen für interaktive Auswahl
        assignment_options = []
        for i, assignment in enumerate(assignments, 1):
            files = submissions_dict[assignment]
            assignment_options.append(f"{i}. {assignment} ({len(files)} Submission(s))")
        assignment_options.append("Abbrechen")
        
        # Interaktive Auswahl mit Pfeiltasten
        choice = questionary.select(
            "Welches Assignment bewerten?",
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
        assignment_name = assignments[idx]
        
        # Submissions für Assignment
        submission_files = submissions_dict[assignment_name]
        print(f"\n  {len(submission_files)} Submission(s) für '{assignment_name}':")
        
        # Erstelle Optionen für interaktive Auswahl
        submission_options = []
        for i, filepath in enumerate(submission_files, 1):
            # Extrahiere User aus Pfad
            user = extract_user_from_path(filepath)
            filename = os.path.basename(filepath)
            submission_options.append(f"{i}. {user}: {filename}")
        submission_options.append("Alle bewerten")
        submission_options.append("Abbrechen")
        
        # Interaktive Auswahl mit Pfeiltasten
        choice = questionary.select(
            "Welche Submission bewerten?",
            choices=submission_options,
            style=questionary.Style([
                ('question', 'bold cyan'),
                ('pointer', 'fg:#ff9d00 bold'),
                ('highlighted', 'fg:#ff9d00 bold'),
                ('selected', 'fg:#5f819d'),
            ])
        ).ask()
        
        if choice == "Abbrechen" or not choice:
            return None
        elif choice == "Alle bewerten":
            # Alle bewerten
            return evaluate_all_submissions(
                submission_files, 
                assignment_name, 
                course_name,
                course_id,
                model
            )
        else:
            # Extrahiere Index aus der Auswahl
            idx = int(choice.split('.')[0]) - 1
            filepath = submission_files[idx]
        
        # Einzelne Submission bewerten
        return evaluate_single_submission(
            filepath,
            assignment_name,
            course_name,
            course_id,
            model
        )
        
    except Exception as e:
        logger.error(f"Fehler bei Submission Grading: {e}")
        print(f"  Fehler: {e}")
        return None


def evaluate_single_submission(filepath: str, assignment_name: str, 
                              course_name: str, course_id: int, 
                              model: str) -> Dict:
    """
    Bewertet eine einzelne Submission.
    """
    print(f"\n  Bewerte Submission...")
    print(f"  Datei: {os.path.basename(filepath)}")
    print(f"  User: {extract_user_from_path(filepath)}")
    
    # Hole Kompetenzen aus Neo4j
    db = GraphDatabase()
    competencies = get_assignment_competencies(db, assignment_name)
    
    if not competencies:
        print(f"  Keine Kompetenzen für '{assignment_name}' gefunden!")
        print("     Führe erst Phase 3 (Assignment-Analyse) aus")
        return None
    
    print(f"{len(competencies)} Kompetenzen zu bewerten")
    
    # Lade Submission
    with open(filepath, 'r', encoding='utf-8') as f:
        submission_code = f.read()
    
    # Erkenne Task-Type
    extension = os.path.splitext(filepath)[1].lower()
    task_type = FeedbackPromptBuilder.get_extension_mapping().get(extension, ".java")
    
    # Bewerte jede Kompetenz
    print(f"\n  Bewerte mit {model}...")
    bewertungen = []
    erreicht_count = 0
    
    for i, comp in enumerate(competencies, 1):
        print(f"    [{i}/{len(competencies)}] {comp['name']}...", end="")
        
        # Bewerte mit Feedback-System
        bewertung = evaluate_competency(
            submission_code=submission_code,
            competency=comp,
            task_type=task_type,
            model=model
        )
        
        if bewertung:
            bewertungen.append(bewertung)
            if bewertung.erreicht:
                erreicht_count += 1
                print(" ✓")
            else:
                print(" ✗")
        else:
            print(" ⚠️ Fehler")
    
    # Zusammenfassung
    print(f"\n  {'='*40}")
    print(f"  BEWERTUNGSERGEBNIS")
    print(f"  {'='*40}")
    print(f"  Kompetenzen erreicht: {erreicht_count}/{len(competencies)}")
    print(f"  Erfolgsquote: {erreicht_count/len(competencies)*100:.1f}%")
    
    # Details anzeigen
    print(f"\n  Details:")
    for b in bewertungen:
        symbol = "✓" if b.erreicht else "✗"
        print(f"  {symbol} {b.kompetenz_name}")
        print(f"     Erfüllungsgrad: {b.erfuellungsgrad}")
        if b.tipp:
            print(f"     Tipp: {b.tipp[:100]}...")
    
    # Feedback in Moodle speichern
    moodle_user_id = extract_moodle_user_id(filepath)
    if moodle_user_id:
        print(f"\n  Speichere Feedback in Moodle...")
        success = save_feedback_to_moodle(
            user_id=moodle_user_id,
            assignment_name=assignment_name,
            course_id=course_id,
            bewertungen=bewertungen,
            erreicht_count=erreicht_count
        )
        
        if success:
            print("Feedback in Moodle gespeichert")
        else:
            print("  ⚠️ Feedback konnte nicht gespeichert werden")
        
        # Markiere Kompetenzen als erreicht/nicht erreicht in Moodle
        print(f"\n  Markiere Kompetenzen in Moodle...")
        marked_count = mark_competencies_in_moodle(
            user_id=moodle_user_id,
            course_id=course_id,
            bewertungen=bewertungen
        )
        print(f"{marked_count} Kompetenzen in Moodle markiert")
    
    return {
        'assignment': assignment_name,
        'filepath': filepath,
        'user': extract_user_from_path(filepath),
        'kompetenzen_total': len(competencies),
        'kompetenzen_erreicht': erreicht_count,
        'erfolgsquote': erreicht_count/len(competencies) if competencies else 0,
        'bewertungen': bewertungen
    }


def evaluate_all_submissions(submission_files: List[str], assignment_name: str,
                            course_name: str, course_id: int, 
                            model: str) -> Dict:
    """
    Bewertet alle Submissions eines Assignments.
    """
    print(f"\n  Bewerte {len(submission_files)} Submissions...")
    
    # Hole Kompetenzen einmal
    db = GraphDatabase()
    competencies = get_assignment_competencies(db, assignment_name)
    
    if not competencies:
        print(f"  Keine Kompetenzen gefunden!")
        return None
    
    print(f"{len(competencies)} Kompetenzen pro Submission")
    
    # Bewerte alle
    alle_ergebnisse = []
    
    for i, filepath in enumerate(submission_files, 1):
        user = extract_user_from_path(filepath)
        print(f"\n  [{i}/{len(submission_files)}] Bewerte {user}...")
        
        # Einzelbewertung
        ergebnis = evaluate_single_submission(
            filepath, assignment_name, course_name, course_id, model
        )
        
        if ergebnis:
            alle_ergebnisse.append(ergebnis)
            erfolg = ergebnis['erfolgsquote']
            print(f"     → {ergebnis['kompetenzen_erreicht']}/{ergebnis['kompetenzen_total']} ({erfolg*100:.0f}%)")
    
    # Gesamtübersicht
    if alle_ergebnisse:
        print(f"\n  {'='*40}")
        print(f"  GESAMTÜBERSICHT")
        print(f"  {'='*40}")
        
        for ergebnis in alle_ergebnisse:
            erfolg = ergebnis['erfolgsquote']
            symbol = "🟢" if erfolg >= 0.8 else "🟡" if erfolg >= 0.5 else "🔴"
            print(f"  {symbol} {ergebnis['user']}: {ergebnis['kompetenzen_erreicht']}/{ergebnis['kompetenzen_total']} ({erfolg*100:.0f}%)")
    
    return {
        'assignment': assignment_name,
        'total_submissions': len(submission_files),
        'bewertet': len(alle_ergebnisse),
        'ergebnisse': alle_ergebnisse
    }


def get_assignment_competencies(db: GraphDatabase, assignment_name: str) -> List[Dict]:
    """
    Hole Kompetenzen für ein Assignment aus Neo4j.
    """
    query = """
    MATCH (a:Assignment)-[:REQUIRES]->(c:Competency)
    WHERE a.name CONTAINS $assignment_name
    RETURN 
        c.name as name,
        c.description as description,
        c.bloom_level as bloom_level
    ORDER BY c.name
    """
    
    result = db.execute_query(query, {"assignment_name": assignment_name})
    data, columns = result
    
    competencies = []
    for row in data:
        competencies.append({
            "name": row[0],
            "description": row[1] or "",
            "bloom_level": row[2] or "Anwenden"
        })
    
    return competencies


def evaluate_competency(submission_code: str, competency: Dict, 
                       task_type: str, model: str) -> Optional[KompetenzBewertung]:
    """
    Bewertet eine einzelne Kompetenz.
    """
    try:
        # Bestimme LLM-Provider basierend auf Model-Name
        llm_name = "claude" if "claude" in model.lower() else "openai"
        
        # LLM mit Feedback-Factory
        llm = get_feedback_llm(llm_name=llm_name, task_type=task_type, model=model)
        
        # Formatiere Kompetenz
        kompetenz_text = f"""
        {competency['name']}:
        - {competency['description']}
        - Bloom-Level: {competency['bloom_level']}
        """
        
        # Bewerte
        result = llm.evaluate(
            abgabe=submission_code,
            kompetenz=kompetenz_text
        )
        
        # Strukturiere Ergebnis
        ist_erreicht = result.kompetenz_erfüllt in [
            "funktional erfüllt",
            "sicher angewendet",
            "besonders gut umgesetzt"
        ]
        
        return KompetenzBewertung(
            kompetenz_name=competency['name'],
            kompetenz_beschreibung=competency['description'],
            bloom_level=competency['bloom_level'],
            erreicht=ist_erreicht,
            erfuellungsgrad=result.kompetenz_erfüllt,
            feedback=result.komplettes_feedback,
            tipp=result.tipp,
            beispielhafte_beobachtung=result.beispielhafte_beobachtung
        )
        
    except Exception as e:
        logger.error(f"Fehler bei Bewertung von '{competency['name']}': {e}")
        return None


def save_feedback_to_moodle(user_id: int, assignment_name: str, course_id: int,
                           bewertungen: List[KompetenzBewertung], 
                           erreicht_count: int) -> bool:
    """
    Speichert Feedback als Kommentar in Moodle.
    """
    try:
        client = MoodleClient(
            url=os.getenv("MOODLE_URL"),
            token=os.getenv("MOODLE_TOKEN")
        )
        
        # Hole Assignment ID
        downloader = CourseDownloader(client)
        assignments = downloader.get_course_assignments(course_id)
        
        assignment_id = None
        for assign in assignments:
            if assign.get('name') == assignment_name:
                assignment_id = assign.get('id')
                break
        
        if not assignment_id:
            logger.warning(f"Assignment '{assignment_name}' nicht gefunden")
            return False
        
        # Erstelle HTML-Feedback
        feedback_html = create_feedback_html(bewertungen, erreicht_count)
        
        # Berechne Note (Prozent der erreichten Kompetenzen)
        grade = round((erreicht_count / len(bewertungen)) * 100) if bewertungen else 0
        
        # Speichere in Moodle
        params = {
            'assignmentid': assignment_id,
            'applytoall': 0,
            'grades[0][userid]': user_id,
            'grades[0][grade]': grade,
            'grades[0][attemptnumber]': -1,
            'grades[0][addattempt]': 0,
            'grades[0][workflowstate]': 'graded',
            'grades[0][plugindata][assignfeedbackcomments_editor][text]': feedback_html,
            'grades[0][plugindata][assignfeedbackcomments_editor][format]': 1
        }
        
        result = client.call_function('mod_assign_save_grades', **params)
        
        logger.info(f"Feedback für User {user_id} gespeichert (Note: {grade}%)")
        return True
        
    except Exception as e:
        logger.error(f"Fehler beim Speichern des Feedbacks: {e}")
        return False


def create_feedback_html(bewertungen: List[KompetenzBewertung], erreicht_count: int) -> str:
    """
    Erstellt formatiertes HTML-Feedback.
    """
    html = "<h3>KI-basierte Kompetenzbewertung</h3>\n"
    html += f"<p><strong>Erreichte Kompetenzen: {erreicht_count}/{len(bewertungen)}</strong></p>\n"
    html += "<hr>\n"
    
    for komp in bewertungen:
        status = "✓" if komp.erreicht else "✗"
        html += f"<h4>{status} {komp.kompetenz_name}</h4>\n"
        html += f"<p><strong>Erfüllungsgrad:</strong> {komp.erfuellungsgrad}</p>\n"
        html += f"<p><strong>Feedback:</strong> {komp.feedback}</p>\n"
        
        if komp.beispielhafte_beobachtung:
            html += f"<p><strong>Beobachtung:</strong> {komp.beispielhafte_beobachtung}</p>\n"
        
        if komp.tipp:
            html += f"<p><strong>Tipp:</strong> {komp.tipp}</p>\n"
        
        html += "<hr>\n"
    
    return html


def get_task_type(filepath: str) -> str:
    """
    Ermittelt den Task-Type basierend auf Dateiendung.
    """
    if filepath.endswith('.py'):
        return "python"
    elif filepath.endswith('.java'):
        return "java"
    elif filepath.endswith('.js'):
        return "javascript"
    else:
        return "text"


def extract_user_from_path(filepath: str) -> str:
    """
    Extrahiert Username aus Dateipfad.
    """
    # test_submissions/submissions/user_4/assignment_Name/file.py
    parts = filepath.split('/')
    for part in parts:
        if part.startswith('user_'):
            return part
    return "unknown"


def extract_moodle_user_id(filepath: str) -> Optional[int]:
    """
    Extrahiert Moodle User ID aus Dateipfad.
    """
    parts = filepath.split('/')
    for part in parts:
        if part.startswith('user_'):
            try:
                return int(part.replace('user_', ''))
            except ValueError:
                return None
    return None


def mark_competencies_in_moodle(user_id: int, course_id: int, 
                               bewertungen: List[KompetenzBewertung]) -> int:
    """
    Markiert Kompetenzen in Moodle als erreicht/nicht erreicht.
    Nutzt die Moodle Competency API.
    """
    marked_count = 0
    
    # Neo4j für Moodle IDs
    db = GraphDatabase()
    
    # Competency Token verwenden (hat mehr Rechte)
    client = MoodleClient(
        url=os.getenv("MOODLE_URL"),
        token=os.getenv("MOODLE_COMPETENCY_TOKEN") or os.getenv("MOODLE_TOKEN")
    )
    
    for bewertung in bewertungen:
        try:
            # Hole Moodle ID aus Neo4j
            query = """
            MATCH (c:Competency {name: $name})
            RETURN c.moodle_id as moodle_id
            """
            result = db.execute_query(query, {"name": bewertung.kompetenz_name})
            data, _ = result
            
            if not data or not data[0][0]:
                logger.warning(f"Keine Moodle ID für '{bewertung.kompetenz_name}' gefunden")
                continue
            
            moodle_comp_id = int(data[0][0])
            
            # Markiere in Moodle
            params = {
                'courseid': course_id,
                'userid': user_id,
                'competencyid': moodle_comp_id,
                'grade': 2 if bewertung.erreicht else 1,  # 2=Kompetent, 1=Noch nicht kompetent
                'note': f"KI-Bewertung: {bewertung.erfuellungsgrad}"
            }
            
            result = client.call_function('core_competency_grade_competency_in_course', **params)
            
            if result:
                marked_count += 1
                status = "erreicht" if bewertung.erreicht else "nicht erreicht"
                logger.info(f"Kompetenz '{bewertung.kompetenz_name}' als {status} markiert")
            
        except Exception as e:
            logger.error(f"Fehler beim Markieren von '{bewertung.kompetenz_name}': {e}")
    
    return marked_count