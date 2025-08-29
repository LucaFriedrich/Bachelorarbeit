# /llm/shared/loaders/text_loader.py

from pathlib import Path
from langchain_core.documents import Document
from .base_loader import BaseLoader

class TextLoader(BaseLoader):
    """
    Lädt einfache Textdateien oder Quellcode-Dateien.
    """

    def load_as_string(self, path: str) -> str:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {path}")
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return file_path.read_text(encoding="latin-1")

    def load_as_document(self, path: str) -> Document:
        content = self.load_as_string(path)
        return Document(
            page_content=content,
            metadata={
                "source": str(path),
                "type": "text"
            }
        )