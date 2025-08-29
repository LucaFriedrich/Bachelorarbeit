from pathlib import Path
from collections import defaultdict
from langchain_core.documents import Document
import warnings

# Unterdrücke die Warning BEVOR UnstructuredPDFLoader importiert wird
warnings.filterwarnings("ignore", message=".*No languages specified.*")

from langchain_community.document_loaders import UnstructuredPDFLoader
from llm.shared.loaders.base_loader import BaseLoader

class PDFLoader(BaseLoader):
    def __init__(self):
        self.mode = "elements"  # Für granulare Erkennung einzelner Textobjekte

    def load_as_string(self, path: str) -> str:
        """
        Gibt das gesamte PDF als zusammenhängenden Text-String zurück.
        """
        docs = self._load_docs(path)
        return "\n\n".join(doc.page_content for doc in docs)

    def load_as_document(self, path: str) -> Document:
        """
        Gibt das gesamte PDF als ein LangChain-Dokument zurück.
        Ideal für einfache Summarisierung o.ä.
        """
        docs = self._load_docs(path)
        full_text = "\n\n".join(doc.page_content.strip() for doc in docs)
        page_count = len(set(doc.metadata.get("page_number", 0) for doc in docs))

        return Document(
            page_content=full_text,
            metadata={
                "source": str(path),
                "type": "pdf",
                "pages": page_count
            }
        )

    def load_page_documents(self, path: str) -> list[Document]:
        """
        Gibt eine Liste von Dokumenten pro Seite zurück.
        Setzt `unit`-Feld als "page_1", "page_2", ...
        """
        docs = self._load_docs(path)
        pages = defaultdict(list)

        for doc in docs:
            page = doc.metadata.get("page_number", 0)
            pages[page].append(doc.page_content.strip())

        return [
            Document(
                page_content="\n\n".join(contents),
                metadata={
                    "source": str(path),
                    "type": "pdf",
                    "unit": f"page_{page}",
                    "elements": len(contents)
                }
            )
            for page, contents in sorted(pages.items())
        ]

    def _load_docs(self, path: str) -> list[Document]:
        if not Path(path).exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {path}")

        loader = UnstructuredPDFLoader(path, mode=self.mode)
        docs = loader.load()

        for doc in docs:
            doc.metadata.setdefault("source", str(path))
            doc.metadata.setdefault("type", "pdf")

        return docs