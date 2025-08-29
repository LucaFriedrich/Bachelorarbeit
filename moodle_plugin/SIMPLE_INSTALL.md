# Moodle Plugin Installation - Einfache Anleitung

## Was macht das Plugin?
Ermöglicht es, Kompetenzen direkt mit Assignments zu verknüpfen (was Moodle normalerweise nur über die UI erlaubt).

## Installation:

### 1. Plugin hochladen
- **WICHTIG**: Den Ordner umbenennen von `local_competency_linker` zu `competency_linker`
- Dann hochladen nach: `/moodle/local/competency_linker/`
- Per FTP oder direkt auf dem Server

### 2. In Moodle installieren
- Login als Admin
- Gehe zu: **Site Administration → Notifications**
- Moodle erkennt das neue Plugin automatisch
- Klicke auf **Upgrade Moodle database now**

### 3. Web Service aktivieren
Nach der Installation:

1. **Neue External Service erstellen:**
   - Site Administration → Plugins → Web services → External services
   - "Add" klicken
   - Name: `Competency Module Linker`
   - Short name: `competency_linker`
   - Enabled: 

2. **Funktionen hinzufügen:**
   - Bei dem neuen Service auf "Functions" klicken
   - Diese 3 Funktionen hinzufügen:
     - `local_competency_linker_add_competency_to_module`
     - `local_competency_linker_remove_competency_from_module`  
     - `local_competency_linker_set_module_competency_ruleoutcome`

3. **Token erstellen/erweitern:**
   - Site Administration → Plugins → Web services → Manage tokens
   - Entweder neuen Token mit dem Service erstellen
   - Oder bestehenden Token bearbeiten und Service hinzufügen

## Testen ob es funktioniert:

Erstelle eine Datei `test_plugin.py`:

```python
import os
from dotenv import load_dotenv
from llm.moodle.client import MoodleClient

load_dotenv()
client = MoodleClient(os.getenv('MOODLE_URL'), os.getenv('MOODLE_COMPETENCY_TOKEN'))

# Test: Funktioniert die neue Funktion?
try:
    result = client.call_function(
        'local_competency_linker_add_competency_to_module',
        cmid=15,  # "Hello World" Assignment
        competencyid=10,  # Irgendeine Kompetenz
        ruleoutcome=1  # Evidence
    )
    print(" Plugin funktioniert!")
    print(f"Ergebnis: {result}")
except Exception as e:
    if "Can't find data record" in str(e):
        print(" Plugin nicht gefunden - Installation prüfen")
    else:
        print(f" Fehler: {e}")
```

## Bei Problemen:

1. **Plugin wird nicht erkannt:**
   - Prüfe ob Ordnername korrekt ist: `competency_linker` (ohne "local_")
   - Prüfe Dateiberechtigungen (755 oder 777)

2. **Funktion nicht gefunden:**
   - Service und Token prüfen
   - Cache leeren: Site Administration → Development → Purge all caches

3. **Permission denied:**
   - User braucht Capability: `moodle/competency:coursecompetencymanage`