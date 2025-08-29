"""
Moodle Competency Framework Uploader
Überträgt Kompetenzen aus Neo4j nach Moodle
"""

from typing import Dict, List, Optional, Any
from .client import MoodleClient
from llm.graph.neo4j_client import GraphDatabase
from logger import get_logger
import json
from datetime import datetime

logger = get_logger(__name__)


class MoodleCompetencyUploader:
    """
    Überträgt Kompetenz-Hierarchie aus Neo4j nach Moodle.
    
    Workflow:
    1. Lese ThemeCluster und Kompetenzen aus Neo4j
    2. Erstelle Competency Framework in Moodle (1 pro Kurs)
    3. Erstelle Parent-Kompetenzen (ThemeCluster)
    4. Erstelle Child-Kompetenzen und verknüpfe mit Parents
    5. Verknüpfe Framework mit Kurs
    6. Mappe Assignment-Kompetenzen
    """
    
    def __init__(self, moodle_client: MoodleClient):
        self.moodle = moodle_client
        self.db = GraphDatabase()
        self.framework_id = None
        self.competency_mapping = {}  # Neo4j name -> Moodle ID
        
    def create_framework_for_course(self, course_shortname: str, course_fullname: str = None) -> int:
        """
        Erstellt ein Competency Framework für einen Kurs.
        
        Args:
            course_shortname: Kurs-Kurzname (z.B. "GDP", "TK1")
            course_fullname: Voller Kursname (optional)
            
        Returns:
            Framework ID in Moodle
        """
        if not course_fullname:
            course_fullname = f"Kompetenzen für {course_shortname}"
            
        # Framework-Daten mit allen erforderlichen Feldern
        framework_data = {
            'shortname': f'framework_{course_shortname.lower()}',
            'idnumber': f'fw_{course_shortname.lower()}_{datetime.now().strftime("%Y%m%d")}',
            'description': f'Automatisch generiertes Kompetenz-Framework für {course_fullname}',
            'descriptionformat': 1,  # HTML
            'visible': 1,
            'scaleid': 2,  # Default competence scale
            'scaleconfiguration': '[{"scaleid":"2"},{"id":1,"scaledefault":0,"proficient":0},{"id":2,"scaledefault":1,"proficient":1}]',  # Beide auf Competent für Course Completion
            'contextid': 1  # System context (ID 1)
        }
        
        try:
            # Moodle erwartet die Daten in einem 'competencyframework' wrapper
            response = self.moodle.call_function(
                'core_competency_create_competency_framework',
                competencyframework=framework_data
            )
            
            self.framework_id = response['id']
            logger.info(f" Competency Framework erstellt: ID={self.framework_id}, Name={response['shortname']}")
            return self.framework_id
            
        except Exception as e:
            logger.error(f" Fehler beim Erstellen des Frameworks: {e}")
            raise
            
    def load_competencies_from_neo4j(self, course_shortname: str) -> Dict[str, Any]:
        """
        Lädt die Kompetenz-Hierarchie aus Neo4j.
        
        Returns:
            Dict mit ThemeClusters und zugehörigen Kompetenzen
        """
        # 1. Hole ThemeCluster
        cluster_query = """
        MATCH (tc:ThemeCluster)
        RETURN tc.cluster_id as id, tc.name as name, tc.description as description
        ORDER BY tc.name
        """
        
        cluster_result = self.db.execute_query(cluster_query, {})
        clusters_data, _ = cluster_result
        
        clusters = {}
        for row in clusters_data:
            cluster_id, name, desc = row
            clusters[name] = {
                'id': cluster_id,
                'name': name,
                'description': desc or f"Themenbereich: {name}",
                'competencies': []
            }
        
        # 2. Hole Kompetenzen pro Cluster
        comp_query = """
        MATCH (tc:ThemeCluster)<-[:BELONGS_TO]-(d:Document)
        MATCH (d)-[:TEACHES]->(c:Competency)
        WHERE d.lecture_name = $course_id
        RETURN 
            tc.name as cluster_name,
            c.name as comp_name,
            c.description as comp_desc,
            c.bloom_level as bloom_level
        ORDER BY tc.name, c.name
        """
        
        comp_result = self.db.execute_query(comp_query, {'course_id': course_shortname.upper()})
        comp_data, _ = comp_result
        
        for row in comp_data:
            cluster_name, comp_name, comp_desc, bloom_level = row
            if cluster_name in clusters:
                clusters[cluster_name]['competencies'].append({
                    'name': comp_name,
                    'description': comp_desc or comp_name,
                    'bloom_level': bloom_level or 'apply'
                })
        
        # Falls keine Cluster vorhanden, hole alle Kompetenzen direkt
        if not clusters:
            logger.warning(" Keine ThemeCluster gefunden, lade Kompetenzen ohne Hierarchie")
            direct_query = """
            MATCH (d:Document)-[:TEACHES]->(c:Competency)
            WHERE d.lecture_name = $course_id
            RETURN DISTINCT
                c.name as name,
                c.description as description,
                c.bloom_level as bloom_level
            ORDER BY c.name
            """
            
            direct_result = self.db.execute_query(direct_query, {'course_id': course_shortname.upper()})
            direct_data, _ = direct_result
            
            # Erstelle einen Default-Cluster
            clusters['Allgemeine Kompetenzen'] = {
                'id': 'default',
                'name': 'Allgemeine Kompetenzen',
                'description': f'Kompetenzen für {course_shortname}',
                'competencies': []
            }
            
            for row in direct_data:
                name, desc, bloom = row
                clusters['Allgemeine Kompetenzen']['competencies'].append({
                    'name': name,
                    'description': desc or name,
                    'bloom_level': bloom or 'apply'
                })
        
        logger.info(f" Geladen: {len(clusters)} Cluster mit insgesamt {sum(len(c['competencies']) for c in clusters.values())} Kompetenzen")
        return clusters
    
    def create_competency(self, name: str, description: str, parent_id: int = 0, 
                          idnumber: str = None) -> int:
        """
        Erstellt eine einzelne Kompetenz in Moodle.
        
        Args:
            name: Kompetenz-Name
            description: Beschreibung
            parent_id: ID der Parent-Kompetenz (0 = Top-Level)
            idnumber: Externe ID für Referenzierung
            
        Returns:
            Moodle Competency ID
        """
        if not self.framework_id:
            raise ValueError("Framework muss zuerst erstellt werden!")
            
        if not idnumber:
            # Generiere ID aus Name
            idnumber = f"comp_{name[:50].lower().replace(' ', '_').replace('/', '_')}"
            
        comp_data = {
            'competencyframeworkid': self.framework_id,
            'shortname': name[:100],  # Moodle Limit
            'idnumber': idnumber,
            'description': description,
            'parentid': parent_id
            # sortorder und descriptionformat weglassen - Moodle nutzt Defaults
        }
        
        try:
            # Moodle erwartet die Daten in einem 'competency' wrapper
            response = self.moodle.call_function(
                'core_competency_create_competency',
                competency=comp_data
            )
            
            comp_id = response['id']
            self.competency_mapping[name] = comp_id
            
            logger.debug(f" Kompetenz erstellt: {name} (ID={comp_id}, Parent={parent_id})")
            return comp_id
            
        except Exception as e:
            logger.error(f" Fehler beim Erstellen der Kompetenz '{name}': {e}")
            raise
    
    def upload_competency_hierarchy(self, clusters: Dict[str, Any]) -> Dict[str, int]:
        """
        Lädt die komplette Kompetenz-Hierarchie nach Moodle hoch.
        
        Args:
            clusters: Dict mit ThemeClusters und Kompetenzen
            
        Returns:
            Mapping von Kompetenz-Namen zu Moodle IDs
        """
        if not self.framework_id:
            raise ValueError("Framework muss zuerst erstellt werden!")
            
        logger.info(f" Lade {len(clusters)} Themenbereiche nach Moodle...")
        
        # 1. Erstelle Parent-Kompetenzen (ThemeCluster)
        parent_ids = {}
        for cluster_name, cluster_data in clusters.items():
            try:
                parent_id = self.create_competency(
                    name=cluster_name,
                    description=cluster_data['description'],
                    parent_id=0,  # Top-Level
                    idnumber=f"cluster_{cluster_data['id']}"
                )
                parent_ids[cluster_name] = parent_id
                logger.info(f"   Themenbereich erstellt: {cluster_name}")
            except Exception as e:
                logger.error(f"   Fehler bei Themenbereich '{cluster_name}': {e}")
                continue
        
        # 2. Erstelle Child-Kompetenzen
        total_comps = 0
        for cluster_name, cluster_data in clusters.items():
            if cluster_name not in parent_ids:
                continue
                
            parent_id = parent_ids[cluster_name]
            
            for comp in cluster_data['competencies']:
                try:
                    self.create_competency(
                        name=comp['name'],
                        description=comp['description'],
                        parent_id=parent_id
                    )
                    total_comps += 1
                except Exception as e:
                    logger.error(f"     Fehler bei Kompetenz '{comp['name']}': {e}")
                    continue
        
        logger.info(f" Upload abgeschlossen: {len(parent_ids)} Themenbereiche, {total_comps} Kompetenzen")
        
        # NEU: Speichere Moodle IDs in Neo4j
        self.update_neo4j_with_moodle_ids()
        
        return self.competency_mapping
    
    def update_neo4j_with_moodle_ids(self):
        """
        Aktualisiert Neo4j Competency Nodes mit den Moodle IDs.
        """
        from llm.graph.neo4j_client import GraphDatabase
        
        db = GraphDatabase()
        updated_count = 0
        
        logger.info(" Aktualisiere Neo4j mit Moodle IDs...")
        
        for comp_name, moodle_id in self.competency_mapping.items():
            query = """
            MATCH (c:Competency {name: $name})
            SET c.moodle_id = $moodle_id
            RETURN c.name
            """
            try:
                result = db.execute_query(query, {
                    "name": comp_name,
                    "moodle_id": moodle_id
                })
                if result[0]:  # Wenn Knoten gefunden und aktualisiert
                    updated_count += 1
                    logger.debug(f"   {comp_name} -> Moodle ID {moodle_id}")
            except Exception as e:
                logger.error(f"   Fehler bei {comp_name}: {e}")
        
        logger.info(f" {updated_count}/{len(self.competency_mapping)} Kompetenzen in Neo4j aktualisiert")
    
    def link_framework_to_course(self, course_id: int) -> bool:
        """
        Verknüpft das Framework mit einem Moodle-Kurs.
        
        Args:
            course_id: Moodle Course ID
            
        Returns:
            True bei Erfolg
        """
        if not self.framework_id:
            raise ValueError("Framework muss zuerst erstellt werden!")
            
        try:
            # Alternative: Verwende search_competencies mit framework filter
            response = self.moodle.call_function(
                'core_competency_search_competencies',
                searchtext='',  # Leerer Search text = alle
                competencyframeworkid=self.framework_id
            )
            
            competency_ids = [comp['id'] for comp in response]
            
            # Füge jede Kompetenz zum Kurs hinzu
            added_count = 0
            for comp_id in competency_ids:
                try:
                    self.moodle.call_function(
                        'core_competency_add_competency_to_course',
                        courseid=course_id,
                        competencyid=comp_id
                    )
                    added_count += 1
                except Exception as e:
                    logger.warning(f" Kompetenz {comp_id} konnte nicht verknüpft werden: {e}")
            
            logger.info(f" {added_count}/{len(competency_ids)} Kompetenzen mit Kurs verknüpft")
            return added_count > 0
            
        except Exception as e:
            logger.error(f" Fehler beim Verknüpfen mit Kurs: {e}")
            return False
    
    def set_competency_completion_rules(self, course_id: int) -> int:
        """
        Setzt Completion Rules für Kompetenzen im Kurs.
        
        Wenn IRGENDEINE Aktivität im Kurs abgeschlossen wird,
        werden die Kompetenzen basierend auf ihrer Rule aktualisiert.
        
        Args:
            course_id: Moodle Course ID
            
        Returns:
            Anzahl gesetzter Rules
        """
        logger.info(" Setze Competency Completion Rules...")
        
        if not self.competency_mapping:
            logger.warning(" Keine Kompetenzen zum Verknüpfen vorhanden")
            return 0
            
        rules_set = 0
        
        # Setze für jede Kompetenz eine Rule
        for comp_name, comp_id in self.competency_mapping.items():
            try:
                # Rule outcome options:
                # 0 = None (nothing happens)
                # 1 = Evidence (log completion as evidence)
                # 2 = Recommend (flag for review)
                # 3 = Complete (mark competency as complete)
                
                # Wir verwenden "Evidence" als Standard
                # Das bedeutet: Wenn eine Aktivität abgeschlossen wird,
                # wird dies als Beweis für diese Kompetenz geloggt
                self.moodle.call_function(
                    'core_competency_set_course_competency_ruleoutcome',
                    coursecompetencyid=comp_id,
                    ruleoutcome=1  # Evidence
                )
                rules_set += 1
                logger.debug(f"   Rule gesetzt für: {comp_name}")
                
            except Exception as e:
                logger.warning(f"   Fehler beim Setzen der Rule für '{comp_name}': {e}")
                
        logger.info(f" {rules_set} Completion Rules gesetzt")
        return rules_set
    
    def map_assignment_competencies(self, course_shortname: str, course_id: int) -> int:
        """
        Mappt Assignment-REQUIRES Beziehungen aus Neo4j zu Moodle.
        
        Args:
            course_shortname: Kurs-Kurzname für Neo4j
            course_id: Moodle Course ID
            
        Returns:
            Anzahl gemappter Beziehungen
        """
        # 1. Hole Moodle Assignments
        logger.info(" Lade Moodle Assignments...")
        try:
            course_contents = self.moodle.call_function(
                'core_course_get_contents',
                courseid=course_id
            )
            
            # Sammle alle Assignments mit ihren IDs
            moodle_assignments = {}
            for section in course_contents:
                if 'modules' in section:
                    for module in section['modules']:
                        if module.get('modname') == 'assign':
                            moodle_assignments[module['name']] = {
                                'module_id': module['id'],
                                'instance_id': module.get('instance', 0)
                            }
            
            logger.info(f"  Gefunden: {len(moodle_assignments)} Assignments in Moodle")
            
        except Exception as e:
            logger.error(f" Fehler beim Laden der Moodle Assignments: {e}")
            return 0
        
        # 2. Hole Assignment-Kompetenz Mappings aus Neo4j
        query = """
        MATCH (a:Assignment)-[:REQUIRES]->(c:Competency)
        WHERE a.course_id = $course_id
        RETURN a.name as assignment_name, collect(c.name) as competencies
        """
        
        result = self.db.execute_query(query, {'course_id': course_shortname.upper()})
        data, _ = result
        
        if not data:
            logger.info("ℹ️ Keine Assignment-Kompetenz Mappings in Neo4j gefunden")
            return 0
        
        logger.info(f" {len(data)} Assignment-Mappings in Neo4j gefunden")
        
        # 3. Mappe Assignments zu Kompetenzen
        mapped_count = 0
        for row in data:
            assignment_name, neo4j_competencies = row
            
            # Finde passendes Moodle Assignment
            if assignment_name not in moodle_assignments:
                logger.warning(f" Assignment '{assignment_name}' nicht in Moodle gefunden")
                continue
                
            module_id = moodle_assignments[assignment_name]['module_id']
            
            # Mappe Kompetenz-Namen zu Moodle IDs
            for comp_name in neo4j_competencies:
                if comp_name in self.competency_mapping:
                    comp_id = self.competency_mapping[comp_name]
                    
                    try:
                        # Verknüpfe Assignment-Modul mit Kompetenz 
                        # Nutze das neue Plugin anstatt der nicht-existierenden core_competency Funktion
                        self.moodle.call_function(
                            'local_competency_linker_add_competency_to_module',
                            cmid=module_id,
                            competencyid=comp_id,
                            ruleoutcome=1  # Evidence
                        )
                        mapped_count += 1
                        logger.debug(f"   Verknüpft: {assignment_name} -> {comp_name}")
                        
                    except Exception as e:
                        logger.warning(f"   Fehler beim Verknüpfen {assignment_name} -> {comp_name}: {e}")
                else:
                    logger.warning(f"   Kompetenz '{comp_name}' nicht in Moodle gefunden")
        
        logger.info(f" {mapped_count} Assignment-Kompetenz Verknüpfungen erstellt")
        return mapped_count
    
    def full_upload_workflow(self, course_shortname: str, course_fullname: str, 
                            moodle_course_id: int) -> Dict[str, Any]:
        """
        Kompletter Upload-Workflow.
        
        Args:
            course_shortname: Kurs-Kurzname (z.B. "TK1")
            course_fullname: Voller Kursname
            moodle_course_id: Moodle Course ID
            
        Returns:
            Dict mit Ergebnis-Informationen
        """
        logger.info(f" Starte Kompetenz-Upload für {course_shortname}")
        
        try:
            # 1. Framework erstellen
            framework_id = self.create_framework_for_course(course_shortname, course_fullname)
            
            # 2. Kompetenzen aus Neo4j laden
            clusters = self.load_competencies_from_neo4j(course_shortname)
            
            if not clusters:
                logger.warning(" Keine Kompetenzen in Neo4j gefunden!")
                return {
                    'success': False,
                    'message': 'Keine Kompetenzen gefunden',
                    'framework_id': framework_id
                }
            
            # 3. Hierarchie hochladen
            mapping = self.upload_competency_hierarchy(clusters)
            
            # 4. Mit Kurs verknüpfen
            linked = self.link_framework_to_course(moodle_course_id)
            
            # 5. Assignment-Mappings (optional)
            assignment_count = self.map_assignment_competencies(course_shortname, moodle_course_id)
            
            return {
                'success': True,
                'framework_id': framework_id,
                'competency_count': len(mapping),
                'cluster_count': len(clusters),
                'linked_to_course': linked,
                'assignment_mappings': assignment_count,
                'competency_mapping': mapping
            }
            
        except Exception as e:
            logger.error(f" Upload fehlgeschlagen: {e}")
            return {
                'success': False,
                'message': str(e),
                'framework_id': self.framework_id
            }