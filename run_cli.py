#!/usr/bin/env python3
"""
Entry point für die Kompetenzanalyse-Pipeline CLI.

Verwendung:
    python run_cli.py
"""
from cli.main import Pipeline

if __name__ == "__main__":
    Pipeline().run()