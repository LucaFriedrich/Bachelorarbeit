# Readme zur Bachelorarbeit von Luca Friedrich

## Installation

1. **Klonen**
```bash
git clone https://github.com/LucaFriedrich/Bachelorarbeit
cd ba_be
```

2. **Docker Setup** - `docker-compose.yml`:

`docker-compose up -d`

3. **Dependencies**
```bash
pip install -r requirements.txt
```

4. **.env Datei**

Erstellen Sie eine `.env` Datei im Projektverzeichnis mit der im Anhang der Bachelorarbeit vorhanden Datei.
Diese enthält alle notwendigen, über Guthaben verfügende API-Keys und Konfigurationsparameter
Das Hochladen der Datei in das Repository ist aus Sicherheitsgründen und der automatischen Löschung von API-Keys nicht möglich.

5. **Start**
```bash
python run_cli.py
```
oder
```bash
python3 run_cli.py
```

Die GUI der Neo4j-Datenbank ist unter `http://localhost:7474` erreichbar. Das Passwort ist in der `.env` Datei definiert.