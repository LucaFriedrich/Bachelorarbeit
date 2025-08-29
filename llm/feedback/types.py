from pydantic import BaseModel, Field
from typing import Literal, List

class FeedbackResult(BaseModel):
    kompetenz_erfüllt: Literal[
        "nicht sichtbar",
        "oberflächlich",
        "funktional erfüllt",
        "sicher angewendet",
        "besonders gut umgesetzt"
    ]
    beispielhafte_beobachtung: str
    tipp: str
    komplettes_feedback: str


# ==================== Submission Evaluation Models ====================

class KompetenzBewertung(BaseModel):
    """Bewertung einer einzelnen Kompetenz für eine Submission."""
    kompetenz_name: str
    kompetenz_beschreibung: str
    bloom_level: str
    erreicht: bool
    erfuellungsgrad: str  # Der Literal-Wert von kompetenz_erfüllt
    feedback: str
    tipp: str
    beispielhafte_beobachtung: str


class BewertungsZusammenfassung(BaseModel):
    """Zusammenfassung aller Kompetenzbewertungen."""
    total: int
    erreicht: int
    erfolgsquote: float = Field(ge=0.0, le=1.0)


class SubmissionBewertung(BaseModel):
    """Komplette Bewertung einer Student-Submission."""
    assignment: str
    filepath: str
    user: str
    kompetenzen_gefunden: int
    bewertungen: List[KompetenzBewertung]
    zusammenfassung: BewertungsZusammenfassung