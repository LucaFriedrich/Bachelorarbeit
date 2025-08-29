"""
Phase U: Moodle Upload

Uploaded Kompetenzen aus Neo4j nach Moodle.
Erstellt Competency Framework und verknüpft mit Kurs.
"""
import os
from logger import get_logger
from typing import Dict, Optional
from llm.moodle import MoodleClient
from llm.moodle.competency_uploader import MoodleCompetencyUploader
from llm.moodle.topic_updater import MoodleTopicUpdater
from llm.graph.neo4j_client import GraphDatabase

logger = get_logger(__name__)


def run_moodle_upload(course_name: str) -> Optional[Dict]:
    """
    Phase U: Upload der Kompetenzen nach Moodle.
    
    Erstellt ein Competency Framework in Moodle aus den Neo4j-Daten
    und verknüpft es mit dem Kurs.
    
    Args:
        course_name: Shortname des Kurses
    
    Returns:
        Dict mit Upload-Ergebnis oder None bei Fehler
    """
    
    # Prüfe Neo4j-Daten
    if not check_neo4j_data(course_name):
        print("  Keine Kompetenzen in Neo4j gefunden!")
        print("     Führe erst Phase 1-3 aus um Kompetenzen zu extrahieren")
        return None
    
    # Moodle-Verbindung
    moodle_url = os.getenv('MOODLE_URL')
    moodle_token = os.getenv('MOODLE_COMPETENCY_TOKEN') or os.getenv('MOODLE_TOKEN')
    
    if not moodle_url or not moodle_token:
        logger.error("Moodle-Credentials fehlen in .env!")
        print("  MOODLE_URL und MOODLE_TOKEN müssen in .env gesetzt sein")
        return None
    
    try:
        # Moodle Client
        client = MoodleClient(moodle_url, moodle_token)
        
        # Teste Verbindung
        print("  Teste Moodle-Verbindung...")
        info = client.call_function('core_webservice_get_site_info')
        print(f"Verbunden mit: {info['sitename']}")
        
        # Finde Kurs in Moodle
        print(f"\n  Suche Kurs '{course_name}' in Moodle...")
        course_id = get_course_by_shortname(client, course_name)
        
        if not course_id:
            print(f"  Kurs '{course_name}' nicht in Moodle gefunden!")
            print("     Stelle sicher, dass der Kurs in Moodle existiert")
            return None
        
        # Upload durchführen
        print(f"\n  Starte Upload...")
        print("  " + "-"*40)
        
        uploader = MoodleCompetencyUploader(client)
        
        # Framework-Name
        course_fullname = f"Kompetenzen für {course_name.upper()}"
        
        result = uploader.full_upload_workflow(
            course_shortname=course_name,
            course_fullname=course_fullname,
            moodle_course_id=course_id
        )
        
        # Zeige Ergebnis
        print("\n  " + "-"*40)
        if result['success']:
            print("     UPLOAD ERFOLGREICH!")
            print(f"    Framework ID: {result['framework_id']}")
            print(f"    Themenbereiche: {result['cluster_count']}")
            print(f"    Kompetenzen: {result['competency_count']}")
            
            if result.get('linked_to_course'):
                print(f"    Mit Kurs verknüpft: Ja")
            
            if result.get('assignment_mappings', 0) > 0:
                print(f"    Assignment-Mappings: {result['assignment_mappings']}")
            
            # Topic-Updates mit Lernzielen
            print(f"\n  Aktualisiere Topic-Summaries mit Lernzielen...")
            try:
                topic_updater = MoodleTopicUpdater(client)
                topic_result = topic_updater.update_course_topics(course_name, course_id)
                
                if topic_result['success']:
                    print(f"    Topics aktualisiert: {topic_result['updated_topics']}")
                    if topic_result['failed_topics'] > 0:
                        print(f"    Fehlgeschlagen: {topic_result['failed_topics']}")
                else:
                    print(f"    Topic-Update fehlgeschlagen")
            except Exception as e:
                logger.error(f"Fehler bei Topic-Update: {e}")
                print(f"    Topic-Update fehlgeschlagen: {e}")
            
            print(f"\n  Moodle-Links:")
            print(f"    Framework: {moodle_url}/admin/tool/lp/competencyframeworks.php")
            print(f"    Kurs-Kompetenzen: {moodle_url}/admin/tool/lp/coursecompetencies.php?courseid={course_id}")
            
            return result
        else:
            print("  UPLOAD FEHLGESCHLAGEN!")
            print(f"    Fehler: {result.get('message', 'Unbekannt')}")
            return None
            
    except Exception as e:
        logger.error(f"Fehler bei Moodle-Upload: {e}")
        print(f"  Fehler: {e}")
        return None


def check_neo4j_data(course_name: str) -> bool:
    """
    Prüft ob Kompetenzen in Neo4j vorhanden sind.
    
    Args:
        course_name: Kurs-Shortname
    
    Returns:
        True wenn Daten vorhanden
    """
    try:
        db = GraphDatabase()
        
        # Prüfe Kompetenzen
        query = """
        MATCH (d:Document)-[:TEACHES]->(c:Competency)
        WHERE d.lecture_name = $course_id
        RETURN count(DISTINCT c) as comp_count
        """
        result = db.execute_query(query, {'course_id': course_name.upper()})
        data, _ = result
        comp_count = data[0][0] if data else 0
        
        if comp_count > 0:
            print(f"{comp_count} Kompetenzen in Neo4j gefunden")
            
            # Prüfe auch Cluster
            cluster_query = """
            MATCH (tc:ThemeCluster)
            WHERE $course_id IN tc.keywords
            RETURN count(tc) as cluster_count
            """
            cluster_result = db.execute_query(cluster_query, {'course_id': course_name.upper()})
            cluster_data, _ = cluster_result
            cluster_count = cluster_data[0][0] if cluster_data else 0
            
            if cluster_count > 0:
                print(f"{cluster_count} Themenbereiche gefunden")
            
            # Prüfe Assignment-Mappings
            assign_query = """
            MATCH (a:Assignment)-[:REQUIRES]->(c:Competency)
            WHERE a.course_id = $course_id
            RETURN count(DISTINCT a) as assign_count
            """
            assign_result = db.execute_query(assign_query, {'course_id': course_name})
            assign_data, _ = assign_result
            assign_count = assign_data[0][0] if assign_data else 0
            
            if assign_count > 0:
                print(f"{assign_count} Assignments mit Kompetenz-Mappings")
            
            return True
        else:
            return False
            
    except Exception as e:
        logger.error(f"Fehler bei Neo4j-Prüfung: {e}")
        return False


def get_course_by_shortname(client: MoodleClient, shortname: str) -> Optional[int]:
    """
    Holt die Moodle Course ID für einen Kurznamen.
    
    Args:
        client: Moodle Client
        shortname: Kurs-Shortname
    
    Returns:
        Course ID oder None
    """
    try:
        response = client.call_function(
            'core_course_get_courses_by_field',
            field='shortname',
            value=shortname
        )
        
        if response.get('courses'):
            course = response['courses'][0]
            print(f"Kurs gefunden: {course['fullname']} (ID: {course['id']})")
            return course['id']
        else:
            return None
            
    except Exception as e:
        logger.error(f"Fehler beim Suchen des Kurses: {e}")
        return None