# TODO: Feedback-System Integration

##  Hauptziel
Das bestehende Feedback-Framework mit der Kompetenz-Pipeline verknüpfen, um Studenten-Abgaben gegen die extrahierten Kurs-Kompetenzen zu bewerten.

##  Kern-Aufgaben

### 1. Neo4j Integration für Kompetenz-Persistenz
- [ ] Funktion zum Laden aller Kompetenzen eines Kurses aus Neo4j
- [ ] Query für: Kompetenz → Source Documents → Beispiel-Code
- [ ] Cache für geladene Kompetenzen pro Kurs

```python
def _load_competencies_from_graph(self, course_id: str):
    """Lädt alle Kompetenzen für einen Kurs aus Neo4j"""
    query = """
    MATCH (d:Document)-[:TEACHES]->(c:Competency)
    WHERE d.file_path CONTAINS $course_id
    RETURN DISTINCT c.name as kompetenz,
           c.description as beschreibung,
           collect(DISTINCT d.filename) as source_docs
    """
```

### 2. RAG-Enhancement für Feedback
- [ ] ChromaDB-Queries für kompetenz-spezifische Code-Beispiele
- [ ] Kontext-Anreicherung aus Vorlesungsmaterialien
- [ ] Ähnliche Patterns aus Kursmaterial finden

```python
def _get_competency_context(self, kompetenz: str):
    # Query ChromaDB für relevante Code-Snippets
    # Filtere nach Code-Patterns
    # Nutze DocumentManager für RAG
```

### 3. Enhanced CompetencyLLM Implementation
- [ ] Erweitere base.py um Kurs-Kontext
- [ ] Multi-Kompetenz Bewertung (alle auf einmal)
- [ ] Strukturierte Prompts mit Kurs-spezifischen Beispielen

```python
class EnhancedCompetencyLLM(CompetencyLLM):
    def __init__(self, doc_manager: DocumentManager, course_id: str):
        self.doc_manager = doc_manager
        self.course_id = course_id
        self.kompetenz_cache = self._load_course_competencies()
```

### 4. Intelligente Prompt-Gestaltung
- [ ] Template für Code-Bewertung mit Kontext
- [ ] Beispiel-basiertes Feedback (zeige gute Lösungen)
- [ ] Konkrete Verbesserungsvorschläge basierend auf Kursmaterial

### 5. Test mit sample_files/abgabe.py
- [ ] Bewerte gegen "Verwendung von Kontrollstrukturen"
- [ ] Bewerte gegen "Verwendung von Datentypen"
- [ ] Generiere Lernpfad-Empfehlungen

##  Konkrete Implementierungs-Schritte

### Phase 1: Basis-Integration (2h)
1. `CompetencyRepository` Klasse erstellen
2. Neo4j Query-Functions implementieren
3. Einfacher Test mit einer Kompetenz

### Phase 2: RAG-Enhancement (2h)
1. ChromaDB Integration in Feedback
2. Code-Pattern Matching implementieren
3. Kontext-aware Prompts erstellen

### Phase 3: Vollständige Bewertung (2h)
1. Multi-Kompetenz Evaluator
2. Lernpfad-Generator
3. Moodle-Export Format

##  Code-Snippets zum Kopieren

### Holistische Bewertung
```python
def evaluate_submission_holistic(self, abgabe: str) -> Dict[str, FeedbackResult]:
    """Bewertet eine Abgabe gegen ALLE Kurs-Kompetenzen"""
    results = {}
    all_competencies = self.kompetenz_cache['konsolidierte_kompetenzen']
    
    for kompetenz in all_competencies:
        feedback = self.evaluate(abgabe, kompetenz)
        if feedback.kompetenz_erfüllt != "nicht sichtbar":
            results[kompetenz] = feedback
    
    return results
```

### Lernpfad-Empfehlungen
```python
def generate_learning_recommendations(self, feedback_results):
    weak_competencies = [
        komp for komp, result in feedback_results.items()
        if result.kompetenz_erfüllt in ["nicht sichtbar", "oberflächlich"]
    ]
    
    recommendations = []
    for weak_comp in weak_competencies:
        relevant_docs = self._find_documents_for_competency(weak_comp)
        recommendations.append({
            "kompetenz": weak_comp,
            "empfohlene_materialien": relevant_docs
        })
```

##  Erwartetes Ergebnis für abgabe.py

```json
{
  "Verwendung von Kontrollstrukturen": {
    "kompetenz_erfüllt": "funktional erfüllt",
    "beispielhafte_beobachtung": "if-else in add_user(), for-loop in show_admins()",
    "tipp": "Nutze switch-case für menu() für bessere Struktur"
  },
  "Verwendung von Datentypen": {
    "kompetenz_erfüllt": "sicher angewendet",
    "beispielhafte_beobachtung": "Dictionary für User-Objekte, Listen-Manipulation",
    "tipp": "Erwäge Klassen statt Dictionaries für Type-Safety"
  }
}
```

## ⚡ Quick Win für morgen
1. Starte mit der einfachsten Integration
2. Lade Kompetenzen aus Neo4j
3. Bewerte abgabe.py gegen eine Kompetenz
4. Wenn das funktioniert → erweitern

##  Nicht vergessen
- DocumentManager ist bereits da - nutze ihn!
- Neo4j hat alle Daten - keine neue Persistenz nötig
- ChromaDB hat den Kurs-Content - perfekt für RAG
- Keep it simple - erst basic, dann fancy