from typing import List, Dict, Any, Optional, Tuple
from .models import Document, Competency, Exercise
from .neo4j_client import GraphDatabase
from logger import get_logger

logger = get_logger(__name__)


class GraphQueries:
    def __init__(self):
        self.db = GraphDatabase()
    
    def find_related_documents(self, 
                             doc_id: str, 
                             max_distance: int = 2) -> List[Dict[str, Any]]:
        
        # Neo4j erlaubt keine Parameter in variable-length patterns
        # Wir müssen die Query dynamisch bauen
        query = f"""
        MATCH (start:Document {{doc_id: $doc_id}})
        MATCH path = (start)-[*1..{max_distance}]-(related:Document)
        WHERE related.doc_id <> start.doc_id
        WITH related, min(length(path)) as distance
        RETURN DISTINCT 
            related.doc_id as doc_id,
            related.title as title,
            related.doc_type as type,
            distance
        ORDER BY distance, related.doc_id
        LIMIT 20
        """
        
        results, _ = self.db.execute_query(query, {
            "doc_id": doc_id
        })
        
        return [
            {
                "doc_id": row[0],
                "title": row[1],
                "type": row[2],
                "distance": row[3]
            }
            for row in results
        ]
    
    def find_competencies_for_document(self, doc_id: str) -> List[Dict[str, Any]]:
        
        query = """
        MATCH (d:Document {doc_id: $doc_id})-[r:TEACHES]->(c:Competency)
        RETURN 
            c.name as name,
            c.description as description,
            c.level as level,
            r.confidence as confidence
        ORDER BY r.confidence DESC
        """
        
        results, _ = self.db.execute_query(query, {"doc_id": doc_id})
        
        return [
            {
                "name": row[0],
                "description": row[1],
                "level": row[2],
                "confidence": row[3]
            }
            for row in results
        ]
    
    def find_learning_path(self, 
                          start_competency: str, 
                          target_competency: str) -> Optional[List[str]]:
        
        query = """
        MATCH path = shortestPath(
            (start:Competency {name: $start})-[:PREREQUISITE_OF*]-(target:Competency {name: $target})
        )
        RETURN [node IN nodes(path) | node.name] as path
        """
        
        results, _ = self.db.execute_query(query, {
            "start": start_competency,
            "target": target_competency
        })
        
        return results[0][0] if results else None
    
    def get_competency_coverage(self, doc_ids: List[str]) -> Dict[str, float]:
        
        query = """
        MATCH (d:Document)-[r:TEACHES]->(c:Competency)
        WHERE d.doc_id IN $doc_ids
        WITH c.name as competency, avg(r.confidence) as avg_confidence
        RETURN competency, avg_confidence
        ORDER BY avg_confidence DESC
        """
        
        results, _ = self.db.execute_query(query, {"doc_ids": doc_ids})
        
        return {row[0]: row[1] for row in results}
    
    def find_documents_for_competency(self, 
                                    competency_name: str,
                                    min_confidence: float = 0.5) -> List[Dict[str, Any]]:
        
        query = """
        MATCH (c:Competency {name: $comp_name})<-[r:TEACHES]-(d:Document)
        WHERE r.confidence >= $min_conf
        RETURN 
            d.doc_id as doc_id,
            d.title as title,
            d.lecture_name as lecture,
            r.confidence as confidence
        ORDER BY r.confidence DESC
        """
        
        results, _ = self.db.execute_query(query, {
            "comp_name": competency_name,
            "min_conf": min_confidence
        })
        
        return [
            {
                "doc_id": row[0],
                "title": row[1],
                "lecture": row[2],
                "confidence": row[3]
            }
            for row in results
        ]
    
    def get_document_context(self, doc_id: str) -> Dict[str, Any]:
        
        # Hole Dokument mit allen relevanten Beziehungen
        query = """
        MATCH (d:Document {doc_id: $doc_id})
        OPTIONAL MATCH (d)-[:FOLLOWS]->(next:Document)
        OPTIONAL MATCH (prev:Document)-[:FOLLOWS]->(d)
        OPTIONAL MATCH (d)-[:TEACHES]->(c:Competency)
        OPTIONAL MATCH (d)-[:PART_OF]->(l:Lecture)
        RETURN 
            d.title as title,
            d.content as content,
            prev.doc_id as prev_doc,
            next.doc_id as next_doc,
            l.name as lecture,
            collect(DISTINCT c.name) as competencies
        """
        
        results, _ = self.db.execute_query(query, {"doc_id": doc_id})
        
        if not results:
            return {}
        
        row = results[0]
        return {
            "title": row[0],
            "content": row[1],
            "previous": row[2],
            "next": row[3],
            "lecture": row[4],
            "competencies": row[5]
        }
    
    def find_similar_exercises(self, 
                             competencies: List[str],
                             limit: int = 5) -> List[Dict[str, Any]]:
        
        query = """
        MATCH (c:Competency)<-[:TRAINS]-(e:Exercise)
        WHERE c.name IN $competencies
        WITH e, count(DISTINCT c) as matching_comps
        RETURN 
            e.exercise_id as id,
            e.title as title,
            e.difficulty as difficulty,
            matching_comps
        ORDER BY matching_comps DESC, e.difficulty
        LIMIT $limit
        """
        
        results, _ = self.db.execute_query(query, {
            "competencies": competencies,
            "limit": limit
        })
        
        return [
            {
                "id": row[0],
                "title": row[1],
                "difficulty": row[2],
                "matching_competencies": row[3]
            }
            for row in results
        ]
