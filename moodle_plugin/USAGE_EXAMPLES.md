# Moodle Plugin Usage Examples

## Was macht das Plugin?

Das Plugin ermöglicht es, **Kompetenzen direkt mit Assignments/Aktivitäten zu verknüpfen** - eine Funktion die Moodle intern hat, aber NICHT über die Web Service API verfügbar macht.

## Warum ist das wichtig für die Thesis?

Ohne dieses Plugin wäre es UNMÖGLICH gewesen, die aus der KI-Analyse extrahierten Kompetenzen automatisch mit den entsprechenden Assignments zu verknüpfen. Das hätte die komplette Automatisierung zunichte gemacht.

## Die drei Plugin-Funktionen

### 1. `local_competency_linker_add_competency_to_module`
Verknüpft eine Kompetenz mit einer Aktivität (Assignment, Quiz, etc.)

```python
result = client.call_function(
    'local_competency_linker_add_competency_to_module',
    cmid=16,         # Course Module ID (die ID der Aktivität)
    competencyid=3,  # Kompetenz ID
    ruleoutcome=1    # 1=Evidence, 2=Recommend, 3=Complete
)
```

### 2. `local_competency_linker_remove_competency_from_module`
Entfernt eine Kompetenz-Verknüpfung

```python
result = client.call_function(
    'local_competency_linker_remove_competency_from_module',
    cmid=16,         # Course Module ID
    competencyid=3   # Kompetenz ID
)
```

### 3. `local_competency_linker_set_module_competency_ruleoutcome`
Ändert die Rule für eine bestehende Verknüpfung

```python
result = client.call_function(
    'local_competency_linker_set_module_competency_ruleoutcome',
    cmid=16,         # Course Module ID
    competencyid=3,  # Kompetenz ID
    ruleoutcome=3    # 3=Complete (markiert als abgeschlossen)
)
```

## Rule Outcomes erklärt

- **0 = None**: Nichts passiert
- **1 = Evidence**: Aktivitätsabschluss wird als "Beweis" für Kompetenz geloggt
- **2 = Recommend**: Kompetenz wird zur Überprüfung markiert
- **3 = Complete**: Kompetenz wird als abgeschlossen markiert

## Vollständiges Beispiel: Kompetenz-Upload Workflow

```python
import os
from dotenv import load_dotenv
from llm.moodle.client import MoodleClient
from llm.moodle.competency_uploader import MoodleCompetencyUploader

load_dotenv()

# 1. Client initialisieren
client = MoodleClient(
    os.getenv('MOODLE_URL'), 
    os.getenv('MOODLE_COMPETENCY_TOKEN')
)

# 2. Uploader erstellen
uploader = MoodleCompetencyUploader(client)

# 3. Framework für Kurs erstellen
framework_id = uploader.create_framework_for_course(
    course_shortname="TK1",
    course_fullname="Technische Grundlagen der Informatik 1"
)

# 4. Kompetenzen aus Neo4j laden und hochladen
clusters = uploader.load_competencies_from_neo4j("TK1")
mapping = uploader.upload_competency_hierarchy(clusters)

# 5. Framework mit Moodle-Kurs verknüpfen
uploader.link_framework_to_course(course_id=2)  # Moodle Course ID

# 6. Assignment-Kompetenz Mappings erstellen
# Das nutzt intern das Plugin!
uploader.map_assignment_competencies("TK1", course_id=2)
```

## Wie findet man die richtigen IDs?

### Course Module IDs finden:
```python
# Alle Module eines Kurses abrufen
contents = client.call_function(
    'core_course_get_contents',
    courseid=2  # Moodle Course ID
)

for section in contents:
    if 'modules' in section:
        for module in section['modules']:
            if module.get('modname') == 'assign':  # Nur Assignments
                print(f"Assignment: {module['name']}")
                print(f"  Module ID: {module['id']}")
```

### Kompetenz IDs finden:
```python
# Alle Kompetenzen eines Kurses
result = client.call_function(
    'core_competency_list_course_competencies',
    id=2  # Course ID
)

for comp in result:
    print(f"Kompetenz: {comp['competency']['shortname']}")
    print(f"  ID: {comp['competency']['id']}")
```

## Integration in den Grader

Für den Grader kannst du die verknüpften Kompetenzen so abrufen:

```python
# Hole alle Kompetenzen die mit einem Assignment verknüpft sind
def get_assignment_competencies(client, module_id):
    """
    Ruft die mit einem Assignment verknüpften Kompetenzen ab.
    
    HINWEIS: Diese Funktion existiert NICHT in der Standard Moodle API!
    Du müsstest entweder:
    1. Ein weiteres Plugin schreiben das diese Info liefert
    2. Die Kompetenzen aus Neo4j holen (wie bisher)
    3. Die Course-Level Kompetenzen nutzen
    """
    # Workaround: Hole alle Kurs-Kompetenzen
    # und prüfe welche "required" sind
    pass
```

## Wichtige Hinweise

1. **Das Plugin nutzt EXISTIERENDE Moodle PHP Funktionen** - wir haben nichts "gehackt", sondern nur vorhandene Funktionen exponiert

2. **Sicherheit**: Das Plugin prüft Permissions (`moodle/competency:coursecompetencymanage`)

3. **Keine direkten DB-Zugriffe**: Alles läuft über die offizielle Moodle API

4. **Fehlerbehandlung**: Wenn eine Kompetenz nicht zum Kurs gehört, gibt es einen sauberen Fehler

## Für die Thesis-Dokumentation

Dieses Plugin war **kritisch für den Erfolg**, weil:

1. Moodle's Web Service API diese Funktion nicht bereitstellt
2. Ohne das Plugin wäre keine automatische Verknüpfung möglich
3. Es ermöglicht die vollständige Automatisierung des Kompetenz-Mappings
4. Die Alternative wäre manuelle Arbeit für JEDE einzelne Kompetenz-Assignment Verknüpfung

## Testing des Plugins

```python
# Einfacher Test ob das Plugin funktioniert
def test_plugin():
    try:
        result = client.call_function(
            'local_competency_linker_add_competency_to_module',
            cmid=99999,      # Ungültige ID
            competencyid=99999,
            ruleoutcome=1
        )
    except Exception as e:
        if "course_modules" in str(e):
            print(" Plugin funktioniert!")
        elif "external_functions" in str(e):
            print(" Plugin nicht installiert")
```

## Grader Integration Vorschlag

Für morgen: Der Grader könnte so funktionieren:

1. Student lädt Lösung hoch
2. System prüft welche Kompetenzen mit dem Assignment verknüpft sind (via Plugin oder Neo4j)
3. KI evaluiert ob die Lösung diese Kompetenzen erfüllt
4. Bei Erfolg: Kompetenz als "Complete" markieren (ruleoutcome=3)
5. Feedback an Student mit erfüllten/nicht-erfüllten Kompetenzen

Das wäre dann der vollständige Kreislauf!