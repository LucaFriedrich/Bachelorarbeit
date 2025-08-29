# llm/evaluate/kompetenz_evaluator.py

from typing import Any, Dict, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from llm.evaluate.base import BaseEvaluator, KompetenzResult
from llm.evaluate.factory import register_evaluator
from llm.evaluate.document_manager import DocumentManager
from llm.evaluate.prompts.informatik_prompts import get_classifier_prompt, get_specialized_prompt
from llm.shared.llm_factory import get_llm
from llm.shared.json_utils import clean_json_response
import json
import re


@register_evaluator("kompetenz")
class KompetenzEvaluator(BaseEvaluator):
    """
    Evaluator für die Extraktion von Kompetenzen aus Kursinhalten.
    Nutzt RAG mit ChromaDB für bessere Kontextualisierung.
    """
    
    def __init__(self, model: str, use_rag: bool = True, **kwargs):
        from llm.shared.llm_factory import MODEL_TO_PROVIDER
        provider = MODEL_TO_PROVIDER.get(model, "openai")
        super().__init__(provider, use_rag)
        
        # LLM über zentrale Factory
        # o1/o3 Modelle unterstützen keine temperature
        self.logger.info(f"Initialisiere LLM mit Model: {model}")
        if model.startswith("o1") or model in ["o3", "gpt-5"]:
            self.logger.info(f"O1/O3 Model erkannt - keine temperature")
            try:
                self.llm = get_llm(model=model)
            except Exception as e:
                self.logger.error(f"Fehler beim Laden des O1/O3 Modells: {e}")
                raise ValueError(f"Modell {model} konnte nicht geladen werden. Bitte prüfen Sie die Modellkonfiguration.", e)
            self.logger.info("o1/03 erstellt")
        else:
            self.logger.info(f"Standard Model - temperature=0.1")
            self.llm = get_llm(
                model=model,
                temperature=kwargs.get("temperature", 0.1)
            )
        
        # DocumentManager für intelligente Dokumentenverwaltung
        self.doc_manager = DocumentManager()
        
        # GraphIngestion einmal erstellen und für alle Dokumente wiederverwenden!
        # Das ist wichtig für den Embedding-Cache
        from llm.graph.graph_ingestion import GraphIngestion
        self.graph_ingestion = GraphIngestion()
        
        self.logger.info(f" KompetenzEvaluator erfolgreich initialisiert: {model}, RAG: {use_rag}")
    
    def _clean_json_response(self, response_content: str) -> str:
        """
        Bereinigt LLM-Antworten von Markdown-Code-Blöcken für JSON-Parsing.
        Nutzt die zentrale json_utils Funktion.
        
        Args:
            response_content: Rohe LLM-Antwort
            
        Returns:
            Bereinigter JSON-String
        """
        # Erst Text vor JSON entfernen (Claude gibt oft Erklärungen vor dem JSON)
        if '{' in response_content:
            # Finde den ersten { und nimm alles ab dort
            json_start = response_content.find('{')
            response_content = response_content[json_start:]
            
            # Finde das letzte } und nimm alles bis dort
            json_end = response_content.rfind('}')
            if json_end != -1:
                response_content = response_content[:json_end + 1]
        
        # Dann nutze zentrale Funktion für Markdown-Bereinigung
        return clean_json_response(response_content)
    
    def _generate_smart_rag_query(self, full_content: str, fachbereich: str = None) -> str:
        """
        Nutzt LLM um intelligente RAG-Query aus Dokumentinhalt zu generieren.
        
        Args:
            full_content: Kompletter Dokumentinhalt
            fachbereich: Klassifizierter Fachbereich (optional)
            
        Returns:
            LLM-generierte RAG-Query mit relevanten Schlüsselwörtern
        """
        # Verwende günstiges Model für RAG-Query-Generierung
        query_llm = get_llm(model="gpt-4o-mini", temperature=0.1)
        
        # Begrenze Content für Query-Generierung (erste 1000 Zeichen)
        content_sample = full_content[:1000] + "..." if len(full_content) > 1000 else full_content
        
        system_prompt = f"""Du bist ein Experte für Informationsextraktion und Suchmaschinenoptimierung.

Analysiere den folgenden Dokumentinhalt und extrahiere die 5-8 wichtigsten Schlüsselwörter/Begriffe, die für die Suche nach ähnlichen Inhalten in einer Kursdatenbank relevant wären.

Fokus auf:
- Technische Begriffe und Tools
- Methodische Konzepte  
- Fachspezifische Terminologie
- Lernrelevante Themen

{f"Kontext: Das Dokument gehört zum Fachbereich '{fachbereich}'." if fachbereich else ""}

Antworte im JSON-Format:
{{
    "keywords": ["Begriff1", "Begriff2", "Begriff3", ...],
    "query": "Optimierte Suchquery für ähnliche Kursinhalte"
}}"""

        user_prompt = f"Analysiere diesen Dokumentinhalt:\n\n{content_sample}"
        
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = query_llm.invoke(messages)
            
            # JSON bereinigen und parsen
            cleaned_content = self._clean_json_response(response.content)
            result = json.loads(cleaned_content)
            
            keywords = result.get("keywords", [])
            smart_query = result.get("query", "")
            
            print(f"\n RAG KEYWORDS: {keywords}")
            # RAG-Query wird nicht geloggt - zu verbose
            
            # Fallback wenn LLM keine gute Query liefert
            if not smart_query and keywords:
                smart_query = f"Themen: {', '.join(keywords)} {fachbereich or 'IT'} Kompetenzen"
            elif not smart_query:
                # Ultima ratio fallback
                smart_query = f"{content_sample[:100]} Kompetenzen Lernziele"
            
            return smart_query
            
        except Exception as e:
            self.logger.warning(f" Smart RAG-Query-Generierung fehlgeschlagen: {e}")
            
            # Fallback: Einfache Extraktion
            first_sentence = full_content.split('.')[0][:150]
            fallback_query = f"{first_sentence} {fachbereich or 'IT'} Kompetenzen"
            return fallback_query
    
    def extract_kompetenzen_from_assignment(self, assignment_description: str, 
                                           course_materials: List[str] = None) -> List[str]:
        """
        Extrahiert Lernziele/Kompetenzen aus einer Assignment-Beschreibung MIT Kurskontext.
        
        Args:
            assignment_description: Beschreibung der Aufgabe (z.B. aus Moodle)
            course_materials: Liste von relevanten Kursmaterialien (optional)
            
        Returns:
            Liste von extrahierten Kompetenzen
        """
        self.logger.info(" Extrahiere kontextbasierte Kompetenzen aus Assignment")
        
        # Wenn Kursmaterialien vorhanden, nutze RAG für Kontext
        context_info = ""
        if course_materials and self.doc_manager:
            # Generiere Query basierend auf Assignment
            query = f"{assignment_description} Konzepte Methoden Techniken"
            
            # Hole relevante Chunks aus den Kursmaterialien
            related_chunks = self.doc_manager.get_related_content(query, "tk1", k=5)
            
            if related_chunks:
                context_info = "\n\nRELEVANTE KURSINHALTE (aus Vorlesungen/Übungen):\n"
                for i, chunk in enumerate(related_chunks[:3], 1):
                    context_info += f"\n[Kontext {i}]:\n{chunk.page_content[:500]}...\n"
        
        system_prompt = """Du bist ein erfahrener Dozent für Informatik, der präzise Lernziele formuliert.

WICHTIG: Extrahiere SPEZIFISCHE, MESSBARE Lernziele basierend auf:
1. Der konkreten Aufgabenstellung
2. Den tatsächlich gelehrten Konzepten aus dem Kurs
3. Dem Schwierigkeitsgrad und Kontext

Formuliere Lernziele die:
- KONKRETE Konzepte/Techniken benennen (nicht generisch!)
- MESSBAR sind (man kann prüfen ob erfüllt oder nicht)
- Den KURSKONTEXT reflektieren (was wurde tatsächlich gelehrt, was ist realistisch auf Basis des Könnens der Studierenden? Ein Anfängerkurs hat andere Lernziele als ein fortgeschrittener-Kurs)
- ANALYTISCH formuliert sind (z.B. "Beherrscht Schleifen für Iterationen")

VERMEIDE generische Aussagen wie:
- "Kann ein Programm schreiben"
- "Versteht Python"

NUTZE analytische Formulierungen wie:
- "Wendet das Konzept der Funktionsdeklaration korrekt an"
- "Nutzt Kontrollstrukturen (if/else) zur Fallunterscheidung"
- "Implementiert die in Vorlesung 3 besprochene Modularisierung"

Antworte NUR mit einem JSON-Array der spezifischen Lernziele."""
        
        user_prompt = f"Aufgabenstellung: {assignment_description}"
        if context_info:
            user_prompt += f"\n{context_info}"
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        try:
            response = self.llm.invoke(messages)
            content = self._clean_json_response(response.content)
            kompetenzen = json.loads(content)
            
            if isinstance(kompetenzen, list):
                self.logger.info(f" {len(kompetenzen)} spezifische Lernziele extrahiert")
                # Zeige die ersten paar zur Kontrolle
                for i, komp in enumerate(kompetenzen[:3], 1):
                    self.logger.info(f"   {i}. {komp}")
                return kompetenzen
            else:
                self.logger.warning("Unerwartetes Format bei Lernziel-Extraktion")
                return []
                
        except Exception as e:
            self.logger.error(f"Fehler bei kontextbasierter Lernziel-Extraktion: {e}")
            # Fallback zu einfacher Extraktion
            return ["Grundlegende Programmierkonzepte anwenden"]
    
    def evaluate_code(self, code: str, filename: str = "submission.py") -> KompetenzResult:
        """
        Evaluiert studentischen Code und extrahiert Kompetenzen.
        
        Args:
            code: Der zu analysierende Code
            filename: Name der Datei (für Kontext)
            
        Returns:
            KompetenzResult mit erkannten Kompetenzen
        """
        # Nutze die normale evaluate Methode mit Code-spezifischen Metadaten
        metadata = {
            "filename": filename,
            "doc_type": "code",
            "language": "python"
        }
        
        return self.evaluate(code, metadata=metadata)
    
    def evaluate(self, content: Any, **kwargs) -> KompetenzResult:
        """
        Extrahiert Kompetenzen aus Kursinhalten.
        
        Args:
            content: Kursinhalt (Text oder bereits zusammengefasst)
            **kwargs:
                - kurs_metadaten: Dict mit Kursinfos (Name, Semester, etc.)
                - use_context: Anzahl der RAG-Dokumente (default: 5)
                - taxonomie_focus: Spezifische Taxonomie-Ebene fokussieren
        """
        kurs_metadaten = kwargs.get("kurs_metadaten", {})
        k_documents = kwargs.get("use_context", 5)
        taxonomie_focus = kwargs.get("taxonomie_focus", None)
        
        # RAG-Kontext holen, wenn aktiviert
        context_docs = []
        if self.use_rag and k_documents > 0:
            context_docs = self.get_rag_context(str(content), k=k_documents)
        
        # System-Prompt
        system_prompt = self._build_system_prompt(taxonomie_focus)
        
        # User-Prompt mit Kontext
        user_prompt = self._build_user_prompt(content, context_docs, kurs_metadaten)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        try:
            response = self.llm.invoke(messages)
            self.logger.debug(f"Kompetenz-Extraktion Response erhalten")
            
            # Bereinige die Antwort von Markdown-Code-Blöcken
            cleaned_content = self._clean_json_response(response.content)
            result_json = json.loads(cleaned_content)
            
            return KompetenzResult(
                kompetenzen=result_json.get("kompetenzen", []),
                lernziele=result_json.get("lernziele", []),
                taxonomiestufe=result_json.get("taxonomiestufe", "Nicht klassifiziert"),
                begründung=result_json.get("begründung", ""),
                kontext_chunks=context_docs,
                raw_output=response.content,
                metadata={
                    "provider": self.provider,
                    "kurs_metadaten": kurs_metadaten,
                    "rag_documents_used": len(context_docs),
                    "model": self.llm.model_name if hasattr(self.llm, 'model_name') else 'unknown'
                }
            )
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON-Parsing-Fehler bei Kompetenzextraktion: {e}")
            return KompetenzResult(
                kompetenzen=[],
                lernziele=[],
                taxonomiestufe="Fehler",
                begründung=f"Parsing-Fehler: {str(e)}",
                kontext_chunks=context_docs,
                raw_output=response.content if response else "",
                metadata={"error": str(e), "provider": self.provider}
            )

    def _build_system_prompt(self, taxonomie_focus: str = None) -> str:
        """Erstellt den System-Prompt für die Kompetenzextraktion"""
        base_prompt = """Du bist ein Experte für kompetenzbasierte Bildung und Curriculumsentwicklung.
Deine Aufgabe ist es, aus Kursinhalten die vermittelten Kompetenzen zu extrahieren und zu strukturieren.

Beachte dabei:
1. Unterscheide zwischen Fachkompetenzen, Methodenkompetenzen, Sozialkompetenzen und Selbstkompetenzen
2. Formuliere konkrete, messbare Lernziele im Format "Die Studierenden können..."
3. Ordne die Kompetenzen nach der Bloom'schen Taxonomie ein:
   - Erinnern/Wissen
   - Verstehen
   - Anwenden
   - Analysieren
   - Evaluieren/Bewerten
   - Erschaffen/Kreieren
4. Nutze den bereitgestellten Kontext aus ähnlichen Kursen zur besseren Einordnung
5. Achte auf realistische und umsetzbare Kompetenzbeschreibungen"""

        if taxonomie_focus:
            base_prompt += f"\n\nFokussiere besonders auf Kompetenzen der Taxonomiestufe: {taxonomie_focus}"

        base_prompt += """\n\nAntworte immer im folgenden JSON-Format:
{
    "kompetenzen": ["Kompetenz 1", "Kompetenz 2", ...],
    "lernziele": ["Die Studierenden können...", ...],
    "taxonomiestufe": "Hauptsächliche Bloom-Taxonomiestufe",
    "begründung": "Kurze Begründung der Kompetenzeinordnung",
    "topic_title": "Passende, prägnante Überschrift, die die Vorlesung in Moodle tragen soll"
}"""

        return base_prompt
    
    def _build_user_prompt(self, content: str, context_docs: List[Dict], kurs_metadaten: Dict) -> str:
        """Baut den User-Prompt mit Kontext auf"""
        prompt_parts = []
        
        # Kurs-Metadaten wenn vorhanden
        if kurs_metadaten:
            meta_str = "\n".join([f"- {k}: {v}" for k, v in kurs_metadaten.items()])
            prompt_parts.append(f"KURS-INFORMATION:\n{meta_str}")
        
        # RAG-Kontext wenn vorhanden
        if context_docs:
            prompt_parts.append("\nKONTEXT AUS ÄHNLICHEN KURSINHALTEN:")
            for i, doc in enumerate(context_docs, 1):
                meta = doc.get("metadata", {})
                content_preview = doc.get("content", "")[:500]
                meta_str = ", ".join([f"{k}: {v}" for k, v in meta.items()])
                prompt_parts.append(f"\n[Dokument {i} - {meta_str}]")
                prompt_parts.append(content_preview + "...")
        
        # Hauptinhalt
        prompt_parts.append(f"\nZU ANALYSIERENDER KURSINHALT:\n{content}")
        
        return "\n".join(prompt_parts)
    
    def classify_course_content(self, content: str) -> Dict[str, Any]:
        """
        NEUE METHODE: Klassifiziert Kursinhalt um passenden Prompt zu wählen.
        
        Args:
            content: Kursinhalt zur Klassifikation
            
        Returns:
            Dict mit Klassifikation (fachbereich, zielgruppe, etc.)
        """
        self.logger.info(" Klassifiziere Kursinhalt...")
        
        # Verwende günstiges LLM für Klassifikation
        classifier_llm = get_llm(model="gpt-4o-mini", temperature=0.1)
        
        classifier_prompt = get_classifier_prompt()
        
        # Begrenze Content für Klassifikation (erste 2000 Zeichen)
        content_sample = content[:2000] + "..." if len(content) > 2000 else content
        
        messages = [
            SystemMessage(content=classifier_prompt),
            HumanMessage(content=f"Klassifiziere folgenden Kursinhalt:\n\n{content_sample}")
        ]
        
        try:
            response = classifier_llm.invoke(messages)
            
            # Bereinige die Antwort von Markdown-Code-Blöcken
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:]  # Entferne ```json
            if content.startswith("```"):
                content = content[3:]   # Entferne ```
            if content.endswith("```"):
                content = content[:-3]  # Entferne ```
            content = content.strip()
            
            # JSON parsen und echte Klassifikation zeigen
            classification = json.loads(content)
            confidence = classification.get('confidence', 0.0)
            
            # Option B: Bei unsicherer Klassifikation → besseres Modell
            if confidence < 0.8:
                self.logger.warning(f" Niedrige Confidence ({confidence}) → Upgrade zu besserem Modell")
                
                # Nutze das Haupt-LLM für bessere Klassifikation
                better_llm = self.llm  # Das ist das teure Modell
                response = better_llm.invoke(messages)
                
                # Nochmal bereinigen
                content = self._clean_json_response(response.content)
                classification = json.loads(content)
                
                new_confidence = classification.get('confidence', 0.0)
                self.logger.info(f" Verbesserte Klassifikation: {classification.get('fachbereich', 'Unbekannt')} (Confidence: {new_confidence:.1f})")
            else:
                # Bereits oben geloggt
                pass
            
            return classification
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Klassifikation-Parsing-Fehler: {e}")
            self.logger.error(f"LLM-Antwort war: '{response.content if 'response' in locals() else 'Keine Antwort'}'")
            
            # Fallback-Klassifikation
            return {
                "fachbereich": "Sonstiges Informatik",
                "zielgruppe": "Bachelor Hauptstudium", 
                "schwerpunkt": "Gemischt",
                "confidence": 0.5,
                "begründung": f"Fallback nach Parsing-Fehler: {str(e)}"
            }
    
    def evaluate_full_document(self, source_file: str, course_id: str, 
                             use_related_context: bool = True) -> KompetenzResult:
        """
        NEUE METHODE: Analysiert ein komplettes Dokument aus ChromaDB.
        
        Args:
            source_file: Dateiname (z.B. "vorlesung1.pdf")
            course_id: Kurs-ID
            use_related_context: Ob verwandte Dokumente als Kontext genutzt werden sollen
            
        Returns:
            KompetenzResult mit Kompetenzextraktion für das gesamte Dokument
        """
        self.logger.info(f" Starte Dokumentanalyse: {source_file}")
        
        # 1. Hole komplettes Dokument ZUERST
        full_content = self.doc_manager.get_full_document(source_file, course_id)
        
        if not full_content.strip():
            return KompetenzResult(
                kompetenzen=[],
                lernziele=[],
                taxonomiestufe="Fehler",
                begründung="Dokument nicht gefunden oder leer",
                kontext_chunks=[],
                raw_output="",
                metadata={"error": "Dokument leer", "source_file": source_file}
            )
        # TODO klassifizierung ewigentlich aus phase 2, aber bissi egal geht so auch, aber unschön für abgabe
        # 2. Klassifiziere den Kursinhalt EINMAL
        classification = self.classify_course_content(full_content)
        fachbereich = classification.get("fachbereich", "Sonstiges Informatik")
        
        if use_related_context:
            # VERBESSERTER Hybrid-Ansatz: Komplettes Dokument + intelligenter Kontext
            
            # 3. Generiere intelligente RAG-Query mit LLM
            smart_query = self._generate_smart_rag_query(full_content, fachbereich)
            
            # 4. Hole verwandte Chunks mit intelligenter Query
            all_related = self.doc_manager.get_related_content(smart_query, course_id, k=10)
            
            # 5. Filtere das aktuelle Dokument aus und nimm beste 5
            related_chunks = [doc for doc in all_related 
                             if doc.metadata.get("source_file") != source_file][:5]
            
            self.logger.debug(f" Smart RAG mit Query: '{smart_query[:100]}...' → {len(related_chunks)} Chunks")
            
            context_docs = []
            for chunk in related_chunks:
                context_docs.append({
                    "content": chunk.page_content,
                    "metadata": chunk.metadata
                })
            
            self.logger.info(f"Hybrid-Modus: {len(full_content)} Zeichen + {len(context_docs)} Kontext-Chunks")
            
        else:
            # Nur das komplette Dokument, keine verwandten Chunks
            context_docs = []
            self.logger.debug(f"Full-Document-Modus: {len(full_content)} Zeichen")
        
        # 2. Wähle spezialisierten Prompt basierend auf Klassifikation
        specialized_prompt = get_specialized_prompt(fachbereich)
        self.logger.info(f" Spezialisierter {fachbereich}-Prompt aktiviert")
        
        # System-Prompt ist jetzt spezialisiert
        system_prompt = specialized_prompt
        
        # User-Prompt für komplettes Dokument
        user_prompt = self._build_full_document_prompt(
            full_content, context_docs, source_file, course_id
        )
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        # Berechne tatsächliche Prompt-Größe
        total_prompt_length = len(system_prompt) + len(user_prompt)
        self.logger.info(f" Sende Dokumentanalyse an LLM (System: {len(system_prompt):,} + User: {len(user_prompt):,} = {total_prompt_length:,} Zeichen)...")
        try:
            response = self.llm.invoke(messages)
            
            # WICHTIG: Logge die RAW Response für Debugging
            self.logger.debug(f" LLM Response erhalten ({len(response.content) if response and response.content else 0} Zeichen)")
            if response and response.content:
                # Zeige KOMPLETTE Response auf INFO-Level für Debugging
                self.logger.debug(f" KOMPLETTE RAW Response:\n{response.content}")
            
            # DEBUG: Prüfe ob Claude überhaupt antwortet
            if not response or not response.content:
                self.logger.error("ANTWORT LEER!")
                return KompetenzResult(
                    kompetenzen=[],
                    lernziele=[],
                    taxonomiestufe="Fehler",
                    begründung="keine Antwort",
                    kontext_chunks=context_docs,
                    raw_output="",
                    metadata={"error": "Empty response", "source_file": source_file}
                )
            
            if len(response.content.strip()) == 0:
                self.logger.error("ANTWORT NUR WHITESPACE!")
                return KompetenzResult(
                    kompetenzen=[],
                    lernziele=[],
                    taxonomiestufe="Fehler", 
                    begründung="nur Whitespace zurück",
                    kontext_chunks=context_docs,
                    raw_output=response.content,
                    metadata={"error": "Whitespace only", "source_file": source_file}
                )
            
            # RAW Response nur bei Debug-Level
            self.logger.debug(f" RAW Response ({len(response.content)} Zeichen): {response.content[:200]}...")
            
            # Bereinige die Antwort von Markdown-Code-Blöcken
            cleaned_content = self._clean_json_response(response.content)
            
            # Logge die KOMPLETTE bereinigte JSON für Debugging
            self.logger.debug(f" KOMPLETTER bereinigter JSON ({len(cleaned_content)} Zeichen):\n{cleaned_content}")
            
            result_json = json.loads(cleaned_content)
            
            # Logge ob topic_title vorhanden ist
            if 'topic_title' in result_json:
                self.logger.info(f" Topic-Titel extrahiert: '{result_json['topic_title']}'")
            else:
                self.logger.warning(f"KEIN topic_title im JSON gefunden! Keys: {list(result_json.keys())}")
            
            # Sammle alle Kompetenzen aus verschiedenen Kategorien
            all_kompetenzen = []
            
            # Standard-Format (alte Prompts)
            if "kompetenzen" in result_json:
                all_kompetenzen.extend(result_json["kompetenzen"])
            
            # Spezialisierte IT-Prompts Format
            for key in ["fachkompetenzen", "methodenkompetenzen", "toolkompetenzen", "problemloesungskompetenzen"]:
                if key in result_json:
                    all_kompetenzen.extend(result_json[key])
            
            # Weitere mögliche Kategorien (für andere Fachbereiche)
            for key in ["programmiersprache", "konzepte", "development_skills", "software_engineering"]:
                if key in result_json:
                    all_kompetenzen.extend(result_json[key])
            
            result = KompetenzResult(
                kompetenzen=all_kompetenzen,
                lernziele=result_json.get("lernziele", []),
                taxonomiestufe=result_json.get("taxonomiestufe", "Nicht klassifiziert"),
                begründung=result_json.get("begründung", ""),
                kontext_chunks=context_docs,
                raw_output=response.content,
                filename=source_file,  # Für Summary
                topic_title=result_json.get("topic_title", "Kein Titel extrahiert"),  # NEU: Topic-Titel mit klarem Fallback
                metadata={
                    "provider": self.provider,
                    "source_file": source_file,
                    "course_id": course_id,
                    "analysis_mode": "full_document_hybrid" if use_related_context else "full_document_only",
                    "document_length": len(full_content),
                    "context_chunks_used": len(context_docs),
                    "fachbereich": fachbereich,
                    "course_classification": classification,
                    "kompetenz_kategorien": {k: v for k, v in result_json.items() if "kompetenz" in k.lower() or k in ["programmiersprache", "konzepte", "development_skills", "software_engineering"]}
                }
            )
            
            #  Erfolgreiche Analyse - zeige echte Daten
            self.logger.info(f" {result.get_summary()}")
            print(f"\n EXTRAHIERTE KOMPETENZEN ({source_file}):")
            for i, komp in enumerate(all_kompetenzen[:10], 1):
                print(f"   {i}. {komp}")
            if len(all_kompetenzen) > 10:
                print(f"   ... und {len(all_kompetenzen) - 10} weitere")
            
            if result_json.get("lernziele"):
                print(f"\n LERNZIELE:")
                for i, ziel in enumerate(result_json["lernziele"][:5], 1):
                    print(f"   {i}. {ziel}")
            
            print(f"\n Taxonomie: {result_json.get('taxonomiestufe', 'N/A')}")
            print("-" * 60)
            
            return result
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON-Parsing-Fehler bei Full-Document-Analyse: {e}")
            # IMMER die KOMPLETTE Response zeigen bei JSON-Fehler!
            if response and response.content:
                self.logger.error(f" Fehlerhafte Response ({len(response.content)} Zeichen)")
                print(f"\nJSON-FEHLER - KOMPLETTE Claude Response:")
                print("=" * 80)
                print(response.content)  # Zeige ALLES
                print("=" * 80)
                print(f"\nFehler war: {e}")
            return KompetenzResult(
                kompetenzen=[],
                lernziele=[],
                taxonomiestufe="Fehler",
                begründung=f"Parsing-Fehler: {str(e)}",
                kontext_chunks=context_docs,
                raw_output=response.content if response else "",
                metadata={"error": str(e), "source_file": source_file}
            )
    
    def _build_full_document_prompt(self, full_content: str, context_docs: List[Dict], 
                                  source_file: str, course_id: str) -> str:
        """Baut User-Prompt für komplette Dokumentenanalyse"""
        prompt_parts = [
            f"KURS-ID: {course_id}",
            f"DOKUMENT: {source_file}",
            f"ANALYSE-MODUS: Komplette Dokumentenanalyse"
        ]
        
        # VERBESSERTE Kontext-Dokumente wenn vorhanden
        if context_docs:
            prompt_parts.append(f"\nVERWANDTE INHALTE (durch intelligente RAG-Suche gefunden, {len(context_docs)} Chunks):")
            for i, doc in enumerate(context_docs[:3], 1):  # Max 3 für Prompt-Länge
                meta = doc.get("metadata", {})
                # Mehr Content zeigen (750 statt 300 Zeichen) da es gezielter ist
                content_preview = doc.get("content", "")[:750]
                source = meta.get("source_file", "Unbekannt")
                chunk_id = meta.get("chunk_id", "?")
                prompt_parts.append(f"\n[Verwandtes Dokument {i}: {source} (Chunk {chunk_id})]")
                prompt_parts.append(content_preview + "...")
        
        # Das komplette Dokument
        prompt_parts.append(f"\nKOMPLETTES ZU ANALYSIERENDES DOKUMENT:\n{full_content}")
        
        prompt_parts.append("""
        
AUFGABE: Analysiere das komplette Dokument und extrahiere ALLE vermittelten Kompetenzen.
Da du das gesamte Dokument siehst, erstelle eine umfassende Kompetenzübersicht.
Nutze die verwandten Inhalte nur als Kontext für bessere Einordnung.""")
        
        return "\n".join(prompt_parts)
    
    def consolidate_document_competencies(self, kompetenzen: List[str], source_file: str) -> List[str]:
        """
        NEUE METHODE: Konsolidiert die Kompetenzen eines einzelnen Dokuments.
        Reduziert z.B. 10 extrahierte Kompetenzen auf 2-5 Kernkompetenzen.
        
        Args:
            kompetenzen: Liste der extrahierten Kompetenzen aus dem Dokument
            source_file: Dateiname für Kontext
            
        Returns:
            Liste von 2-5 konsolidierten Kernkompetenzen
        """
        if len(kompetenzen) <= 3:
            # Bereits wenige Kompetenzen, keine weitere Konsolidierung nötig
            return kompetenzen
            
        self.logger.info(f" Konsolidiere {len(kompetenzen)} Kompetenzen für {source_file}")
        
        # Verwende günstiges Modell für Konsolidierung
        consolidation_llm = get_llm(model="gpt-4o-mini", temperature=0.1)
        
        system_prompt = """Du bist ein Experte für Curriculumsentwicklung und Kompetenzmodellierung.

Deine Aufgabe: Konsolidiere die gegebenen Kompetenzen eines einzelnen Vorlesungsdokuments 
zu 2-5 KERNKOMPETENZEN, die das Wesentliche der Vorlesung erfassen.

REGELN:
1. Fasse ähnliche/überlappende Kompetenzen zusammen
2. Erstelle 2-5 prägnante Kernkompetenzen (nicht mehr!)
3. Formuliere KONKRET und MESSBAR
4. Behalte den spezifischen Fokus des Dokuments
5. Vermeide zu generische Aussagen

WICHTIG ZUR FORMULIERUNG:
- Kompetenzen sind das, was VERMITTELT wird, nicht was Studierende TUN
- Nutze Substantive statt Verben: "Nutzung von...", "Anwendung von...", "Einsatz von..."
- NICHT: "Implementiert Arrays" (das tut der Student)
- SONDERN: "Nutzung von Arrays in Java" (das wird vermittelt)

BEISPIELE:
Input: ["Arrays erstellen", "Arrays durchlaufen", "Arrays sortieren", "Mehrdimensionale Arrays", "Array-Länge bestimmen"]
Output: ["Nutzung von ein- und mehrdimensionalen Arrays in Java", "Anwendung von Array-Operationen für Datenverarbeitung"]

Input: ["Klassen definieren", "Objekte erstellen", "Konstruktoren schreiben", "Vererbung implementieren"]
Output: ["Grundlagen der objektorientierten Programmierung in Java", "Einsatz von Vererbung und Kapselung"]

Antworte NUR mit einem JSON-Array der konsolidierten Kompetenzen."""

        user_prompt = f"""Dokument: {source_file}

Extrahierte Kompetenzen:
{chr(10).join(f"- {k}" for k in kompetenzen)}

Konsolidiere diese zu 2-5 Kernkompetenzen, die das Wesentliche dieses Dokuments erfassen."""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = consolidation_llm.invoke(messages)
            cleaned = self._clean_json_response(response.content)
            consolidated = json.loads(cleaned)
            
            if isinstance(consolidated, list) and 2 <= len(consolidated) <= 5:
                self.logger.info(f" Konsolidiert zu {len(consolidated)} Kernkompetenzen")
                # Zeige die konsolidierten Kompetenzen auch in print, nicht nur im logger
                for i, komp in enumerate(consolidated, 1):
                    print(f"      {i}. {komp}")
                    self.logger.debug(f"   {i}. {komp}")
                return consolidated
            else:
                self.logger.warning(f"Unerwartetes Konsolidierungsergebnis, verwende Original")
                return kompetenzen[:5]  # Fallback: erste 5
                
        except Exception as e:
            self.logger.error(f"Konsolidierung fehlgeschlagen: {e}")
            return kompetenzen[:5]  # Fallback
    
    def save_competencies_to_neo4j(self, kompetenzen: List[str], source_file: str, course_id: str) -> Dict[str, str]:
        """
        NEUE METHODE: Speichert Kompetenzen direkt als Neo4j Nodes und verknüpft mit Document.
        Wird in Phase 3 nach der Konsolidierung aufgerufen.
        
        Args:
            kompetenzen: Liste der konsolidierten Kompetenzen
            source_file: Dateiname des Dokuments
            course_id: Kurs-ID
            
        Returns:
            Dict mapping competency_name -> node_id
        """
        from llm.graph.neo4j_client import GraphDatabase
        
        db = GraphDatabase()
        # Nutze die gespeicherte GraphIngestion Instanz für Cache-Wiederverwendung!
        graph = self.graph_ingestion
        competency_ids = {}
        
        self.logger.info(f" Speichere {len(kompetenzen)} Kompetenzen in Neo4j für {source_file}")
        
        # Tracking für neue vs. wiederverwendete Kompetenzen
        new_count = 0
        reused_count = 0
        
        for competency_name in kompetenzen:
            # Generiere eindeutige ID
            import re
            comp_id = f"comp_{competency_name[:50].lower().replace(' ', '_')}"
            comp_id = re.sub(r'[^a-z0-9_]', '', comp_id)
            
            # Bestimme Bloom Level basierend auf Formulierung
            bloom_level = "apply"  # Default
            if any(word in competency_name.lower() for word in ["grundlagen", "einführung", "überblick"]):
                bloom_level = "understand"
            elif any(word in competency_name.lower() for word in ["nutzung", "anwendung", "einsatz"]):
                bloom_level = "apply"
            elif any(word in competency_name.lower() for word in ["analyse", "bewertung", "vergleich"]):
                bloom_level = "analyze"
            elif any(word in competency_name.lower() for word in ["entwicklung", "design", "konzeption"]):
                bloom_level = "create"
            
            try:
                self.logger.debug(f"  Verarbeite Kompetenz: {competency_name}")
                
                # Nutze GraphIngestion für Embedding-basierte Deduplikation
                comp, reused = graph.create_or_get_similar_competency(
                    name=competency_name,
                    description=f"Kernkompetenz aus {source_file}",
                    level="intermediate",
                    keywords=[course_id],
                    similarity_threshold=0.75  # Reduziert von 0.85 für bessere Duplikat-Erkennung
                )
                
                # Zähle neue vs. wiederverwendete
                if reused:
                    reused_count += 1
                else:
                    new_count += 1
                    
            except Exception as e:
                self.logger.error(f" Fehler bei Kompetenz-Erstellung: {e}")
                self.logger.error(f"   Kompetenz: {competency_name}")
                import traceback
                self.logger.error(traceback.format_exc())
                continue
            
            # Setze Bloom Level
            comp.bloom_level = bloom_level
            comp.save()
            
            if reused:
                self.logger.debug(f"   Wiederverwendet: {competency_name}")
            else:
                self.logger.debug(f"   Neu erstellt: {competency_name}")
            
            competency_ids[competency_name] = comp.name
            
            # Verknüpfe Document mit Competency
            create_teaches_query = """
            MATCH (d:Document)
            WHERE d.file_path CONTAINS $filename
            MATCH (c:Competency {name: $comp_name})
            MERGE (d)-[r:TEACHES]->(c)
            ON CREATE SET 
                r.confidence = 0.9,
                r.created_at = datetime()
            RETURN d.doc_id as doc_id
            """
            
            db.execute_query(create_teaches_query, {
                "filename": source_file,
                "comp_name": competency_name
            })
        
        # Bessere Ausgabe mit Details
        if reused_count > 0:
            self.logger.info(f" {new_count} neue, {reused_count} wiederverwendete Kompetenzen für {source_file}")
        else:
            self.logger.info(f" {new_count} neue Kompetenzen erstellt für {source_file}")
        return competency_ids
    
    def save_lernziele_to_neo4j(self, lernziele: List[str], source_file: str, course_id: str) -> List[str]:
        """
        Speichert Lernziele in Neo4j.
        
        Args:
            lernziele: Liste von Lernziel-Beschreibungen
            source_file: Name der Quelldatei (z.B. "gdp01.pdf")
            course_id: Kurs-ID
            
        Returns:
            Liste der erstellten Lernziel-IDs
        """
        from llm.graph.models import LearningOutcome
        
        created_ids = []
        self.logger.info(f" Speichere {len(lernziele)} Lernziele für {source_file}")
        
        for i, lernziel in enumerate(lernziele, 1):
            try:
                # Erstelle eindeutige ID basierend auf Dokument und Index
                outcome_id = f"{course_id}_{source_file}_{i}".replace('.', '_')
                
                # Erstelle oder aktualisiere LearningOutcome
                outcome = LearningOutcome.nodes.get_or_none(outcome_id=outcome_id)
                if not outcome:
                    outcome = LearningOutcome(
                        outcome_id=outcome_id,
                        description=lernziel,
                        document_name=source_file,
                        course_id=course_id
                    ).save()
                    self.logger.debug(f"  Lernziel erstellt: {outcome_id}")
                else:
                    # Update falls bereits vorhanden
                    outcome.description = lernziel
                    outcome.save()
                    self.logger.debug(f"  Lernziel aktualisiert: {outcome_id}")
                
                created_ids.append(outcome_id)
                
            except Exception as e:
                self.logger.error(f" Fehler bei Lernziel-Speicherung: {e}")
                self.logger.error(f"   Lernziel: {lernziel[:100]}...")
                continue
        
        self.logger.info(f" {len(created_ids)} Lernziele in Neo4j gespeichert")
        return created_ids
    
    def save_topic_title_to_neo4j(self, topic_title: str, source_file: str, course_id: str) -> bool:
        """
        Speichert den Topic-Titel für ein Dokument in Neo4j.
        
        Args:
            topic_title: Der extrahierte Topic-Titel
            source_file: Name der Quelldatei (z.B. "gdp01.pdf")
            course_id: Kurs-ID
            
        Returns:
            True bei Erfolg
        """
        from llm.graph.models import Document
        
        if not topic_title or topic_title == "Kein Titel extrahiert":
            self.logger.debug(f" Kein gültiger Topic-Titel für {source_file}")
            return False
        
        try:
            # Finde das Document in Neo4j
            # Documents haben jetzt title mit vollständigem Dateinamen inkl. Erweiterung
            doc = Document.nodes.get_or_none(
                title=source_file,  # z.B. gdp01.pdf
                lecture_name=course_id.upper()
            )
            
            if doc:
                doc.topic_title = topic_title
                doc.save()
                self.logger.info(f" Topic-Titel gespeichert: '{topic_title}' für {source_file}")
                return True
            else:
                self.logger.warning(f" Document {source_file} nicht in Neo4j gefunden")
                return False
                
        except Exception as e:
            self.logger.error(f" Fehler beim Speichern des Topic-Titels: {e}")
            return False