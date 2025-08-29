from pathlib import Path
from collections import defaultdict
from langchain_core.documents import Document
from langchain_community.document_loaders import UnstructuredPowerPointLoader
from llm.shared.loaders.base_loader import BaseLoader

class PowerPointLoader(BaseLoader):
    def __init__(self):
        self.mode = "elements"  # Granularer Extraktionsmodus

    def load_as_string(self, path: str) -> str:
        """
        Lädt alle Inhalte der Präsentation als zusammengefassten String.
        """
        docs = self._load_docs(path)
        return "\n\n".join(doc.page_content for doc in docs)

    def load_as_document(self, path: str) -> Document:
        """
        Gibt das gesamte PPTX als ein LangChain-Dokument zurück.
        """
        docs = self._load_docs(path)
        full_text = "\n\n".join(doc.page_content.strip() for doc in docs)
        slide_count = len(set(doc.metadata.get("page_number", 0) for doc in docs))

        return Document(
            page_content=full_text,
            metadata={
                "source": str(path),
                "type": "presentation",
                "slides": slide_count
            }
        )

    def load_page_documents(self, path: str) -> list[Document]:
        """
        Gibt eine Liste von Dokumenten pro Folie zurück.
        Setzt `unit`-Feld als "slide_1", "slide_2", ...
        """
        docs = self._load_docs(path)
        slides = defaultdict(list)

        for doc in docs:
            slide = doc.metadata.get("page_number", 0)
            slides[slide].append(doc.page_content.strip())

        return [
            Document(
                page_content="\n\n".join(contents),
                metadata={
                    "source": str(path),
                    "type": "presentation",
                    "unit": f"slide_{slide}",
                    "elements": len(contents)
                }
            )
            for slide, contents in sorted(slides.items())
        ]

    def _load_docs(self, path: str) -> list[Document]:
        if not Path(path).exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {path}")

        loader = UnstructuredPowerPointLoader(path, mode=self.mode)
        docs = loader.load()

        for doc in docs:
            doc.metadata.setdefault("source", str(path))
            doc.metadata.setdefault("type", "presentation")

        return docs