#!/usr/bin/env python3
"""
Hauptprogramm für die Kompetenzanalyse-Pipeline.

Minimalistisches CLI ohne unnötige Komplexität.

Author: Luca
Date: 2025-01
"""
import sys
import logging
from pathlib import Path
from typing import Dict, Callable
import time

from cli.phases.ingestion import run_ingestion
from cli.phases.classification import run_classification
from cli.phases.analysis import run_analysis
from cli.phases.assignment_analysis import run_assignment_analysis
from cli.phases.upload import run_moodle_upload
from cli.phases.grading import run_submission_grading
# TODO: Implementieren
# from cli.phases.aggregation import run_aggregation

from cli.ui_components import (
    console, print_header, print_phase_header, print_success, print_error,
    print_warning, print_info, show_menu, show_course_list, prompt_choice,
    prompt_int, prompt_confirm, show_spinner, stop_spinner, clear_screen,
    print_divider
)

from logger import update_all_loggers
from dotenv import load_dotenv
import os
import questionary
from cli.dev_cache import save_pipeline_result, load_cached_analysis, has_cached_analysis

load_dotenv()


class Pipeline:
    """Einfache Pipeline-Klasse ohne Overcomplexity."""
    
    def __init__(self):
        self.model = "claude-opus-4-1-20250805"  # Standard-Modell Opus 4.1
        # Debug-Modus basierend auf LOG_LEVEL aus .env
        log_level = os.getenv('LOG_LEVEL', 'ERROR').upper()
        self.debug_mode = log_level in ['DEBUG', 'INFO']
        self.setup_logging()
        
        # Pipeline-State (bleibt zwischen Menü-Aufrufen erhalten)
        self.doc_manager = None
        self.course_name = None
        self.course_id = None
        
        # Menu-Actions als Dictionary statt if-else
        self.menu_actions = {
            '1': self.select_and_load_course,
            '2': self.run_pipeline,
            '3': self.select_model,
            '4': self.analyze_assignment,
            '5': self.upload_to_moodle,
            '6': self.run_submission_grading,
            'D': self.toggle_debug,
            'Q': self.quit
        }
    def run_analysis_pipeline(self, shortname):
        """
        Führt die eigentliche Pipeline aus.
        Einfach alle Phasen nacheinander.
        """
        try:
            console.print("\n")
            print_phase_header("1", "Dokumente laden")
            
            progress = show_spinner(f"Lade Dokumente für Kurs '{shortname}'...")
            self.doc_manager, self.course_name, self.course_id = run_ingestion(shortname)
            stop_spinner(progress)
            
            print_success(f"Kurs geladen: {self.course_name} (ID: {self.course_id})")
            time.sleep(0.5)

            # Phase 2: Classification
            console.print("\n")
            print_phase_header("2", "Kurs klassifizieren")
            
            progress = show_spinner(f"Klassifiziere mit {self.model}...")
            classification = run_classification(self.doc_manager, self.course_name, self.model)
            stop_spinner(progress)

            if not classification:
                print_error("Klassifikation fehlgeschlagen")
                return
            
            print_success("Klassifikation erfolgreich")
            time.sleep(0.5)

            # Phase 3: Analysis
            console.print("\n")
            print_phase_header("3", "Dokumente analysieren")
            
            progress = show_spinner(f"Analysiere mit {self.model}...")
            results = run_analysis(self.doc_manager, classification, self.course_name, self.model)
            stop_spinner(progress)
            
            if not results:
                print_error("Keine Analysen durchgeführt")
                return
            
            print_success(f"{len(results)} Dokumente analysiert")
            
            # Speichere Ergebnis für Cache
            save_pipeline_result(self.course_name, self.model, self.doc_manager, 
                               classification, results)

            console.print("\n")
            print_success("Pipeline abgeschlossen - Menü wird wieder angezeigt")
            time.sleep(1)

        except Exception as e:
            print_error(f"Pipeline-Fehler: {e}")
            logging.error(f"Pipeline-Fehler: {e}", exc_info=True)

    def setup_logging(self):
        """Minimales Logging-Setup mit zentraler logger.py."""
        import warnings
        
        # LOG_LEVEL wird aus .env geladen oder über toggle_debug gesetzt
        # Hier nur sicherstellen dass alle Logger aktualisiert sind
        update_all_loggers()
        
        # Unterdrücke die nervige Sprach-Warning von unstructured
        warnings.filterwarnings("ignore", message=".*No languages specified.*")
    
    def run(self):
        """Hauptschleife."""
        clear_screen()
        print_header("KOMPETENZANALYSE-PIPELINE", "KI-basierte Curriculum-Analyse für Moodle")
        
        # Kurs direkt beim Start auswählen
        console.print("\n[bold cyan]Kurs auswählen:[/bold cyan]")
        shortname = self.select_course()
        if not shortname:
            print_error("Kein Kurs ausgewählt. Beende.")
            return
        
        # Prüfe ob gecachte Analyse existiert
        if has_cached_analysis(shortname):
            choice = questionary.select(
                f"Es existiert bereits eine Analyse für '{shortname}'. Was möchtest du tun?",
                choices=[
                    "Bestehende Analyse nutzen",
                    "Neue Analyse durchführen"
                ],
                style=questionary.Style([
                    ('question', 'bold fg:#0066cc'),  # Dunkelblau statt Gelb
                    ('pointer', 'fg:#ff9d00 bold'),
                    ('highlighted', 'fg:#ff9d00 bold'),
                ])
            ).ask()
            
            if choice == "Bestehende Analyse nutzen":
                cached = load_cached_analysis(shortname)
                if cached:
                    self.doc_manager, classification, analysis_results, cached_model = cached
                    self.course_name = shortname
                    self.course_id = shortname
                    print_success(f"Analyse geladen (erstellt mit {cached_model})")
                    print_info(f"{len(analysis_results)} Dokumente in der Analyse")
                else:
                    print_error("Cache konnte nicht geladen werden")
                    return
            else:
                # Neue Analyse wird über Pipeline ausführen gemacht
                self.course_name = shortname
                self.course_id = shortname
                print_info("Nutze Menü-Option 'Pipeline ausführen' für neue Analyse")
        else:
            self.course_name = shortname
            self.course_id = shortname
            print_success(f"Kurs '{shortname}' ausgewählt")
        
        time.sleep(1)
        
        # Hauptmenü-Loop mit Pfeiltasten-Navigation
        while True:
            clear_screen()  # Clear vor jedem Menü
            choice = self.show_interactive_menu()
            
            if choice == "Beenden":
                self.quit()
            elif choice and not choice.startswith("─"):  # Ignoriere Trennlinien
                clear_screen()  # Clear vor jeder Aktion
                # Führe die gewählte Aktion aus
                if choice == "Pipeline ausführen (Phase 1-3)":
                    self.run_pipeline()
                    console.print("\n")
                    prompt_choice("Enter zum Fortfahren", default="")
                elif choice == "Assignment-Analyse":
                    self.analyze_assignment()
                    console.print("\n")
                    prompt_choice("Enter zum Fortfahren", default="")
                elif choice == "Kompetenzen nach Moodle uploaden":
                    self.upload_to_moodle()
                    console.print("\n")
                    prompt_choice("Enter zum Fortfahren", default="")
                elif choice == "Submission-Bewertung":
                    self.run_submission_grading()
                    console.print("\n")
                    prompt_choice("Enter zum Fortfahren", default="")
                elif choice == "Anderen Kurs wählen":
                    self.select_and_load_course()
                elif choice == "Modell wechseln":
                    self.select_model()
                    time.sleep(1)  # Kurz warten damit man die Meldung sieht
                elif choice.startswith("Debug-Modus"):
                    self.toggle_debug()
                    time.sleep(1)  # Kurz warten damit man die Meldung sieht
    
    def show_interactive_menu(self):
        """
        Zeigt ein interaktives Menü mit Pfeiltasten-Navigation.
        
        Returns:
            Gewählte Option als String
        """
        # Header
        print_header("KOMPETENZANALYSE-PIPELINE", "KI-basierte Curriculum-Analyse")
        
        # Status anzeigen
        console.print(f"\n[dim]Kurs:[/dim] [cyan]{self.course_name or 'Keiner'}[/cyan]")
        console.print(f"[dim]Modell:[/dim] [cyan]{self.model}[/cyan]")
        console.print(f"[dim]Debug:[/dim] [cyan]{'An' if self.debug_mode else 'Aus'}[/cyan]\n")
        
        # Menü-Optionen (logisch sortiert: Hauptaktionen -> Zusatzfunktionen -> Einstellungen)
        options = [
            "Pipeline ausführen (Phase 1-3)",
            "Assignment-Analyse",
            "Kompetenzen nach Moodle uploaden",
            "Submission-Bewertung",
            "─────────────────",  # Trennlinie
            "Anderen Kurs wählen",
            "Modell wechseln",
            f"Debug-Modus {'aus' if self.debug_mode else 'ein'}schalten",
            "─────────────────",  # Trennlinie
            "Beenden"
        ]
        
        # Interaktive Auswahl mit Pfeiltasten
        choice = questionary.select(
            "Was möchtest du tun?",
            choices=options,
            style=questionary.Style([
                ('question', 'bold'),
                ('pointer', 'fg:#ff9d00 bold'),
                ('highlighted', 'fg:#ff9d00 bold'),
                ('selected', 'fg:#5f819d'),
            ])
        ).ask()
        
        return choice
    
    def show_menu(self):
        """Legacy-Funktion für Kompatibilität."""
        pass
    
    def select_and_load_course(self):
        """Wählt einen anderen Kurs."""
        shortname = self.select_course()
        if shortname:
            self.course_name = shortname
            self.course_id = shortname
            self.doc_manager = None  # Reset manager
            print_success(f"Kurs gewechselt zu: {shortname}")
    
    def run_pipeline(self):
        """
        Führt die Analyse-Pipeline aus.
        
        Wrapper-Funktion für run_analysis_pipeline(), die:
        - Prüft ob ein Kurs ausgewählt ist
        - Als Menü-Action ohne Parameter aufrufbar ist
        """
        if not self.course_name:
            print_error("Kein Kurs ausgewählt!")
            return
        
        self.run_analysis_pipeline(self.course_name)
    
    def select_course(self) -> str:
        """
        Zeigt verfügbare Kurse und gibt den shortname des gewählten zurück.
        
        Returns:
            Shortname des gewählten Kurses oder "" bei Abbruch
        """
        from llm.moodle import MoodleClient, CourseDownloader
        import os
        
        moodle_url = os.getenv('MOODLE_URL')
        moodle_token = os.getenv('MOODLE_TOKEN')
        
        if not moodle_url or not moodle_token:
            print_error("MOODLE_URL und MOODLE_TOKEN müssen in .env gesetzt sein")
            return ""
            
        client = MoodleClient(moodle_url, moodle_token)
        downloader = CourseDownloader(client)
        
        # Hole alle Kurse
        progress = show_spinner("Lade Kursliste von Moodle...")
        courses = downloader.get_all_courses()
        stop_spinner(progress)
        
        if not courses:
            print_error("Keine Kurse gefunden")
            return ""
        
        # Zeige die Tabelle mit Kursen
        show_course_list(courses)
        
        # Erstelle Optionen für interaktive Auswahl
        course_options = []
        for i, course in enumerate(courses, 1):
            course_options.append(f"{i}. {course['fullname']} ({course['shortname']})")
        course_options.append("Abbrechen")
        
        # Interaktive Auswahl mit Pfeiltasten
        console.print("")  # Leerzeile zwischen Tabelle und Menü
        choice = questionary.select(
            "Wähle einen Kurs",
            choices=course_options,
            style=questionary.Style([
                ('question', 'bold cyan'),
                ('pointer', 'fg:#ff9d00 bold'),
                ('highlighted', 'fg:#ff9d00 bold'),
                ('selected', 'fg:#5f819d'),
            ])
        ).ask()
        
        if choice == "Abbrechen" or not choice:
            return ""
        
        # Extrahiere shortname aus der Auswahl
        for i, course in enumerate(courses, 1):
            if f"{i}. {course['fullname']} ({course['shortname']})" == choice:
                print_success(f"Gewählt: {course['fullname']}")
                return course['shortname']
        
        return ""

    
    def analyze_assignment(self):
        """Analysiert ein Assignment und ordnet Kompetenzen zu."""
        if self.course_name is None:
            print_error("Erst einen Kurs laden!")
            return
        
        print_phase_header("T", f"Assignment-Analyse für {self.course_name}")
        result = run_assignment_analysis(self.course_name, self.model)
        
        if result:
            console.print("\n")
            print_success(f"Assignment '{result['assignment']}' erfolgreich analysiert")
            print_info(f"{len(result['competencies'])} Kompetenzen zugeordnet")
        else:
            console.print("\n")
            print_error("Assignment-Analyse fehlgeschlagen")
    
    def upload_to_moodle(self):
        """Uploaded Kompetenzen nach Moodle."""
        if self.course_name is None:
            print_error("Erst einen Kurs laden!")
            return
        
        print_phase_header("U", f"Moodle Upload für {self.course_name}")
        result = run_moodle_upload(self.course_name)
        
        if result and result['success']:
            console.print("\n")
            print_success("Upload erfolgreich abgeschlossen")
        else:
            console.print("\n")
            print_error("Upload fehlgeschlagen oder abgebrochen")
    
    def run_submission_grading(self):
        """Führt Submission-Bewertung durch."""
        if self.course_name is None:
            print_error("Erst einen Kurs laden!")
            return
        
        print_phase_header("G", f"Submission Grading für {self.course_name}")
        result = run_submission_grading(self.course_name, self.model)
        
        if result:
            console.print("\n")
            if 'ergebnisse' in result:  # Mehrere Submissions
                print_success(f"{result['bewertet']} Submissions bewertet")
            else:  # Einzelne Submission
                erfolg = result.get('erfolgsquote', 0)
                print_success(f"Bewertung abgeschlossen ({erfolg*100:.0f}% Kompetenzen erreicht)")
        else:
            console.print("\n")
            print_error("Bewertung fehlgeschlagen oder abgebrochen")
    
    def show_results(self, aggregation: Dict):
        """Zeigt die Analyse-Ergebnisse."""
        items = aggregation.get('consolidated_items', [])
        print(f"\n✓ Analyse abgeschlossen")
        print(f"  {len(items)} Kompetenzen gefunden")
        
        if items:
            print("\nTop 5 Kompetenzen:")
            for i, comp in enumerate(items[:5], 1):
                print(f"  {i}. {comp}")
    
    def select_model(self):
        """Modell-Auswahl mit interaktivem Menü."""
        models = [
            # OpenAI
            ("gpt-4o-mini", "OpenAI - Schnell & günstig"),
            ("gpt-4o", "OpenAI - Standard, ausgewogen"),
            ("gpt-5", "OpenAI GPT-5 - Neuestes Modell, beste Performance"),
            ("o3", "OpenAI - Reasoning, komplex"),
            # Claude
            ("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet - Sehr gut"),
            ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku - Schnell & günstig"),
            ("claude-3-7-sonnet-20250219", "Claude 3.7 - Hybrid mit Reasoning"),
            ("claude-sonnet-4-20250514", "Claude Sonnet 4 - Hybrid, 64K Output"),
            ("claude-opus-4-20250514", "Claude Opus 4 - Bestes Coding"),
            ("claude-opus-4-1-20250805", "Claude Opus 4.1 - Neueste Version"),
        ]
        
        # Erstelle Optionen mit Markierung des aktuellen Modells
        options = []
        for model, desc in models:
            if model == self.model:
                options.append(f"✓ {model} - {desc}")
            else:
                options.append(f"  {model} - {desc}")
        options.append("Abbrechen")
        
        # Interaktive Auswahl
        choice = questionary.select(
            f"Aktuelles Modell: {self.model}\nWähle ein neues Modell:",
            choices=options,
            style=questionary.Style([
                ('question', 'bold cyan'),
                ('pointer', 'fg:#ff9d00 bold'),
                ('highlighted', 'fg:#ff9d00 bold'),
                ('selected', 'fg:#5f819d'),
            ])
        ).ask()
        
        if choice and choice != "Abbrechen":
            # Extrahiere Modellname aus der Auswahl
            for model, desc in models:
                if model in choice:
                    self.model = model
                    print_success(f"Modell gewechselt zu: {self.model}")
                    break
    
    def toggle_debug(self):
        """Schaltet Debug-Modus um."""
        import os
        self.debug_mode = not self.debug_mode
        
        # Setze LOG_LEVEL für alle Module
        os.environ['LOG_LEVEL'] = 'INFO' if self.debug_mode else 'ERROR'
        
        # Aktualisiere alle existierenden Logger mit dem neuen Level
        update_all_loggers()
        
        if self.debug_mode:
            print_success("Debug-Modus aktiviert - detaillierte Ausgaben")
        else:
            print_success("Debug-Modus deaktiviert - minimale Ausgaben")
    
    def quit(self):
        """Beendet das Programm."""
        console.print("\n[bold cyan]Auf Wiedersehen![/bold cyan]")
        sys.exit(0)


if __name__ == "__main__":
    Pipeline().run()