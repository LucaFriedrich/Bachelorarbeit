# llm/evaluate/prompts/informatik_prompts.py

"""
Spezialisierte Prompts für Informatik-Kurse und technische Fächer.
Angepasst an das Moodle Competency Framework.
"""

# GEMEINSAMES JSON-FORMAT für alle Analyse-Prompts
STANDARD_JSON_FORMAT = """{
    "kompetenzen": ["Liste der Hauptkompetenzen..."],
    "lernziele": ["Liste der Lernziele (nur Fähigkeiten/Aktionen)..."],
    "taxonomiestufe": "Bloom-Taxonomiestufe",
    "begründung": "Kurze Begründung der Einordnung",
    "topic_title": "Prägnante Überschrift für Moodle"
}"""

# 1. KURS-KLASSIFIKATION PROMPT
COURSE_CLASSIFIER_PROMPT = """Du bist ein Experte für Informatik-Curricula und Hochschulbildung.

Analysiere die folgenden Kursinhalte und klassifiziere den Kurs:

KURS-KLASSIFIKATION:
1. **Fachbereich**: 
   - Programmierung (Python, Java, C++, etc.)
   - Web-Entwicklung (HTML, CSS, JavaScript, Frameworks)
   - Datenbanken (SQL, NoSQL, Datenmodellierung)
   - Verteilte Systeme (Microservices, Cloud, Docker)
   - Algorithmen & Datenstrukturen
   - Software Engineering (Design Patterns, Testing, CI/CD)
   - IT-Sicherheit (Kryptographie, Pentesting, etc.)
   - Künstliche Intelligenz/Machine Learning
   - Netzwerke & Systemadministration
   - Theoretische Informatik (Komplexität, Automaten)
   - Sonstiges Informatik

2. **Zielgruppe**:
   - Bachelor Grundstudium (1.-2. Semester)
   - Bachelor Hauptstudium (3.-6. Semester) 
   - Master-Niveau

3. **Schwerpunkt**:
   - Theoretisch (Konzepte, Algorithmen)
   - Praktisch (Programmierung, Projekte)
   - Gemischt (Theorie + Praxis)

Antworte im folgenden JSON-Format:
{
    "fachbereich": "Verteilte Systeme",
    "zielgruppe": "Bachelor Hauptstudium",
    "schwerpunkt": "Praktisch",
    "confidence": 0.95,
    "begründung": "Kurze Begründung der Klassifikation"
}"""

# 2. INFORMATIK-SPEZIFISCHE KOMPETENZ-PROMPTS
DISTRIBUTED_SYSTEMS_PROMPT = f"""Du bist ein Experte für Verteilte Systeme und Cloud Computing.

Analysiere den Kursinhalt und extrahiere die vermittelten IT-Kompetenzen für das Moodle Competency Framework.

FOCUS AUF:
- **Fachkompetenzen**: Technische Kenntnisse (Docker, Kubernetes, Microservices, REST APIs, etc.)
- **Methodenkompetenzen**: Architektur-Design, System-Integration, Performance-Optimierung
- **Toolkompetenzen**: Konkrete Tools und Frameworks (Spring Boot, Kafka, Redis, etc.)
- **Problemlösungskompetenzen**: Debugging verteilter Systeme, Skalierungsstrategien

TAXONOMIE-STUFEN (angepasst für IT):
- **Kennen**: Konzepte verstehen (z.B. "Versteht Microservice-Prinzipien")
- **Anwenden**: Tools nutzen (z.B. "Kann Docker Container erstellen")
- **Analysieren**: Systeme bewerten (z.B. "Kann Architektur-Entscheidungen treffen")
- **Entwickeln**: Neue Lösungen schaffen (z.B. "Entwickelt skalierbare APIs")

WICHTIG: Antworte NUR mit reinem, gültigem JSON ohne Kommentare, Erklärungen oder Text davor/danach! Gib IMMER gültiges JSON zurück!

Antworte im folgenden JSON-Format:
{STANDARD_JSON_FORMAT}

Beispiele für Verteilte-Systeme-Kompetenzen:
- Docker-Container erstellen und verwalten
- REST APIs mit Spring Boot entwickeln
- Microservice-Architekturen entwerfen
- System-Performance analysieren
- Kubernetes-Deployment durchführen"""

PROGRAMMING_PROMPT = f"""Du bist ein Experte für Programmierausbildung und Software-Entwicklung.

Analysiere den Kursinhalt und extrahiere die vermittelten Programmier-Kompetenzen.

FOCUS AUF:
- **Programmiersprache**: Spezifische Syntax und Features
- **Programmierkonzepte**: OOP, Funktional, Datenstrukturen
- **Development-Skills**: Debugging, Testing, Code-Qualität  
- **Software-Engineering**: Design Patterns, Clean Code, Refactoring

Antworte im folgenden JSON-Format:
{STANDARD_JSON_FORMAT}

Beispiele für Programmier-Kompetenzen:
- Java-Programmierung
- Spring Framework nutzen
- Objektorientierte Programmierung
- Unit Testing mit JUnit
- Clean Code Prinzipien befolgen

Beispiele für Lernziele (OHNE "können" oder "Studierende"):
- Java-Klassen implementieren
- Spring-Anwendungen entwickeln
- Unit Tests schreiben
- Design Patterns anwenden"""

DATABASE_PROMPT = f"""Du bist ein Experte für Datenbank-Systeme und Datenmanagement.

Analysiere den Kursinhalt und extrahiere die vermittelten Datenbank-Kompetenzen.

FOCUS AUF:
- **Datenbankdesign**: ER-Modellierung, Normalisierung
- **Query-Skills**: SQL, NoSQL-Abfragen
- **Administration**: Performance-Tuning, Backup/Recovery
- **Integration**: ORM, Database-APIs

Antworte im folgenden JSON-Format:
{STANDARD_JSON_FORMAT}

Beispiele für Datenbank-Kompetenzen:
- ER-Diagramme erstellen
- Datenbank-Normalisierung durchführen
- SQL-Abfragen schreiben
- NoSQL-Datenbanken nutzen
- Performance-Tuning durchführen"""

WEB_DEVELOPMENT_PROMPT = f"""Du bist ein Experte für Web-Entwicklung und moderne Web-Technologien.

FOCUS AUF:
- **Frontend**: HTML5, CSS3, JavaScript, Frameworks (React, Vue, Angular)
- **Backend**: Server-side Programming, APIs, Authentication
- **Full-Stack**: Integration, Deployment, Performance
- **Web-Standards**: Accessibility, Security, SEO

Antworte im folgenden JSON-Format:
{STANDARD_JSON_FORMAT}

Beispiele für Web-Entwicklungs-Kompetenzen:
- HTML5/CSS3 entwickeln
- JavaScript programmieren
- React/Vue/Angular nutzen
- REST APIs entwickeln
- Authentication implementieren
- Web-Security gewährleisten"""

# 3. PROMPT-MAPPING
PROMPT_MAPPING = {
    "Verteilte Systeme": DISTRIBUTED_SYSTEMS_PROMPT,
    "Programmierung": PROGRAMMING_PROMPT, 
    "Datenbanken": DATABASE_PROMPT,
    "Web-Entwicklung": WEB_DEVELOPMENT_PROMPT,
    "Software Engineering": PROGRAMMING_PROMPT,  # Fallback
    "Algorithmen & Datenstrukturen": PROGRAMMING_PROMPT,  # Fallback
    "IT-Sicherheit": DISTRIBUTED_SYSTEMS_PROMPT,  # Fallback
    "Künstliche Intelligenz/Machine Learning": PROGRAMMING_PROMPT,  # Fallback
    "Netzwerke & Systemadministration": DISTRIBUTED_SYSTEMS_PROMPT,  # Fallback
    "Sonstiges Informatik": PROGRAMMING_PROMPT  # Default Fallback
}

def get_classifier_prompt() -> str:
    """Gibt den Prompt für die Kurs-Klassifikation zurück"""
    return COURSE_CLASSIFIER_PROMPT

def get_specialized_prompt(fachbereich: str) -> str:
    """
    Gibt den spezialisierten Prompt für einen Fachbereich zurück.
    
    Args:
        fachbereich: Der klassifizierte Fachbereich
        
    Returns:
        Entsprechender spezialisierter Prompt
    """
    return PROMPT_MAPPING.get(fachbereich, PROGRAMMING_PROMPT)

def list_available_specializations() -> list[str]:
    """Listet alle verfügbaren Spezialisierungen auf"""
    return list(PROMPT_MAPPING.keys())