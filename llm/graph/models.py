from neomodel import (
    StructuredNode, StructuredRel, StringProperty, IntegerProperty, 
    RelationshipTo, RelationshipFrom, DateTimeProperty,
    JSONProperty, ArrayProperty, FloatProperty
)
from datetime import datetime
from typing import Optional, List, Dict, Any


class TeachesRel(StructuredRel):
    confidence = FloatProperty(default=1.0)
    extracted_at = DateTimeProperty(default_factory=datetime.now)


# Legacy Relationship
class RequiresRel(StructuredRel):
    strength = StringProperty(choices={"weak": "weak", "medium": "medium", "strong": "strong"}, default="medium")

# Neue LLM-basierte Relationships
class PrerequisiteRel(StructuredRel):
    __label__ = "PREREQUISITE"
    strength = FloatProperty(default=0.5)
    reason = StringProperty()

class BuildsUponRel(StructuredRel):
    __label__ = "BUILDS_UPON"
    strength = FloatProperty(default=0.5)
    reason = StringProperty()

class RelatedRel(StructuredRel):
    __label__ = "RELATED"
    strength = FloatProperty(default=0.5)
    reason = StringProperty()
    relation_type = StringProperty()  # independent, similar, etc.
    

class Document(StructuredNode):
    __label__ = "Document"  # Explizite Neo4j Label Definition
    
    doc_id = StringProperty(unique_index=True, required=True)
    title = StringProperty(required=True)
    content = StringProperty()
    doc_type = StringProperty(choices={"slide": "slide", "exercise": "exercise", "solution": "solution", "exam": "exam"}, required=True)
    
    # Metadaten
    lecture_name = StringProperty()
    semester = StringProperty()
    slide_number = IntegerProperty()
    file_path = StringProperty()
    
    # ChromaDB Integration
    chroma_id = StringProperty()
    embedding_model = StringProperty(default="text-embedding-3-large")
    
    # Zeitstempel
    created_at = DateTimeProperty(default_factory=datetime.now)
    updated_at = DateTimeProperty(default_factory=datetime.now)
    
    # Theme-Zuordnung
    theme = StringProperty()  # Themen-Cluster aus LLM
    topic_title = StringProperty()  # NEU: Prägnanter Titel für Moodle Topics
    
    # LLM-klassifizierte Beziehungen (neu)
    prerequisite = RelationshipTo('Document', 'PREREQUISITE', model=PrerequisiteRel)
    builds_upon = RelationshipTo('Document', 'BUILDS_UPON', model=BuildsUponRel)
    related_to = RelationshipTo('Document', 'RELATED', model=RelatedRel)
    
    # Legacy Beziehungen  
    teaches = RelationshipTo("Competency", "TEACHES", model=TeachesRel)
    requires = RelationshipTo("Competency", "REQUIRES", model=RequiresRel)
    references = RelationshipTo("Document", "REFERENCES")
    similar_to = RelationshipTo("Document", "SIMILAR_TO")
    follows = RelationshipTo("Document", "FOLLOWS")
    part_of_lecture = RelationshipTo("Lecture", "PART_OF")
    

class Competency(StructuredNode):
    name = StringProperty(unique_index=True, required=True)
    description = StringProperty()
    level = StringProperty(choices={"beginner": "beginner", "intermediate": "intermediate", "advanced": "advanced"})
    bloom_level = StringProperty(choices={
        "remember": "remember", "understand": "understand", "apply": "apply", 
        "analyze": "analyze", "evaluate": "evaluate", "create": "create"
    })
    keywords = ArrayProperty(StringProperty())
    
    # Beziehungen
    taught_by = RelationshipFrom("Document", "TEACHES", model=TeachesRel)
    required_by = RelationshipFrom("Document", "REQUIRES", model=RequiresRel)
    prerequisite_of = RelationshipTo("Competency", "PREREQUISITE_OF")
    related_to = RelationshipTo("Competency", "RELATED_TO")
    part_of_goal = RelationshipTo("LearningGoal", "PART_OF")


class Exercise(StructuredNode):
    exercise_id = StringProperty(unique_index=True, required=True)
    title = StringProperty(required=True)
    description = StringProperty()
    difficulty = IntegerProperty(min=1, max=5)
    estimated_time = IntegerProperty()  # in Minuten
    
    # Aufgabentyp
    exercise_type = StringProperty(choices={
        "programming": "programming", "theoretical": "theoretical", "design": "design", 
        "analysis": "analysis", "debugging": "debugging", "refactoring": "refactoring"
    })
    
    # Beziehungen
    trains = RelationshipTo("Competency", "TRAINS")
    applies_concepts_from = RelationshipTo("Document", "APPLIES")
    has_solution = RelationshipTo("Document", "HAS_SOLUTION")
    

class LearningGoal(StructuredNode):
    goal_id = StringProperty(unique_index=True, required=True)
    description = StringProperty(required=True)
    module = StringProperty()
    measurable_criteria = ArrayProperty(StringProperty())
    
    # Beziehungen
    comprises = RelationshipFrom("Competency", "PART_OF")
    evaluated_in = RelationshipTo("Document", "EVALUATED_IN")


class LearningOutcome(StructuredNode):
    """Lernziele aus Dokumenten extrahiert."""
    outcome_id = StringProperty(unique_index=True, required=True)
    description = StringProperty(required=True)
    document_name = StringProperty()  # Quelldokument
    course_id = StringProperty()  # Kurs-Zuordnung
    
    # Beziehungen
    defined_by = RelationshipFrom("Document", "HAS_OUTCOME")
    

class Lecture(StructuredNode):
    lecture_id = StringProperty(unique_index=True, required=True)
    name = StringProperty(required=True)
    semester = StringProperty()
    professor = StringProperty()
    
    # Beziehungen
    contains = RelationshipFrom("Document", "PART_OF")
    teaches_goals = RelationshipTo("LearningGoal", "TEACHES_GOAL")