import os
from neomodel import config, db
from typing import Optional
from logger import get_logger

logger = get_logger(__name__)


class GraphDatabase:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.setup_connection()
            self._initialized = True
    
    def setup_connection(self):
        neo4j_url = os.getenv("NEO4J_URL", "bolt://neo4j:password123@localhost:7687")
        config.DATABASE_URL = neo4j_url
        logger.info(f"Neo4j verbunden mit: {neo4j_url.split('@')[1]}")
        
    def clear_database(self):
        logger.warning("Lösche alle Knoten und Beziehungen...")
        db.cypher_query("MATCH (n) DETACH DELETE n")
        
    def create_constraints(self):
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Competency) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Exercise) REQUIRE e.exercise_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (l:LearningGoal) REQUIRE l.goal_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (lec:Lecture) REQUIRE lec.lecture_id IS UNIQUE"
        ]
        
        for constraint in constraints:
            try:
                db.cypher_query(constraint)
                logger.info(f"Constraint erstellt: {constraint}")
            except Exception as e:
                logger.debug(f"Constraint bereits vorhanden oder Fehler: {e}")
    
    def get_stats(self) -> dict:
        # Separate queries für bessere Kompatibilität
        doc_count_query = "MATCH (d:Document) RETURN count(d) as count"
        comp_count_query = "MATCH (c:Competency) RETURN count(c) as count"
        ex_count_query = "MATCH (e:Exercise) RETURN count(e) as count"
        rel_count_query = "MATCH ()-[r]->() RETURN count(r) as count"
        
        doc_results, _ = db.cypher_query(doc_count_query)
        comp_results, _ = db.cypher_query(comp_count_query)
        ex_results, _ = db.cypher_query(ex_count_query)
        rel_results, _ = db.cypher_query(rel_count_query)
        
        return {
            "documents": doc_results[0][0] if doc_results else 0,
            "competencies": comp_results[0][0] if comp_results else 0,
            "exercises": ex_results[0][0] if ex_results else 0,
            "relationships": rel_results[0][0] if rel_results else 0
        }
    
    @staticmethod
    def execute_query(query: str, params: Optional[dict] = None):
        return db.cypher_query(query, params or {})