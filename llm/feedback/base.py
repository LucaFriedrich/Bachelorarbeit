# llm/feedback/base.py

from abc import ABC, abstractmethod
from llm.feedback.types import FeedbackResult
from logger import get_logger


class CompetencyLLM(ABC):
    """
    Interface für LLMs, die studentische Abgaben in Bezug auf Zielkompetenzen bewerten.
    """

    def __init__(self):
        self.logger = get_logger(self.__class__.__module__)
        self.logger.debug("CompetencyLLM initialisiert für: %s", self.__class__.__name__)

    @abstractmethod
    def evaluate(self, abgabe: str, kompetenz: str) -> FeedbackResult:
        """
        Bewertet eine studentische Abgabe.

        Args:
            abgabe (str): Code oder Text der Abgabe
            kompetenz (str): Zielkompetenz, z.B. "Verwendung von Kontrollstrukturen"

        Returns:
            FeedbackResult: strukturiertes Feedback-Objekt mit Bewertung & Tipps
        """
        pass