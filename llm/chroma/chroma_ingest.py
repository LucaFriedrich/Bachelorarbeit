
import os
from uuid import uuid4
from typing import List
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

from logger import get_logger

logger = get_logger(__name__)

# Konstante Konfiguration
CHROMA_COLLECTION = "moodle_documents"
EMBEDDING_MODEL = "text-embedding-3-large"


def get_vectorstore() -> Chroma:
    """
    Erstellt eine Chroma-Instanz mit Anbindung an den extern laufenden Server.
    Erwartet Umgebungsvariablen:
      - CHROMA_HOST (z. B. "localhost")
      - CHROMA_PORT (z. B. "8000")
    """
    host = os.getenv("CHROMA_HOST")
    port = int(os.getenv("CHROMA_PORT", "8000"))

    if not host:
        raise EnvironmentError("CHROMA_HOST muss in der .env gesetzt sein.")

    logger.debug(f" Verbinde mit Chroma-Server unter {host}:{port}")

    client = chromadb.HttpClient(host=host, port=port, ssl=False)

    return Chroma(
        client=client,
        collection_name=CHROMA_COLLECTION,
        embedding_function=OpenAIEmbeddings(model=EMBEDDING_MODEL),
    )


def ingest_documents(documents: List[Document], chunk: bool = True) -> None:
    """
    Fügt Dokumente (optional gechunkt) mit eindeutigen IDs in die Chroma-Serverdatenbank ein.
    """
    if not documents:
        logger.warning(" Keine Dokumente zum Ingest übergeben.")
        return

    if chunk:
        logger.debug(" Starte Chunking der Dokumente (chunk_size=500, overlap=50)...")
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        documents = splitter.split_documents(documents)
        logger.debug(f" Nach dem Splitten: {len(documents)} Chunks.")

    vectorstore = get_vectorstore()
    ids = [str(uuid4()) for _ in documents]

    for i, (doc, doc_id) in enumerate(zip(documents, ids), start=1):
        logger.debug(f" Dokument {i}/{len(documents)}: ID={doc_id}, "
                     f"Metadaten={doc.metadata}")

    try:
        vectorstore.add_documents(documents=documents, ids=ids)
        logger.info(f" {len(documents)} Dokumente erfolgreich in Chroma ingestiert.")
    except Exception as e:
        logger.exception(f" Fehler beim Hinzufügen von Dokumenten zu Chroma: {e}")