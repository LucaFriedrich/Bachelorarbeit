# llm/evaluate/document_manager.py

from typing import List, Dict, Optional, Tuple
from langchain_core.documents import Document
from llm.chroma.chroma_ingest import get_vectorstore, ingest_documents
from llm.shared.loaders.filetype_router import get_loader
from llm.graph import GraphIngestion, GraphQueries, Document as GraphDocument
from logger import get_logger
import os
import chromadb

logger = get_logger(__name__)


class DocumentManager:
    """
    Verwaltet Dokumente für die Kompetenzextraktion.
    
    Bietet zwei Modi:
    1. Full Document Mode: Lädt komplette Dokumente für Analyse
    2. RAG Mode: Nutzt ChromaDB für Kontext-Suche
    """
    
    def __init__(self, use_graph: bool = True):
        self.vectorstore = get_vectorstore()
        # ChromaDB Client für direkte Queries
        host = os.getenv("CHROMA_HOST")
        port = int(os.getenv("CHROMA_PORT", "8000"))
        self.chroma_client = chromadb.HttpClient(host=host, port=port, ssl=False)
        self.collection = self.chroma_client.get_or_create_collection("moodle_documents")
        
        # Graph Integration (optional)
        self.use_graph = use_graph
        if use_graph:
            try:
                self.graph_ingestion = GraphIngestion()
                self.graph_queries = GraphQueries()
                logger.info(" Graph-Integration aktiviert")
            except Exception as e:
                logger.warning(f" Graph-Integration fehlgeschlagen: {e}")
                self.use_graph = False
        
    def ingest_course_document(self, file_path: str, course_id: str, 
                             chunk_size: int = 1000, chunk_overlap: int = 200) -> Dict[str, any]:
        """
        Lädt ein Kursdokument und speichert es intelligent in ChromaDB.
        
        Args:
            file_path: Pfad zur Datei
            course_id: Eindeutige Kurs-ID
            chunk_size: Größe der Chunks (größer = mehr Kontext pro Chunk)
            chunk_overlap: Überlappung zwischen Chunks
            
        Returns:
            Dict mit Infos über das geladene Dokument
        """
        import sys
        from contextlib import redirect_stdout
        
        # using explicit print statements so that this can be used in CLI scripts
        print(f"Chunke und lade {file_path} in die Vektor-Datenbank")
        
        # 1. Dokument laden
        loader = get_loader(file_path)
        filename = os.path.basename(file_path)
        
        # Unterdrücke stdout während des PDF-Ladens (für unstructured warnings)
        with open(os.devnull, 'w') as devnull:
            with redirect_stdout(devnull):
                # 2. Als komplettes Dokument laden (für später)
                full_content = loader.load_as_string(file_path)
                
                # 3. In Chunks aufteilen für ChromaDB
                if hasattr(loader, 'load_page_documents'):
                    # Nutze Seiten wenn möglich (PDFs, PowerPoint)
                    docs = loader.load_page_documents(file_path)
                    doc_type = "paged"
                else:
                    # Sonst als ein Dokument
                    doc = loader.load_as_document(file_path)
                    docs = [doc]
                    doc_type = "single"
        
        # 4. Metadaten für ALLE Chunks hinzufügen
        for i, doc in enumerate(docs):
            doc.metadata.update({
                "course_id": course_id,
                "source_file": filename,
                "file_path": file_path,
                "doc_type": doc_type,
                "chunk_index": i,
                "total_chunks": len(docs)
            })
        
        # 5. In ChromaDB speichern
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        if chunk_size > 0 and doc_type == "single":
            # Nur bei single docs chunken, pages sind schon gechunkt
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
            docs = splitter.split_documents(docs)
            
        ingest_documents(docs, chunk=False)  # Schon gechunkt!
        
        # 6. OPTIONAL: In Graph speichern
        graph_doc = None
        if self.use_graph and doc_type == "paged":
            # Für Folien: Erstelle einen Graph-Knoten pro Seite
            try:
                for i, doc in enumerate(docs):
                    # Verwende das erste Dokument als Haupt-Knoten
                    if i == 0:
                        graph_doc = self.graph_ingestion.ingest_document(
                            langchain_doc=doc,
                            doc_type="slide",
                            chroma_id=f"{course_id}_{filename}_{i}",
                            course_id=course_id
                        )
                logger.info(f" Graph-Knoten erstellt für: {filename}")
            except Exception as e:
                logger.warning(f"Graph-Ingest fehlgeschlagen: {e}")
        
        return {
            "file_path": file_path,
            "filename": filename,
            "course_id": course_id,
            "chunks_created": len(docs),
            "total_length": len(full_content),
            "doc_type": doc_type,
            "graph_node_id": graph_doc.doc_id if graph_doc else None
        }
    
    def get_full_document(self, source_file: str, course_id: Optional[str] = None) -> str:
        """
        Holt ein KOMPLETTES Dokument (alle Chunks zusammen).
        
        Args:
            source_file: Dateiname (z.B. "vorlesung1.pdf")
            course_id: Optional für zusätzliche Filterung
            
        Returns:
            Der komplette Dokumenteninhalt
        """
        logger.debug(f" Hole komplettes Dokument: {source_file}")
        
        # Query für ChromaDB - mit AND-Operator für mehrere Bedingungen
        if course_id:
            where_filter = {
                "$and": [
                    {"source_file": {"$eq": source_file}},
                    {"course_id": {"$eq": course_id}}
                ]
            }
        else:
            where_filter = {"source_file": {"$eq": source_file}}
        
        # Alle Chunks dieses Dokuments holen
        results = self.collection.get(
            where=where_filter,
            include=["documents", "metadatas"]
        )
        
        if not results["ids"]:
            logger.warning(f" Kein Dokument gefunden: {source_file}")
            return ""
        
        # Chunks sortieren und zusammenfügen
        chunks_with_meta = list(zip(results["documents"], results["metadatas"]))
        
        # Nach chunk_index sortieren (falls vorhanden)
        chunks_with_meta.sort(key=lambda x: x[1].get("chunk_index", 0))
        
        # Zusammenfügen
        full_text = "\n\n".join([chunk[0] for chunk in chunks_with_meta])
        
        logger.info(f" Dokument rekonstruiert: {len(chunks_with_meta)} Chunks, {len(full_text)} Zeichen")
        return full_text
    
    def get_course_documents(self, course_id: str) -> List[Dict[str, str]]:
        """
        Listet alle Dokumente eines Kurses auf.
        
        Args:
            course_id: Die Kurs-ID
            
        Returns:
            Liste von Dokumenten-Infos
        """
        results = self.collection.get(
            where={"course_id": {"$eq": course_id}},
            include=["metadatas"]
        )
        
        # Unique Dokumente finden
        unique_docs = {}
        for meta in results["metadatas"]:
            filename = meta.get("source_file", "unknown")
            if filename not in unique_docs:
                unique_docs[filename] = {
                    "filename": filename,
                    "course_id": course_id,
                    "doc_type": meta.get("doc_type", "unknown"),
                    "chunks": 0
                }
            unique_docs[filename]["chunks"] += 1
        
        return list(unique_docs.values())
    
    def get_related_content(self, query: str, course_id: Optional[str] = None, 
                          k: int = 5) -> List[Document]:
        """
        RAG-Modus: Findet verwandte Inhalte.
        
        Args:
            query: Suchanfrage
            course_id: Optional auf einen Kurs beschränken
            k: Anzahl Ergebnisse
            
        Returns:
            Liste relevanter Dokument-Chunks
        """
        logger.debug(f" RAG-Suche: '{query[:50]}...' (k={k})")
        
        if course_id:
            # Mit Kurs-Filter
            results = self.vectorstore.similarity_search(
                query,
                k=k,
                filter={"course_id": {"$eq": course_id}}
            )
        else:
            # Über alle Kurse
            results = self.vectorstore.similarity_search(query, k=k)
        
        return results
    
    def analyze_full_then_rag(self, source_file: str, course_id: str) -> Tuple[str, List[Document]]:
        """
        Hybrid-Ansatz: Hole komplettes Dokument UND relevante Kontexte.
        
        Args:
            source_file: Zu analysierendes Dokument
            course_id: Kurs-ID
            
        Returns:
            Tuple von (kompletter_text, verwandte_chunks)
        """
        # 1. Komplettes Dokument
        full_doc = self.get_full_document(source_file, course_id)
        
        # 2. Verwandte Inhalte aus ANDEREN Dokumenten
        # (Filtere das aktuelle Dokument aus)
        all_related = self.get_related_content(full_doc[:500], course_id, k=10)
        other_docs = [doc for doc in all_related 
                     if doc.metadata.get("source_file") != source_file][:5]
        
        return full_doc, other_docs