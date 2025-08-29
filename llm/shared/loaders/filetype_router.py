from .powerpoint_loader import PowerPointLoader
from .text_loader import TextLoader
from .base_loader import BaseLoader
from .pdf_loader import PDFLoader
from pathlib import Path

def get_loader(path: str) -> BaseLoader:
    """
    Gibt den passenden Loader anhand der Dateiendung des Pfads zurück.
    """
    suffix = Path(path).suffix.lower().lstrip(".")

    match suffix:
        case "py" | "java" | "js":
            return TextLoader()
        case "txt" | "md":
            return TextLoader()
        case "pptx":
            return PowerPointLoader()
        case "pdf":
            return PDFLoader()
        case _:
            raise ValueError(f"Kein Loader verfügbar für Dateityp: {suffix}")