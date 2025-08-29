# /llm/shared/loaders/base_loader.py
from abc import ABC, abstractmethod
from langchain_core.documents import Document

class BaseLoader(ABC):
    @abstractmethod
    def load_as_string(self, path: str) -> str:
        pass

    @abstractmethod
    def load_as_document(self, path: str) -> Document:
        pass

    def load_page_documents (self, path: str) -> list[Document]:
        pass
