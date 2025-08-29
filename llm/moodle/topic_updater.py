"""
Moodle Topic/Section Updater
Aktualisiert Topic-Summaries mit Lernzielen aus Neo4j
"""

from typing import Dict, List, Optional, Any
from .client import MoodleClient
from llm.graph.neo4j_client import GraphDatabase
from logger import get_logger

logger = get_logger(__name__)


class MoodleTopicUpdater:
    """
    Aktualisiert Moodle Course Topics mit Lernzielen aus Neo4j.
    
    Workflow:
    1. Hole Lernziele aus Neo4j gruppiert nach Dokument
    2. Mappe Dokumente zu Topics (gdp01.pdf -> Topic 1)
    3. Update Topic Summary in Moodle
    """
    
    def __init__(self, moodle_client: MoodleClient):
        self.moodle = moodle_client
        self.db = GraphDatabase()
    
    def get_lernziele_by_document(self, course_id: str) -> Dict[str, List[str]]:
        """
        Holt alle Lernziele aus Neo4j gruppiert nach Dokument.
        
        Args:
            course_id: Kurs-ID
            
        Returns:
            Dict mit document_name -> [lernziele]
        """
        query = """
        MATCH (lo:LearningOutcome)
        WHERE lo.course_id = $course_id
        RETURN lo.document_name as doc, collect(lo.description) as lernziele
        ORDER BY doc
        """
        
        try:
            result = self.db.execute_query(query, {'course_id': course_id})
            data, _ = result
            
            doc_lernziele = {}
            for row in data:
                doc_name = row[0]
                lernziele = row[1]
                doc_lernziele[doc_name] = lernziele
                logger.info(f"  {doc_name}: {len(lernziele)} Lernziele gefunden")
            
            return doc_lernziele
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der Lernziele: {e}")
            return {}
    
    def find_document_section(self, doc_name: str, moodle_course_id: int) -> Optional[int]:
        """
        Findet die Section-Nummer in der das Dokument verlinkt ist.
        
        Durchsucht alle Course Sections nach dem Dokument-Namen.
        
        Args:
            doc_name: Dokument-Name (z.B. "gdp01.pdf")
            moodle_course_id: Moodle Course ID
            
        Returns:
            Section-Nummer oder None
        """
        try:
            # Hole alle Sections des Kurses
            params = {
                'courseid': moodle_course_id
            }
            sections = self.moodle.call_function('core_course_get_contents', **params)
            
            # Durchsuche alle Sections
            for section in sections:
                section_num = section.get('section', 0)
                
                # Prüfe ob Dokument in den Modulen dieser Section ist
                if 'modules' in section:
                    for module in section['modules']:
                        # Prüfe Modul-Name und Contents
                        if doc_name in module.get('name', ''):
                            logger.info(f"  Dokument {doc_name} gefunden in Section {section_num}")
                            return section_num
                        
                        # Prüfe auch in den Contents
                        if 'contents' in module:
                            for content in module['contents']:
                                if doc_name in content.get('filename', ''):
                                    logger.info(f"  Dokument {doc_name} gefunden in Section {section_num}")
                                    return section_num
            
            logger.warning(f"  Dokument {doc_name} nicht in Moodle gefunden")
            return None
            
        except Exception as e:
            logger.error(f"Fehler beim Suchen der Section: {e}")
            return None
    
    def format_lernziele_html(self, lernziele: List[str], doc_name: str = None) -> str:
        """
        Formatiert Lernziele als HTML für Moodle.
        
        Args:
            lernziele: Liste von Lernziel-Beschreibungen
            doc_name: Optional - Dokument-Name für Titel
            
        Returns:
            HTML-formatierter String
        """
        html = '<div class="lernziele">\n'
        html += '<h4>Lernziele dieser Woche:</h4>\n'
        
        if doc_name:
            html += f'<p><em>Basierend auf: {doc_name}</em></p>\n'
        
        html += '<p>Nach dieser Vorlesung können Sie:</p>\n'
        html += '<ul>\n'
        
        for lz in lernziele[:5]:  # Maximal 5 anzeigen
            html += f'  <li>{lz}</li>\n'
        
        html += '</ul>\n'
        html += '</div>'
        
        return html
    
    def get_assignment_titles_from_neo4j(self, course_id: str) -> Dict[str, str]:
        """
        Holt Assignment Display-Titel aus Neo4j.
        
        Args:
            course_id: Kurs-ID
            
        Returns:
            Dict mit assignment_name -> display_title
        """
        query = """
        MATCH (a:Assignment)
        WHERE a.course_id = $course_id
        AND a.display_title IS NOT NULL
        RETURN a.name as name, a.display_title as title
        ORDER BY name
        """
        
        try:
            result = self.db.execute_query(query, {'course_id': course_id.upper()})
            data, _ = result
            
            assignment_titles = {}
            for row in data:
                name = row[0]
                title = row[1]
                assignment_titles[name] = title
                logger.info(f"  Assignment '{name}': Titel '{title}'")
            
            return assignment_titles
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der Assignment-Titel: {e}")
            return {}
    
    def find_assignment_section(self, assignment_name: str, moodle_course_id: int) -> Optional[int]:
        """
        Findet die Section-Nummer in der das Assignment ist.
        
        Args:
            assignment_name: Assignment-Name
            moodle_course_id: Moodle Course ID
            
        Returns:
            Section-Nummer oder None
        """
        try:
            params = {
                'courseid': moodle_course_id
            }
            sections = self.moodle.call_function('core_course_get_contents', **params)
            
            for section in sections:
                section_num = section.get('section', 0)
                
                if 'modules' in section:
                    for module in section['modules']:
                        # Assignments haben modname='assign'
                        if module.get('modname') == 'assign' and assignment_name in module.get('name', ''):
                            logger.info(f"  Assignment '{assignment_name}' gefunden in Section {section_num}")
                            return section_num
            
            logger.warning(f"  Assignment '{assignment_name}' nicht in Moodle gefunden")
            return None
            
        except Exception as e:
            logger.error(f"Fehler beim Suchen der Assignment Section: {e}")
            return None
    
    def get_topic_titles_from_neo4j(self, course_id: str) -> Dict[str, str]:
        """
        Holt Topic-Titel aus Neo4j für alle Dokumente.
        
        Args:
            course_id: Kurs-ID
            
        Returns:
            Dict mit document_name -> topic_title
        """
        query = """
        MATCH (d:Document)
        WHERE d.lecture_name = $course_id
        AND d.topic_title IS NOT NULL
        AND d.topic_title <> "Kein Titel extrahiert"
        RETURN d.title as doc, d.topic_title as title
        ORDER BY doc
        """
        
        try:
            result = self.db.execute_query(query, {'course_id': course_id.upper()})
            data, _ = result
            
            doc_titles = {}
            for row in data:
                doc_name = row[0]
                title = row[1]
                doc_titles[doc_name] = title
                logger.info(f"  {doc_name}: Topic-Titel '{title}'")
            
            return doc_titles
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der Topic-Titel: {e}")
            return {}
    
    def update_course_topics(self, course_id: str, moodle_course_id: int) -> Dict[str, Any]:
        """
        Hauptfunktion: Updated alle Topics eines Kurses mit Lernzielen.
        
        Args:
            course_id: Neo4j Kurs-ID (z.B. "tk1")
            moodle_course_id: Moodle Course ID
            
        Returns:
            Dict mit Ergebnis-Informationen
        """
        logger.info(f"Starte Topic-Update für Kurs {course_id}")
        
        # 1. Hole Lernziele aus Neo4j
        doc_lernziele = self.get_lernziele_by_document(course_id)
        
        if not doc_lernziele:
            logger.warning("Keine Lernziele gefunden")
            return {
                'success': False,
                'message': 'Keine Lernziele in Neo4j gefunden'
            }
        
        # 1b. Hole Topic-Titel aus Neo4j
        doc_titles = self.get_topic_titles_from_neo4j(course_id)
        
        # 1c. Hole Assignment-Titel aus Neo4j
        assignment_titles = self.get_assignment_titles_from_neo4j(course_id)
        logger.info(f"Assignment-Titel geladen: {len(assignment_titles)} gefunden")
        
        # 2. Update Topics für Dokumente
        updated_count = 0
        failed_count = 0
        
        for doc_name, lernziele in doc_lernziele.items():
            section_num = self.find_document_section(doc_name, moodle_course_id)
            
            if section_num is None:
                logger.warning(f"  Kann {doc_name} keinem Topic zuordnen")
                continue
            
            # Formatiere Lernziele als HTML
            summary_html = self.format_lernziele_html(lernziele, doc_name)
            
            # Update Topic in Moodle mit local_wsmanagesections Plugin
            try:
                # Baue Section-Update-Parameter
                section_data = {
                    'section': section_num,
                    'summary': summary_html,
                    'summaryformat': 1  # HTML
                }
                
                # Füge Topic-Titel hinzu wenn vorhanden
                if doc_name in doc_titles:
                    topic_title = doc_titles[doc_name]
                    section_data['name'] = topic_title
                    logger.info(f"  Setze Topic-Name: '{topic_title}' für Section {section_num}")
                
                # Nutze das externe Plugin local_wsmanagesections
                # https://github.com/corvus-albus/moodle-local_wsmanagesections
                params = {
                    'courseid': moodle_course_id,
                    'sections': [section_data]
                }
                
                result = self.moodle.call_function('local_wsmanagesections_update_sections', **params)
                
                # Moodle returns empty array on success
                if isinstance(result, list) or (isinstance(result, dict) and not result.get('exception')):
                    logger.info(f"  Topic {section_num} aktualisiert mit {len(lernziele)} Lernzielen")
                    updated_count += 1
                else:
                    logger.error(f"  Fehler bei Topic {section_num}: {result}")
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"  Fehler bei Topic {section_num}: {e}")
                failed_count += 1
        
        # 2b. Update Topics für Assignments (nur Titel, keine Lernziele)
        for assignment_name, assignment_title in assignment_titles.items():
            section_num = self.find_assignment_section(assignment_name, moodle_course_id)
            
            if section_num is None:
                logger.warning(f"  Kann Assignment '{assignment_name}' keinem Topic zuordnen")
                continue
            
            # Update nur den Topic-Namen für Assignments
            try:
                params = {
                    'courseid': moodle_course_id,
                    'sections': [{
                        'section': section_num,
                        'name': assignment_title
                    }]
                }
                
                result = self.moodle.call_function('local_wsmanagesections_update_sections', **params)
                
                if isinstance(result, list) or (isinstance(result, dict) and not result.get('exception')):
                    logger.info(f"  Topic {section_num} Name aktualisiert für Assignment: '{assignment_title}'")
                    updated_count += 1
                else:
                    logger.error(f"  Fehler bei Assignment Topic {section_num}: {result}")
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"  Fehler bei Assignment Topic {section_num}: {e}")
                failed_count += 1
        
        # 3. Ergebnis
        return {
            'success': updated_count > 0,
            'updated_topics': updated_count,
            'failed_topics': failed_count,
            'total_documents': len(doc_lernziele)
        }