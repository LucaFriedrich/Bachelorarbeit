"""
UI-Komponenten für modernes CLI-Design.

Nutzt rich für ansprechende Terminal-Ausgaben.
"""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.text import Text
from rich.layout import Layout
from rich.live import Live
from rich import box
from typing import List, Dict, Optional
import time

# Globale Console-Instanz
console = Console()


def print_header(title: str, subtitle: str = None):
    """Zeigt einen schönen Header."""
    header_text = Text(title, style="bold cyan")
    if subtitle:
        header_text.append(f"\n{subtitle}", style="dim")
    
    panel = Panel(
        header_text,
        box=box.DOUBLE_EDGE,
        style="cyan",
        padding=(1, 2)
    )
    console.print(panel)


def print_phase_header(phase: str, description: str):
    """Zeigt einen Phase-Header."""
    text = Text()
    text.append(f"PHASE {phase}: ", style="bold yellow")
    text.append(description, style="bold white")
    
    panel = Panel(
        text,
        box=box.ROUNDED,
        style="yellow",
        padding=(0, 1)
    )
    console.print(panel)


def print_success(message: str):
    """Erfolgs-Nachricht."""
    console.print(f"[bold green]✓[/bold green] {message}")


def print_error(message: str):
    """Fehler-Nachricht."""
    console.print(f"[bold red]✗[/bold red] {message}")


def print_warning(message: str):
    """Warnung."""
    console.print(f"[bold yellow]⚠[/bold yellow] {message}")


def print_info(message: str, style: str = "dim"):
    """Info-Nachricht."""
    console.print(f"[{style}]ℹ {message}[/{style}]")


def create_progress_bar(description: str = "Processing"):
    """Erstellt eine Progress-Bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    )


def show_menu(title: str, options: List[tuple], current_state: Dict = None):
    """
    Zeigt ein schönes Menü.
    
    Args:
        title: Menü-Titel
        options: Liste von (key, label) Tupeln
        current_state: Optional Dict mit Status-Infos
    """
    # Status-Panel wenn vorhanden
    if current_state:
        status_table = Table(show_header=False, box=None)
        status_table.add_column("", style="dim")
        status_table.add_column("")
        
        for key, value in current_state.items():
            status_table.add_row(f"{key}:", f"[cyan]{value}[/cyan]")
        
        console.print(Panel(status_table, title="Status", box=box.MINIMAL))
    
    # Menü-Optionen
    menu_table = Table(show_header=False, box=None)
    menu_table.add_column("", style="bold yellow", width=4)
    menu_table.add_column("")
    
    for key, label in options:
        if key.upper() == 'Q':
            menu_table.add_row(f"[red]{key}[/red]", f"[dim]{label}[/dim]")
        else:
            menu_table.add_row(key, label)
    
    console.print(Panel(menu_table, title=title, box=box.ROUNDED))


def show_course_list(courses: List[Dict]):
    """
    Zeigt Kursliste als schöne Tabelle.
    
    Args:
        courses: Liste von Kurs-Dictionaries
    """
    table = Table(
        title="Verfügbare Moodle-Kurse",
        box=box.ROUNDED,
        show_lines=True
    )
    
    table.add_column("#", style="bold yellow", width=4)
    table.add_column("Kursname", style="cyan")
    table.add_column("Shortname", style="magenta")
    
    for i, course in enumerate(courses, 1):
        table.add_row(
            str(i),
            course['fullname'],
            course['shortname']
        )
    
    console.print(table)


def show_competency_results(competencies: List[Dict], title: str = "Gefundene Kompetenzen"):
    """
    Zeigt Kompetenzen als Tabelle.
    
    Args:
        competencies: Liste von Kompetenz-Dicts
        title: Tabellen-Titel
    """
    if not competencies:
        print_warning("Keine Kompetenzen gefunden")
        return
    
    table = Table(
        title=title,
        box=box.SIMPLE,
        show_lines=False
    )
    
    table.add_column("#", style="dim", width=4)
    table.add_column("Kompetenz", style="cyan", max_width=40)
    table.add_column("Bloom", style="yellow")
    table.add_column("Beschreibung", style="dim", max_width=50)
    
    for i, comp in enumerate(competencies[:10], 1):  # Zeige max 10
        name = comp.get('name', 'Unbenannt')
        bloom = comp.get('bloom_level', '-')
        desc = comp.get('description', '')[:50] + "..." if len(comp.get('description', '')) > 50 else comp.get('description', '')
        
        table.add_row(str(i), name, bloom, desc)
    
    if len(competencies) > 10:
        table.add_row("", f"[dim]... und {len(competencies) - 10} weitere[/dim]", "", "")
    
    console.print(table)


def show_grading_results(bewertungen: List, assignment: str):
    """
    Zeigt Bewertungsergebnisse schön formatiert.
    
    Args:
        bewertungen: Liste von KompetenzBewertung Objekten
        assignment: Assignment-Name
    """
    # Header
    console.print(Panel(f"[bold]Bewertung für: {assignment}[/bold]", box=box.DOUBLE))
    
    # Ergebnisse
    table = Table(box=box.SIMPLE, show_lines=True)
    table.add_column("Status", width=6, justify="center")
    table.add_column("Kompetenz", style="cyan")
    table.add_column("Erfüllungsgrad", style="yellow")
    table.add_column("Feedback", max_width=50)
    
    erreicht = 0
    for b in bewertungen:
        if b.erreicht:
            status = "[green]✓[/green]"
            erreicht += 1
        else:
            status = "[red]✗[/red]"
        
        feedback = b.feedback[:47] + "..." if len(b.feedback) > 50 else b.feedback
        
        table.add_row(
            status,
            b.kompetenz_name,
            b.erfuellungsgrad,
            feedback
        )
    
    console.print(table)
    
    # Zusammenfassung
    prozent = (erreicht / len(bewertungen) * 100) if bewertungen else 0
    
    summary = Panel(
        f"[bold]Erreichte Kompetenzen: {erreicht}/{len(bewertungen)} ({prozent:.1f}%)[/bold]",
        style="green" if prozent >= 60 else "yellow" if prozent >= 40 else "red",
        box=box.DOUBLE
    )
    console.print(summary)


def prompt_choice(message: str, choices: List[str] = None, default: str = None) -> str:
    """
    Fragt nach User-Input mit schönem Prompt.
    
    Args:
        message: Prompt-Nachricht
        choices: Optionale Liste erlaubter Antworten
        default: Standard-Antwort
    
    Returns:
        User-Eingabe
    """
    return Prompt.ask(
        f"[bold yellow]?[/bold yellow] {message}",
        choices=choices,
        default=default
    )


def prompt_int(message: str, min_val: int = None, max_val: int = None) -> int:
    """
    Fragt nach einer Zahl.
    
    Args:
        message: Prompt-Nachricht
        min_val: Minimum
        max_val: Maximum
    
    Returns:
        Eingegebene Zahl
    """
    while True:
        try:
            value = IntPrompt.ask(f"[bold yellow]?[/bold yellow] {message}")
            if min_val is not None and value < min_val:
                print_error(f"Wert muss mindestens {min_val} sein")
                continue
            if max_val is not None and value > max_val:
                print_error(f"Wert darf maximal {max_val} sein")
                continue
            return value
        except Exception:
            print_error("Bitte eine gültige Zahl eingeben")


def prompt_confirm(message: str, default: bool = False) -> bool:
    """
    Ja/Nein Abfrage.
    
    Args:
        message: Frage
        default: Standard-Antwort
    
    Returns:
        True wenn Ja
    """
    return Confirm.ask(
        f"[bold yellow]?[/bold yellow] {message}",
        default=default
    )


def show_spinner(message: str):
    """
    Zeigt einen Spinner für längere Operationen.
    Muss mit stop_spinner() beendet werden.
    
    Args:
        message: Nachricht neben dem Spinner
    
    Returns:
        Progress-Objekt (für stop_spinner)
    """
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    )
    task = progress.add_task(message, total=None)
    progress.start()
    return progress


def stop_spinner(progress: Progress):
    """Stoppt einen Spinner."""
    if progress:
        progress.stop()


def clear_screen():
    """Löscht den Bildschirm."""
    console.clear()


def print_divider(style: str = "dim"):
    """Druckt eine Trennlinie."""
    console.print(f"[{style}]{'─' * console.width}[/{style}]")