from typing import List, Dict, Any, Optional, Tuple
from langchain_core.documents import Document as LangchainDoc
from .models import Document, Competency, Lecture, Exercise
from .neo4j_client import GraphDatabase
from llm.shared.llm_factory import get_embedding_model
from logger import get_logger
from datetime import datetime
import numpy as np
import json

logger = get_logger(__name__)


class GraphIngestion:
    def __init__(self):
        self.db = GraphDatabase()
        self.db.create_constraints()
        
        # Embedding-Funktionalität initialisieren
        try:
            self.embeddings = get_embedding_model("openai")
            logger.info(" Embeddings für Kompetenz-Deduplikation aktiviert")
        except Exception as e:
            self.embeddings = None
            logger.warning(f" Embeddings nicht verfügbar: {e}")
        
        # Cache für Embeddings um API Calls zu reduzieren
        self._embedding_cache = {}
        
    def ingest_document(self, 
                       langchain_doc: LangchainDoc,
                       doc_type: str = "slide",
                       chroma_id: Optional[str] = None,
                       course_id: Optional[str] = None) -> Document:
        
        metadata = langchain_doc.metadata
        
        # Extrahiere Metadaten aus Dateipfad
        file_path = metadata.get("source", "")
        
        # course_id ist required
        if not course_id:
            raise ValueError("course_id muss angegeben werden!")
        
        lecture_info = {"lecture_name": course_id.upper(), "number": "unknown"}
        
        # Erstelle oder finde Lecture
        lecture = self._get_or_create_lecture(lecture_info)
        
        # Erstelle Document-Knoten mit eindeutiger ID basierend auf Dateiname
        # Extrahiere Dateiname ohne Pfad und Erweiterung
        import os
        filename = os.path.basename(file_path)
        filename_without_ext = os.path.splitext(filename)[0]
        doc_id = f"{lecture_info['lecture_name']}_{filename_without_ext}"
        
        # Besserer Title: Verwende Dateinamen oder custom title
        title = metadata.get("title", filename)  # Mit Erweiterung für Konsistenz
        if title == f"Folie {metadata.get('slide_number', 'unknown')}":
            # Wenn nur generischer "Folie X" Title, verwende Dateinamen
            title = filename  # Mit Erweiterung
        
        doc = Document.get_or_create({
            "doc_id": doc_id,
            "title": title,
            "content": langchain_doc.page_content[:5000],  # Neo4j String limit
            "doc_type": doc_type,
            "lecture_name": lecture_info["lecture_name"],
            "semester": lecture_info.get("semester", "unknown"),
            "slide_number": metadata.get("slide_number"),
            "file_path": file_path,
            "chroma_id": chroma_id,
            "updated_at": datetime.now()
        })[0]
        
        # Verbinde mit Lecture
        if lecture:
            doc.part_of_lecture.connect(lecture)
        
        logger.info(f"Dokument ingested: {doc_id}")
        return doc
    
    def _get_or_create_lecture(self, lecture_info: Dict[str, Any]) -> Optional[Lecture]:
        if lecture_info["lecture_name"] == "unknown":
            return None
            
        lecture = Lecture.get_or_create({
            "lecture_id": lecture_info["lecture_name"],
            "name": self._get_full_lecture_name(lecture_info["lecture_name"]),
            "semester": "WS2024/25"  # Default, könnte aus Config kommen
        })[0]
        
        return lecture
    
    def _get_full_lecture_name(self, abbrev: str) -> str:
        # einfach den Ordnernamen als Kursnamen, später noch mapping evtl
        return abbrev
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Berechne Cosine Similarity zwischen zwei Vektoren."""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def create_or_get_similar_competency(self,
                                        name: str,
                                        description: str,
                                        level: str = "intermediate",
                                        keywords: List[str] = None,
                                        similarity_threshold: float = 0.85) -> Tuple[Competency, bool]:
        """
        Erstelle eine neue Kompetenz oder nutze eine existierende ähnliche.
        Nutzt Embeddings zur Similarity-Berechnung, speichert diese aber nicht.
        
        Returns:
            Tuple[Competency, bool]: (Kompetenz-Objekt, True wenn wiederverwendet)
        """
        
        logger.info(f" create_or_get_similar_competency START: {name}")
        
        # Embeddings müssen verfügbar sein
        if not self.embeddings:
            raise ValueError("Embeddings nicht initialisiert - OpenAI API Key prüfen!")
        
        # Generiere Embedding für neue Kompetenz
        # Nutze nur den Namen für Similarity, da Beschreibungen oft generisch sind
        comp_text = name
        logger.info(f"   Generiere Embedding für neue Kompetenz: {comp_text[:50]}...")
        new_embedding = self.embeddings.embed_query(comp_text)
        logger.info(f"   Embedding generiert (Länge: {len(new_embedding)})")
        
        # Hole nur existierende Kompetenzen des aktuellen Kurses
        logger.info(f"   Lade existierende Kompetenzen aus Neo4j...")
        # Filtere nach course_id in keywords array
        if keywords and len(keywords) > 0:
            course_id = keywords[0]  # course_id ist das erste keyword
            all_comps = Competency.nodes.all()
            existing_comps = [c for c in all_comps if course_id in c.keywords]
            logger.info(f"   {len(existing_comps)} von {len(all_comps)} Kompetenzen für Kurs '{course_id}' gefiltert")
        else:
            existing_comps = Competency.nodes.all()
            logger.info(f"   {len(existing_comps)} existierende Kompetenzen geladen (kein Kurs-Filter)")
        
        best_match = None
        best_similarity = 0.0
        
        # Vergleiche mit allen existierenden Kompetenzen
        logger.debug(f"   Vergleiche mit {len(existing_comps)} existierenden Kompetenzen...")
        api_calls_made = 0
        cache_hits = 0
        
        for i, comp in enumerate(existing_comps):
            if i % 10 == 0 and i > 0:
                logger.debug(f"    ... {i}/{len(existing_comps)} verglichen")
            
            # Prüfe ob wir das Embedding bereits im Cache haben
            existing_text = comp.name
            
            if existing_text in self._embedding_cache:
                # Cache Hit! Kein API Call nötig
                existing_embedding = self._embedding_cache[existing_text]
                cache_hits += 1
                logger.debug(f"     Cache-Hit für '{comp.name}'")
            else:
                # Cache Miss - muss Embedding generieren
                logger.debug(f"     Generiere Embedding für '{comp.name}'...")
                existing_embedding = self.embeddings.embed_query(existing_text)
                self._embedding_cache[existing_text] = existing_embedding
                api_calls_made += 1
            
            # Berechne Similarity
            similarity = self._cosine_similarity(new_embedding, existing_embedding)
            logger.debug(f"     Similarity: {similarity:.3f}")
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = comp
        
        if existing_comps:
            logger.info(f"   Embedding-Stats: {api_calls_made} API Calls, {cache_hits} Cache Hits")
        
        logger.debug(f"   Bester Match: {best_match.name if best_match else 'None'} (Similarity: {best_similarity:.2f})")
        
        # Entscheide ob ähnlich genug
        if best_match and best_similarity >= similarity_threshold:
            logger.info(f" Ähnliche Kompetenz gefunden: '{name}' → '{best_match.name}' (Similarity: {best_similarity:.2f})")
            return best_match, True
        
        # Keine ähnliche gefunden - erstelle neue
        logger.debug(f"   Erstelle neue Kompetenz in Neo4j...")
        comp = Competency.get_or_create({
            "name": name,
            "description": description,
            "level": level,
            "keywords": keywords or []
        })[0]
        
        # WICHTIG: Füge das neue Embedding zum Cache hinzu für zukünftige Vergleiche!
        self._embedding_cache[name] = new_embedding
        
        logger.info(f" Neue Kompetenz erstellt: {name}")
        logger.debug(f" create_or_get_similar_competency ENDE")
        return comp, False
    
    
    def link_document_to_competency(self, 
                                   doc: Document, 
                                   comp: Competency,
                                   confidence: float = 1.0):
        
        # Prüfe ob Beziehung bereits existiert
        existing = doc.teaches.relationship(comp)
        if existing:
            # Update Konfidenz wenn nötig
            existing.confidence = confidence
            existing.save()
            logger.info(f"Aktualisiert: {doc.doc_id} -> lehrt -> {comp.name} (Konfidenz: {confidence})")
        else:
            # Neue Beziehung
            rel = doc.teaches.connect(comp)
            rel.confidence = confidence
            rel.save()
            logger.info(f"Verknüpft: {doc.doc_id} -> lehrt -> {comp.name} (Konfidenz: {confidence})")
    
    def create_document_similarity(self, 
                                  doc1: Document, 
                                  doc2: Document,
                                  similarity_score: float):
        
        if similarity_score > 0.8:  # Schwellwert für "ähnlich genug"
            doc1.similar_to.connect(doc2)
            logger.info(f"Ähnlichkeit: {doc1.doc_id} <-> {doc2.doc_id} ({similarity_score:.2f})")
    
    def create_sequence_relationship(self, 
                                   docs: List[Document]):
        
        # Verbinde aufeinanderfolgende Folien
        for i in range(len(docs) - 1):
            docs[i].follows.connect(docs[i + 1])
            logger.info(f"Sequenz: {docs[i].doc_id} -> {docs[i + 1].doc_id}")