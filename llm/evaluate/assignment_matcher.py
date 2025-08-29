# llm/evaluate/assignment_matcher.py

from typing import List, Dict, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from llm.shared.llm_factory import get_llm
from llm.graph.neo4j_client import GraphDatabase
import json
from logger import get_logger

logger = get_logger(__name__)


class AssignmentCompetencyMatcher:
    """
    Klasse für die Zuordnung von Assignments zu existierenden Kompetenzen.
    
    Workflow:
    1. Hole alle Kompetenzen aus Neo4j für einen Kurs
    2. Zeige dem LLM die Assignment-Beschreibung + verfügbare Kompetenzen
    3. LLM wählt passende Kompetenzen aus
    4. Erstelle REQUIRES Beziehungen in Neo4j
    """

    def __init__(self, model: str = "gpt-4o"):
        # o1/o3/gpt-5 Modelle unterstützen keine temperature
        if model.startswith("o1") or model in ["o3", "gpt-5"]:
            self.llm = get_llm(model=model)
        else:
            self.llm = get_llm(model=model, temperature=0.1)
        self.db = GraphDatabase()
        logger.info(f" AssignmentCompetencyMatcher initialisiert mit {model}")

    def get_course_competencies(self, course_id: str) -> List[Dict[str, str]]:
        """
        Holt alle Kompetenzen aus Neo4j für einen Kurs.
        
        Returns:
            Liste von Dicts mit competency_id, name, description, bloom_level
        """
        query = """
        MATCH (d:Document)-[:TEACHES]->(c:Competency)
        WHERE d.lecture_name = $course_id
        RETURN DISTINCT 
            c.name as id,
            c.name as name,
            c.description as description,
            c.bloom_level as bloom_level
        ORDER BY c.name
        """

        try:
            result = self.db.execute_query(query, {"course_id": course_id.upper()})
            data, columns = result

            logger.info(f" Neo4j Query erfolgreich: {len(data)} Zeilen zurückgegeben")

            competencies = []
            for row in data:
                comp = {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2] or "",
                    "bloom_level": row[3] or "Anwenden"
                }
                competencies.append(comp)
                logger.debug(f"   Kompetenz geladen: id='{comp['id']}', name='{comp['name']}'")

            logger.info(f" {len(competencies)} Kompetenzen aus Neo4j geladen für Kurs {course_id}")
            return competencies

        except Exception as e:
            logger.error(f" FEHLER bei Neo4j Query:")
            logger.error(f"   course_id: '{course_id}'")
            logger.error(f"   course_id.upper(): '{course_id.upper()}'")
            logger.error(f"   Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def match_assignment(self, assignment_name: str, assignment_description: str,
                         course_competencies: List[Dict[str, str]]) -> tuple[List[str], str]:
        """
        Lässt das LLM passende Kompetenzen für ein Assignment auswählen.
        
        Args:
            assignment_name: Name des Assignments
            assignment_description: Beschreibung/Aufgabenstellung
            course_competencies: Verfügbare Kompetenzen aus dem Kurs
            
        Returns:
            Tuple: (Liste von competency_ids, assignment_title)
        """
        system_prompt = """Du bist ein Experte für Lernzielzuordnung in der Hochschullehre.

Deine Aufgabe: Analysiere eine Aufgabenstellung und wähle aus einer Liste von Kurs-Kompetenzen 
diejenigen aus, die durch diese Aufgabe geprüft/trainiert werden.

WICHTIG:
- Wähle NUR Kompetenzen aus der bereitgestellten Liste
- Nutze die EXAKTEN Namen/IDs aus der Liste, wie sie dort stehen (NICHT ändern, NICHT umformatieren)
- Kopiere die ID-Felder EXAKT wie sie in der Liste stehen
- Wähle nur Kompetenzen die DIREKT und ZENTRAL durch die Aufgabe adressiert werden
- MAXIMUM 5-7 Kompetenzen pro Assignment (nur die wichtigsten!) Versuche nicht 5 zu erreichen, wenn es nicht passt.
- Sei SEHR SELEKTIV: Nur wenn die Kompetenz wirklich Kernbestandteil der Aufgabe ist

Antworte im JSON-Format:
{
    "selected_competencies": ["<exakte ID aus der Liste>", "<exakte ID aus der Liste>", ...],
    "assignment_title": "Prägnanter, aussagekräftiger Titel für diese Aufgabe (max. 50 Zeichen)",
    "reasoning": "Kurze Begründung der Auswahl"
}"""

        # Formatiere Kompetenzen für Prompt
        comp_list = "\n".join([
            f"- ID: {c['id']}\n  Name: {c['name']}\n  Beschreibung: {c['description']}\n  Bloom: {c['bloom_level']}"
            for c in course_competencies
        ])

        user_prompt = f"""ASSIGNMENT: {assignment_name}

AUFGABENSTELLUNG:
{assignment_description}

VERFÜGBARE KOMPETENZEN IM KURS:
{comp_list}

Welche dieser Kompetenzen werden durch dieses Assignment geprüft/trainiert?"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        # DEBUG: Zeige den kompletten Prompt
        logger.debug(" DEBUG - ASSIGNMENT MATCHING PROMPT:")
        logger.debug("=" * 60)
        logger.debug("SYSTEM PROMPT:")
        logger.debug(system_prompt)
        logger.debug("\nUSER PROMPT:")
        logger.debug(user_prompt)
        logger.debug("=" * 60)

        try:
            response = self.llm.invoke(messages)

            # DEBUG: Zeige die komplette Response
            logger.info(" LLM RESPONSE:")
            logger.info("=" * 60)
            logger.info(response.content)
            logger.info("=" * 60)

            # Parse JSON response
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            result = json.loads(content.strip())
            selected_ids_raw = result.get("selected_competencies", [])
            assignment_title = result.get("assignment_title", assignment_name)  # Fallback auf original name
            reasoning = result.get("reasoning", "")

            # Entferne "ID: " Prefix falls vom LLM hinzugefügt (passiert bei manchen Modellen)
            selected_ids = []
            for id_str in selected_ids_raw:
                # Manche LLMs (z.B. gpt-4o-mini, haiku) fügen "ID: " prefix hinzu
                if id_str.startswith("ID: "):
                    clean_id = id_str[4:]  # Entferne die ersten 4 Zeichen "ID: "
                else:
                    clean_id = id_str
                selected_ids.append(clean_id)

            logger.info(f" {len(selected_ids)} Kompetenzen für Assignment '{assignment_name}' ausgewählt")
            logger.info(f"   Neuer Titel: '{assignment_title}'")
            logger.info(f"   Begründung: {reasoning}")

            # DEBUG: Zeige welche IDs ausgewählt wurden und prüfe ob sie existieren
            if selected_ids:
                logger.info(" DEBUG MATCHING:")
                available_ids = [c['id'] for c in course_competencies]

                logger.info(f" Verfügbare IDs aus Neo4j (erste 5 von {len(available_ids)}):")
                for i, aid in enumerate(available_ids[:5]):
                    logger.info(f"   [{i}] '{aid}'")

                logger.info(f" LLM hat {len(selected_ids)} IDs zurückgegeben:")
                for i, sid in enumerate(selected_ids):
                    logger.info(f"   [{i}] '{sid}'")

                logger.debug(" Matching-Check:")
                for sid in selected_ids:
                    exists = sid in available_ids
                    logger.debug(f"   '{sid}' in available_ids? {exists}")

            return selected_ids, assignment_title

        except Exception as e:
            logger.error(f" Fehler bei Kompetenz-Matching: {e}")
            return [], assignment_name

    def create_requires_relationships(self, assignment_name: str, competency_ids: List[str],
                                      course_id: str = None, assignment_title: str = None) -> int:
        """
        Erstellt REQUIRES Beziehungen zwischen Assignment und Kompetenzen in Neo4j.
        
        Args:
            assignment_name: Name des Assignments
            competency_ids: Liste von competency_ids
            course_id: Kurs-ID für Assignment Node
            
        Returns:
            Anzahl erstellter Beziehungen
        """
        # Erstelle Assignment Node
        assignment_id = f"assign_{assignment_name[:30].lower().replace(' ', '_')}"

        create_assign_query = """
        MERGE (a:Assignment {assignment_id: $assignment_id})
        ON CREATE SET 
            a.name = $name,
            a.display_title = $title,
            a.course_id = $course_id,
            a.created_at = datetime()
        ON MATCH SET
            a.display_title = $title,
            a.updated_at = datetime()
        RETURN a.assignment_id as id
        """

        self.db.execute_query(create_assign_query, {
            "assignment_id": assignment_id,
            "name": assignment_name,
            "title": assignment_title if assignment_title else assignment_name,
            "course_id": course_id.upper() if course_id else "UNKNOWN"
        })

        # Erstelle REQUIRES Beziehungen
        created_count = 0
        for comp_id in competency_ids:
            create_requires_query = """
            MATCH (a:Assignment {assignment_id: $assignment_id})
            MATCH (c:Competency {name: $comp_id})
            MERGE (a)-[r:REQUIRES]->(c)
            ON CREATE SET 
                r.strength = 'high',
                r.created_at = datetime()
            RETURN a.name as assignment, c.name as competency
            """

            result = self.db.execute_query(create_requires_query, {
                "assignment_id": assignment_id,
                "comp_id": comp_id
            })

            data, columns = result
            if data:
                created_count += 1
                comp_name = data[0][1] if data[0] else comp_id
                logger.debug(f" Assignment '{assignment_name}' REQUIRES '{comp_name}'")

        logger.info(f" {created_count} REQUIRES Beziehungen erstellt")
        return created_count

    def process_assignment(self, assignment_name: str, assignment_description: str,
                           course_id: str) -> Dict[str, any]:
        """
        Kompletter Workflow: Hole Kompetenzen -> Matche -> Erstelle Beziehungen.
        
        Args:
            assignment_name: Name des Assignments
            assignment_description: Aufgabenstellung
            course_id: Kurs-ID
            
        Returns:
            Dict mit Ergebnis-Informationen
        """
        # 1. Hole Kurs-Kompetenzen
        competencies = self.get_course_competencies(course_id)

        if not competencies:
            logger.warning(f" Keine Kompetenzen für Kurs {course_id} gefunden!")
            return {
                "success": False,
                "message": "Keine Kompetenzen im Kurs gefunden",
                "matched_count": 0
            }

        # 2. Matche Assignment zu Kompetenzen
        matched_ids, assignment_title = self.match_assignment(assignment_name, assignment_description, competencies)

        if not matched_ids:
            logger.warning(f" Keine passenden Kompetenzen gefunden für '{assignment_name}'")
            return {
                "success": False,
                "message": "Keine passenden Kompetenzen gefunden",
                "matched_count": 0
            }

        # 3. Erstelle Beziehungen in Neo4j
        created = self.create_requires_relationships(assignment_name, matched_ids, course_id, assignment_title)

        # 4. Hole Namen der gematchten Kompetenzen für Rückgabe
        matched_names = [c["name"] for c in competencies if c["id"] in matched_ids]

        return {
            "success": True,
            "matched_count": created,
            "matched_competencies": matched_names,
            "competency_ids": matched_ids,
            "assignment_title": assignment_title,
            "total_available": len(competencies)
        }
