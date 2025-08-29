# llm/evaluate/aggregate_evaluator.py

from typing import Any, Dict, List, Union
from langchain_core.messages import HumanMessage, SystemMessage
from llm.evaluate.base import BaseEvaluator, AggregatedResult, KompetenzResult
from llm.evaluate.factory import register_evaluator
from llm.shared.llm_factory import get_llm
from llm.shared.json_utils import clean_json_response, parse_llm_json
import json


@register_evaluator("aggregate")
class AggregateEvaluator(BaseEvaluator):
    """
    Evaluator für die Aggregation und Konsolidierung von Kompetenzen.
    Fasst mehrere Kompetenz-Extraktionen zu einem kohärenten Gesamtbild zusammen.
    """
    
    def __init__(self, model: str, use_rag: bool = True, **kwargs):
        from llm.shared.llm_factory import MODEL_TO_PROVIDER
        provider = MODEL_TO_PROVIDER.get(model, "openai")
        super().__init__(provider, use_rag)
        
        # Hauptmodell für komplexe Aggregation
        self.llm = get_llm(
            model=model,
            temperature=kwargs.get("temperature", 0.2)  # Etwas höher für Kreativität
        )
        
        # Günstiges Modell für RAG-Query-Generierung (falls RAG aktiviert)
        if use_rag:
            self.rag_llm = get_llm(
                model="gpt-4o-mini",
                temperature=0.1
            )
        
        self.logger.info(f"AggregateEvaluator mit {model} initialisiert, RAG: {use_rag}")
    
    def _clean_json_response(self, response_content: str) -> str:
        """
        Bereinigt LLM-Antworten von Markdown-Code-Blöcken für JSON-Parsing.
        Nutzt die zentrale json_utils Funktion.
        
        Args:
            response_content: Rohe LLM-Antwort
            
        Returns:
            Bereinigter JSON-String
        """
        return clean_json_response(response_content, provider=self.provider)
    
    def _generate_competency_rag_query(self, competency: str, context: Dict = None) -> str:
        """
        Generiert intelligente RAG-Query für eine spezifische Kompetenz zur Detail-Anreicherung.
        
        Args:
            competency: Basis-Kompetenz (z.B. "Java-Programmierung")
            context: Zusätzlicher Kontext (Kursname, Fachbereich, etc.)
            
        Returns:
            Optimierte RAG-Query für diese Kompetenz
        """
        if not self.use_rag:
            return ""
            
        # Kontext-Informationen sammeln
        course_context = ""
        if context:
            course_name = context.get("kurs_name", "")
            fachbereich = context.get("fachbereich", "")
            if course_name:
                course_context += f"Kurs: {course_name}. "
            if fachbereich:
                course_context += f"Fachbereich: {fachbereich}. "
        
        system_prompt = f"""Du bist ein Experte für Curriculumsentwicklung und Informationssuche.

Erstelle eine optimierte Suchquery um detaillierte Informationen, konkrete Beispiele und praktische Inhalte zu einer Kompetenz zu finden.

{course_context}

Fokussiere auf:
- Konkrete Implementierungen und Code-Beispiele
- Praktische Übungen und Anwendungen  
- Spezifische Tools, Befehle oder Methoden
- Lernmaterialien und Erklärungen
- Detaillierte Unterthemen

Antworte im JSON-Format:
{{
    "keywords": ["Begriff1", "Begriff2", "Begriff3", ...],
    "query": "Optimierte Suchquery für Details zu dieser Kompetenz"
}}"""

        user_prompt = f"Generiere eine detaillierte Suchquery für die Kompetenz: '{competency}'"
        
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = self.rag_llm.invoke(messages)
            
            # JSON bereinigen und parsen
            cleaned_content = self._clean_json_response(response.content)
            result = json.loads(cleaned_content)
            
            keywords = result.get("keywords", [])
            smart_query = result.get("query", "")
            
            self.logger.debug(f" RAG-Query für '{competency}': '{smart_query}'")
            
            # Fallback falls LLM keine Query liefert
            if not smart_query:
                smart_query = f"{competency} Beispiele Details Implementierung Übungen"
            
            return smart_query
            
        except Exception as e:
            self.logger.warning(f" RAG-Query-Generierung für '{competency}' fehlgeschlagen: {e}")
            # Fallback
            return f"{competency} konkrete Beispiele praktische Anwendung"
    
    def _analyze_document_relationships(self, kompetenz_results: List[KompetenzResult]) -> Dict[str, Any]:
        """
        Analysiert Beziehungen zwischen Dokumenten basierend auf Inhalt + extrahierten Kompetenzen.
        Nutzt Cluster-basierte Analyse für bessere Performance (vermeidet n² Komplexität).
        """
        self.logger.info(f" Starte Cluster-basierte Beziehungsanalyse für {len(kompetenz_results)} Dokumente")
        
        relationships = []
        learning_paths = []
        
        # 1. ZUERST: Themen-Cluster identifizieren
        clusters = self._identify_theme_clusters(kompetenz_results)
        self.logger.info(f" {len(clusters)} Themen-Cluster identifiziert")
        
        # Debug: Zeige die erstellten Cluster
        for theme, docs in clusters.items():
            self.logger.info(f"    Cluster '{theme}': {len(docs)} Dokumente - {', '.join(docs[:3])}{'...' if len(docs) > 3 else ''}")
        
        # 2. OPTIMIERT: Cluster-basierte Analyse statt n²
        use_cluster_optimization = len(kompetenz_results) > 5  # Ab 6 Dokumenten lohnt sich Optimierung
        
        if use_cluster_optimization and len(clusters) > 1:
            # Nutze Cluster-Optimierung
            from llm.evaluate.cluster_relationship_analyzer import ClusterRelationshipAnalyzer
            
            analyzer = ClusterRelationshipAnalyzer(
                compare_func=self._compare_documents_with_rag,
                rag_func=self.get_rag_context if self.use_rag else None
            )
            # Replace the analyzer's logger with ours to ensure output visibility
            analyzer.logger = self.logger
            
            analysis_result = analyzer.analyze_with_clusters(kompetenz_results, clusters)
            relationships = analysis_result["relationships"]
            
            self.logger.info(f" Cluster-Optimierung: {analysis_result['statistics']['complexity_reduction']} Reduktion")
        else:
            # Fallback: Normale n² Analyse für kleine Dokument-Sets
            self.logger.info(f" Verwende Standard-Analyse (wenige Dokumente oder nur 1 Cluster)")
            
            total_comparisons = len(kompetenz_results) * (len(kompetenz_results) - 1) // 2
            comparison_count = 0
            
            for i, result1 in enumerate(kompetenz_results):
                for j, result2 in enumerate(kompetenz_results[i + 1:], i + 1):
                    comparison_count += 1
                    self.logger.info(f" Vergleich {comparison_count}/{total_comparisons}: {result1.filename} <-> {result2.filename}")
                    
                    relationship = self._compare_documents_with_rag(result1, result2)
                    if relationship:
                        relationships.append(relationship)
                        self.logger.info(f" Beziehung gefunden: {relationship.get('type', 'unknown')} (Stärke: {relationship.get('strength', 0):.2f})")
        
        # 3. Taxonomie-basierte Progression finden
        progression = self._find_taxonomic_progression(kompetenz_results)
        
        # 4. Lernpfade generieren
        learning_paths = self._generate_learning_paths(kompetenz_results, relationships)
        
        # 5. NEUE FUNKTIONALITÄT: Beziehungen und Cluster in Neo4j speichern
        self._save_relationships_to_neo4j(relationships, clusters, kompetenz_results)
        
        result = {
            "relationships": relationships,
            "taxonomic_progression": progression,
            "theme_clusters": clusters,
            "learning_paths": learning_paths,
            "statistics": {
                "total_relationships": len(relationships),
                "prerequisite_count": len([r for r in relationships if r.get("type") == "prerequisite"]),
                "builds_upon_count": len([r for r in relationships if r.get("type") == "builds_upon"]),
                "theme_count": len(clusters)
            }
        }
        
        # Output für Debugging
        self.logger.info(f" BEZIEHUNGSANALYSE ERGEBNISSE:")
        self.logger.info(f"   Beziehungen: {len(relationships)}")
        self.logger.info(f"   Themenbereiche: {len(clusters)}")
        self.logger.info(f"   Lernpfade: {len(learning_paths)}")
        
        return result
    
    def _compare_documents_with_rag(self, result1: KompetenzResult, result2: KompetenzResult) -> Dict[str, Any]:
        """
        Vergleicht zwei Dokumente mit RAG-Anreicherung für tiefere Analyse.
        """
        # RAG: Hole verwandte Inhalte für beide Dokumente
        # Bessere Query: Fokus auf Konzepte, Code-Beispiele und Definitionen
        query1 = f"Hauptkonzepte Code-Beispiele Definitionen {' '.join(result1.kompetenzen[:3])} {result1.filename}"
        query2 = f"Hauptkonzepte Code-Beispiele Definitionen {' '.join(result2.kompetenzen[:3])} {result2.filename}"
        
        # Mehr Chunks für besseren Kontext (5 statt 3)
        rag_context1 = self.get_rag_context(query1, k=5) if self.use_rag else []
        rag_context2 = self.get_rag_context(query2, k=5) if self.use_rag else []
        
        # LLM-Prompt mit RAG-Anreicherung
        prompt = f"""Analysiere die Beziehung zwischen diesen Programmierkurs-Dokumenten:

 DOKUMENT 1: {result1.filename}
 Kompetenzen: {', '.join(result1.kompetenzen[:5])}
 Taxonomie: {result1.taxonomiestufe}
 Lernziele: {', '.join(result1.lernziele[:3]) if result1.lernziele else 'Keine'}

 DOKUMENT 2: {result2.filename}
 Kompetenzen: {', '.join(result2.kompetenzen[:5])}
 Taxonomie: {result2.taxonomiestufe}
 Lernziele: {', '.join(result2.lernziele[:3]) if result2.lernziele else 'Keine'}

KONTEXT aus Dokumentinhalten:
"""
        
        # RAG-Context hinzufügen - ALLE Chunks nutzen, nicht nur den ersten!
        if rag_context1:
            prompt += f"\n\n INHALT AUS {result1.filename}:"
            for i, chunk in enumerate(rag_context1[:3], 1):  # Top 3 Chunks
                content = chunk.get('content', '')[:800]  # 800 Zeichen pro Chunk
                prompt += f"\n[Ausschnitt {i}]: {content}..."
                
        if rag_context2:
            prompt += f"\n\n INHALT AUS {result2.filename}:"
            for i, chunk in enumerate(rag_context2[:3], 1):  # Top 3 Chunks  
                content = chunk.get('content', '')[:800]  # 800 Zeichen pro Chunk
                prompt += f"\n[Ausschnitt {i}]: {content}..."
            
        prompt += """

BESTIMME DIE BEZIEHUNG - WÄHLE GENAU EINEN TYP:

1. **PREREQUISITE**: Dok1 ist ZWINGEND notwendig - ohne dieses Wissen ist Dok2 nicht verstehbar
   - Test: Kann ein Student Dok2 verstehen OHNE Dok1? Wenn NEIN → PREREQUISITE
   - Beispiel: "Variablen" → "Arrays" (Arrays = mehrere Variablen)
   - Beispiel: "Klassen" → "Interfaces" (Interface ohne Klassen-Konzept unmöglich)
   - NICHT: "Arrays" → "Listen" (beide unabhängig lernbar = RELATED)

2. **SEQUENCE**: UNMITTELBARE Fortsetzung - wie Buchkapitel oder Seitenzahlen
   - Test: Ist es GENAU dasselbe Thema nur aufgeteilt?
   - Beispiel: "OOP Folie 1-30" → "OOP Folie 31-60"
   - Beispiel: "Rekursion Teil 1/3" → "Rekursion Teil 2/3"
   - NICHT: "Grundlagen" → "Fortgeschritten" (das ist BUILDS_UPON)
   - NICHT: "Woche 1" → "Woche 2" mit unterschiedlichen Themen

3. **BUILDS_UPON**: Dok2 baut DIREKT auf dem spezifischen Wissen von Dok1 auf
   - Muss dasselbe Kernkonzept erweitern/vertiefen
   - Beispiel: "Listen-Grundlagen" → "Listen-Sortierung"
   - Beispiel: "Klassen-Definition" → "Vererbung"
   - Beispiel: "SQL-SELECT" → "SQL-JOINs"
   - NICHT: "Arrays" → "OOP" (Paradigmenwechsel = RELATED)
   - NICHT: "Variablen" → "Datenbanken" (zu großer Sprung = RELATED/INDEPENDENT)

4. **RELATED**: Verwandte Konzepte OHNE direkte Abhängigkeit
   - Gleiche Kategorie/Domäne aber parallel lernbar
   - Beispiel: "Arrays" ↔ "ArrayList" (verschiedene Datenstrukturen)
   - Beispiel: "TCP" ↔ "UDP" (verschiedene Protokolle)
   - Beispiel: "Prozedurale Prog." ↔ "OOP" (verschiedene Paradigmen)
   - Arrays → OOP gehört HIERHER (nicht BUILDS_UPON)!

5. **INDEPENDENT**: Keine relevante Beziehung
   - Beispiel: "Java Basics" ↔ "Git/Versionsverwaltung" (völlig verschiedene Bereiche)
   - Beispiel: "Hardware" ↔ "Webdesign" (unterschiedliche Domänen)

ENTSCHEIDUNGSHILFE - Frage dich der Reihe nach:

1️ 1. Ist es EXAKT dasselbe Thema nur zeitlich/räumlich aufgeteilt? → SEQUENCE
   (wie Seiten eines Buches, Teile einer Vorlesung)

2️ 2. Kann man Dok2 ÜBERHAUPT NICHT verstehen ohne Dok1? → PREREQUISITE
   (Direkte, unmittelbare Abhängigkeit - nicht "alles baut auf Variablen auf")

3️ 3. Erweitert Dok2 GENAU DAS KONZEPT aus Dok1 weiter? → BUILDS_UPON
   (Dasselbe Thema wird vertieft, nicht nur "irgendwie verwandt")

4️ 4. Gehören beide zur selben Themenkategorie? → RELATED
   (Können parallel gelernt werden, ergänzen sich)

5️ 5. Haben sie fachlich nichts miteinander zu tun? → INDEPENDENT

 WICHTIG: "Alles baut irgendwie auf Grundlagen auf" zählt NICHT!
Nur DIREKTE, UNMITTELBARE Abhängigkeiten zählen für PREREQUISITE/BUILDS_UPON.

Beispiel-Kette:
- "Variablen" → "Arrays" = PREREQUISITE (direkt nötig)
- "Variablen" → "Datenbanken" = INDEPENDENT (zu indirekt)
- "Arrays" → "OOP" = RELATED (verschiedene Konzepte)
- "Arrays" → "Sortieralgorithmen für Arrays" = BUILDS_UPON (gleiches Konzept vertieft)

Bei Zweifeln: Wähle die SCHWÄCHERE Beziehung!
BUILDS_UPON nur wenn WIRKLICH dasselbe Konzept erweitert wird.
PREREQUISITE nur wenn UNMITTELBAR notwendig.

Antwort als JSON:
{{
    "type": "PREREQUISITE|SEQUENCE|BUILDS_UPON|RELATED|INDEPENDENT",
    "strength": 0.0-1.0,
    "reason": "Detaillierte Begründung basierend auf Inhalten",
    "examples": ["Konkrete Beispiele aus den Dokumenten"]
}}

Nur bei klaren Beziehungen antworten (strength > 0.6)! 
WICHTIG: Wähle GENAU EINEN Typ - keine Kombination!"""
        
        try:
            messages = [
                SystemMessage(content="Du bist Experte für Curriculum-Design und Lernpfad-Analyse."),
                HumanMessage(content=prompt)
            ]
            
            response = self.llm.invoke(messages)
            cleaned = self._clean_json_response(response.content)
            relationship = json.loads(cleaned)
            
            # Filter für bessere Beziehungsqualität
            strength = relationship.get("strength", 0)
            rel_type = relationship.get("type", "")
            
            # Striktere Kriterien je nach Typ
            if rel_type == "BUILDS_UPON":
                # BUILDS_UPON nur bei sehr starker Verbindung (>0.75)
                # und nur wenn Dokumente nah beieinander (sequenziell)
                doc1_num = int(''.join(filter(str.isdigit, result1.filename)) or 0)
                doc2_num = int(''.join(filter(str.isdigit, result2.filename)) or 0)
                
                # Nur direkte Nachfolger oder max 2 Abstand
                if abs(doc1_num - doc2_num) > 2:
                    return None
                    
                if strength > 0.75:
                    return {
                        "doc1": result1.filename,
                        "doc2": result2.filename,
                        **relationship
                    }
            
            elif rel_type == "PREREQUISITE":
                # PREREQUISITE braucht hohe Confidence
                if strength > 0.7:
                    return {
                        "doc1": result1.filename,
                        "doc2": result2.filename,
                        **relationship
                    }
            
            elif rel_type == "RELATED":
                # RELATED ok bei mittlerer Stärke
                if strength > 0.65:
                    return {
                        "doc1": result1.filename,
                        "doc2": result2.filename,
                        **relationship
                    }
            
            elif rel_type == "INDEPENDENT":
                # INDEPENDENT nicht speichern - keine Kante ist aussagekräftig genug
                return None
            
            # Default: keine Beziehung speichern
            return None
                
        except Exception as e:
            self.logger.debug(f"Beziehungsanalyse {result1.filename}<->{result2.filename} fehlgeschlagen: {e}")
        
        return None
    
    def _find_taxonomic_progression(self, kompetenz_results: List[KompetenzResult]) -> List[str]:
        """
        Findet taxonomische Progression: Verstehen → Anwenden → Evaluieren
        """
        taxonomy_order = ["Erinnern", "Verstehen", "Anwenden", "Analysieren", "Evaluieren", "Erschaffen"]
        
        # Gruppiere nach Taxonomiestufe
        by_taxonomy = {}
        for result in kompetenz_results:
            tax = result.taxonomiestufe
            if tax not in by_taxonomy:
                by_taxonomy[tax] = []
            by_taxonomy[tax].append(result.filename)
        
        # Sortiere nach Taxonomie-Reihenfolge
        progression = []
        for tax_level in taxonomy_order:
            if tax_level in by_taxonomy:
                progression.extend(by_taxonomy[tax_level])
        
        return progression
    
    def _identify_theme_clusters(self, kompetenz_results: List[KompetenzResult]) -> Dict[str, List[str]]:
        """
        Identifiziert Themenbereiche mit LLM-basierter Analyse.
        """
        # Bereite Dokument-Daten für LLM auf
        documents_summary = []
        for result in kompetenz_results:
            doc_info = f"Datei: {result.filename}\nKompetenzen: {', '.join(result.kompetenzen[:8])}\nTaxonomie: {result.taxonomiestufe}"
            documents_summary.append(doc_info)
        
        prompt = f"""Analysiere diese Programmierkurs-Dokumente und gruppiere sie in 3-4 sinnvolle Themenbereiche:

{'\n\n'.join(documents_summary)}

ZIEL: Erstelle 3-4 ausgewogene thematische Cluster für einen typischen Programmierkurs.

WICHTIGE REGELN:
1. Erstelle GENAU 3-4 Cluster (nicht mehr, nicht weniger)
2. Jeder Cluster MUSS mindestens 2 Dokumente enthalten
3. Verteile die Dokumente möglichst gleichmäßig auf die Cluster
4. Gruppiere nach HAUPTTHEMEN, nicht nach Details

VORSCHLAG für typische Programmierkurs-Cluster:
- "Grundlagen und Einführung": Programmierkonzepte, Algorithmen, erste Schritte
- "Datentypen und Strukturen": Variablen, Strings, Arrays, primitive/komplexe Typen  
- "Kontrollfluss und Methoden": Schleifen, Verzweigungen, Funktionen/Methoden
- "Objektorientierung": Klassen, Objekte, Vererbung, Kapselung

ANALYSIERE die Kompetenzen und ordne jedes Dokument EINEM der Cluster zu.
Bei Dokumenten die mehrere Themen abdecken: Wähle das DOMINANTE Thema.

Beispiel für gdp01-gdp10:
- gdp01 könnte zu "Grundlagen" gehören (Algorithmen, Programmiersprachen)
- gdp02-gdp03 könnten zu "Datentypen" gehören (Variablen, Strings)
- gdp04-gdp05 könnten zu "Kontrollfluss" gehören (Schleifen, Methoden)
- gdp07-gdp08 könnten zu "Objektorientierung" gehören (Klassen, Vererbung)

Antwort als JSON (ALLE Dokumente müssen zugeordnet werden):
{{
    "Grundlagen und Einführung": ["gdp01.pdf", ...],
    "Datentypen und Strukturen": ["gdp02.pdf", "gdp03.pdf", ...],
    "Kontrollfluss und Methoden": ["gdp04.pdf", ...],
    "Objektorientierung": ["gdp07.pdf", ...],
    "reasoning": "Kurze Begründung der Gruppierung"
}}"""
        
        try:
            messages = [
                SystemMessage(content="Du bist Experte für Curriculum-Design und thematische Strukturierung von Lernmaterialien."),
                HumanMessage(content=prompt)
            ]
            
            response = self.llm.invoke(messages)
            
            # Debug: Zeige die rohe LLM-Antwort
            self.logger.info(f" LLM Clustering-Antwort (erste 1000 Zeichen):\n{response.content[:1000]}...")
            
            cleaned = self._clean_json_response(response.content)
            
            # Zusätzliche Bereinigung: Entferne alles nach dem letzten }
            # Falls das LLM zusätzlichen Text nach dem JSON hinzufügt
            try:
                result = json.loads(cleaned)
            except json.JSONDecodeError as e:
                self.logger.warning(f"Erste JSON-Parsing fehlgeschlagen: {e}")
                # Versuche aggressivere Bereinigung
                import re
                # Finde nur den JSON-Block zwischen { und }
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
                if json_match:
                    cleaned = json_match.group(0)
                    self.logger.info(f"JSON-Block extrahiert: {len(cleaned)} Zeichen")
                    result = json.loads(cleaned)
                else:
                    raise e
            
            # Entferne 'reasoning' aus Clustern
            clusters = {k: v for k, v in result.items() if k != "reasoning" and isinstance(v, list)}
            
            self.logger.info(f" Themen-Clustering: {len(clusters)} Bereiche identifiziert")
            if "reasoning" in result:
                self.logger.info(f" Begründung: {result['reasoning'][:200]}...")
            
            return clusters
            
        except Exception as e:
            self.logger.warning(f"LLM-Clustering fehlgeschlagen: {e}")
            # Fallback: Alle in einen Bereich
            return {"Alle Dokumente": [r.filename for r in kompetenz_results]}
    
    def _generate_learning_paths(self, kompetenz_results: List[KompetenzResult], relationships: List[Dict]) -> List[List[str]]:
        """
        Generiert optimale Lernpfade basierend auf Beziehungen.
        """
        # Vereinfachte Implementierung: Nutze Dateinamen-Reihenfolge + Beziehungen
        files = [r.filename for r in kompetenz_results]
        files.sort()  # gdp01, gdp02, gdp03, ...
        
        # Haupt-Lernpfad
        main_path = files
        
        # Alternative Pfade basierend auf Themen-Clustern
        clusters = self._identify_theme_clusters(kompetenz_results)
        alternative_paths = []
        
        for theme, theme_files in clusters.items():
            if len(theme_files) > 1:
                sorted_theme_files = sorted(theme_files)
                alternative_paths.append(sorted_theme_files)
        
        return [main_path] + alternative_paths
    
    def _create_cluster_nodes(self, clusters: Dict[str, List[str]], kompetenz_results: List[KompetenzResult]) -> Dict[str, str]:
        """
        Erstellt ThemeCluster als eigene Nodes in Neo4j.
        
        Returns:
            Dict mapping theme_name -> cluster_id
        """
        from llm.graph.neo4j_client import GraphDatabase
        
        db = GraphDatabase()
        cluster_ids = {}
        
        # Erstelle Lookup für Kompetenz-Ergebnisse
        doc_lookup = {r.filename: r for r in kompetenz_results if r}
        
        for theme, doc_names in clusters.items():
            # Sammle aggregierte Daten für diesen Cluster
            cluster_competencies = []
            cluster_taxonomies = []
            
            for doc_name in doc_names:
                if doc_name in doc_lookup:
                    result = doc_lookup[doc_name]
                    cluster_competencies.extend(result.kompetenzen[:3])  # Top 3 pro Dokument
                    if result.taxonomiestufe:
                        cluster_taxonomies.append(result.taxonomiestufe)
            
            # Eindeutige Top-Kompetenzen
            unique_competencies = list(dict.fromkeys(cluster_competencies))[:10]  # Top 10 unique
            
            # Cluster-Node erstellen
            cluster_id = f"cluster_{theme.lower().replace(' ', '_').replace('-', '_')}"
            
            create_cluster_query = """
            MERGE (c:ThemeCluster {cluster_id: $cluster_id})
            ON CREATE SET 
                c.name = $name,
                c.description = $description,
                c.document_count = $doc_count,
                c.competencies = $competencies,
                c.created_at = datetime()
            ON MATCH SET
                c.document_count = $doc_count,
                c.competencies = $competencies,
                c.updated_at = datetime()
            RETURN c.cluster_id as id
            """
            
            result = db.execute_query(create_cluster_query, {
                "cluster_id": cluster_id,
                "name": theme,
                "description": f"Cluster für {theme} mit {len(doc_names)} Dokumenten",
                "doc_count": len(doc_names),
                "competencies": unique_competencies
            })
            
            cluster_ids[theme] = cluster_id
            self.logger.info(f" ThemeCluster erstellt: {theme} ({cluster_id})")
            
            # Verbinde Dokumente mit Cluster
            for doc_name in doc_names:
                link_doc_query = """
                MATCH (d:Document)
                WHERE d.file_path CONTAINS $filename
                MATCH (c:ThemeCluster {cluster_id: $cluster_id})
                MERGE (d)-[r:BELONGS_TO]->(c)
                RETURN d.doc_id as doc_id
                """
                
                db.execute_query(link_doc_query, {
                    "filename": doc_name,
                    "cluster_id": cluster_id
                })
        
        return cluster_ids
    
    def _create_cluster_relationships(self, cluster_ids: Dict[str, str], relationships: List[Dict], clusters: Dict[str, List[str]]) -> int:
        """
        Analysiert und erstellt Cluster-zu-Cluster Beziehungen basierend auf Document-Beziehungen.
        Returns: Anzahl erstellter Cluster-Beziehungen
        """
        from llm.graph.neo4j_client import GraphDatabase
        db = GraphDatabase()
        
        self.logger.info(f" Analysiere Cluster-Beziehungen für {len(cluster_ids)} Cluster mit {len(relationships)} Document-Beziehungen")
        
        # Analysiere welche Cluster miteinander verbunden sind
        cluster_connections = {}
        
        for rel in relationships:
            doc1, doc2 = rel['doc1'], rel['doc2']
            rel_type = rel.get('type', 'RELATED')
            strength = rel.get('strength', 0.5)
            
            # Finde Cluster für beide Dokumente
            cluster1, cluster2 = None, None
            for theme, docs in clusters.items():
                if doc1 in docs:
                    cluster1 = theme
                if doc2 in docs:
                    cluster2 = theme
            
            # Nur Inter-Cluster Beziehungen (verschiedene Cluster)
            if cluster1 and cluster2 and cluster1 != cluster2:
                key = tuple(sorted([cluster1, cluster2]))
                if key not in cluster_connections:
                    cluster_connections[key] = {
                        'types': [],
                        'strengths': [],
                        'count': 0
                    }
                
                cluster_connections[key]['types'].append(rel_type)
                cluster_connections[key]['strengths'].append(strength)
                cluster_connections[key]['count'] += 1
        
        # Erstelle Cluster-Beziehungen für starke Verbindungen
        for (cluster1, cluster2), data in cluster_connections.items():
            # Nur wenn mindestens 2 Dokument-Beziehungen existieren
            if data['count'] >= 2:
                avg_strength = sum(data['strengths']) / len(data['strengths'])
                
                # Bestimme dominanten Beziehungstyp
                type_counts = {}
                for t in data['types']:
                    type_counts[t] = type_counts.get(t, 0) + 1
                dominant_type = max(type_counts, key=type_counts.get)
                
                if dominant_type in ['PREREQUISITE', 'BUILDS_UPON'] or avg_strength > 0.7:
                    create_cluster_rel = f"""
                    MATCH (c1:ThemeCluster {{cluster_id: $cluster1_id}})
                    MATCH (c2:ThemeCluster {{cluster_id: $cluster2_id}})
                    MERGE (c1)-[r:{dominant_type}_CLUSTER]->(c2)
                    ON CREATE SET 
                        r.strength = $strength,
                        r.document_connections = $doc_count,
                        r.reason = $reason
                    """
                    
                    db.execute_query(create_cluster_rel, {
                        "cluster1_id": cluster_ids[cluster1],
                        "cluster2_id": cluster_ids[cluster2],
                        "strength": avg_strength,
                        "doc_count": data['count'],
                        "reason": f"{data['count']} Dokument-Verbindungen zwischen Clustern"
                    })
                    
                    self.logger.info(f" Cluster-Beziehung: {cluster1} -[{dominant_type}]-> {cluster2} (Stärke: {avg_strength:.2f})")
        
        created_count = len([c for c in cluster_connections.values() if c['count'] >= 2])
        self.logger.info(f" Cluster-Beziehungen: {len(cluster_connections)} analysiert, {created_count} erstellt (min. 2 Dokument-Verbindungen benötigt)")
        return created_count
    
    def _save_competencies_as_nodes(self, konsolidierte_kompetenzen: List[str], kompetenz_results: List[KompetenzResult] = None) -> Dict[str, str]:
        """
        Speichert KONSOLIDIERTE Kompetenzen als Neo4j Nodes.
        Nutzt die bereits aggregierten und bereinigten Kompetenzen aus Phase 4.
        
        Args:
            konsolidierte_kompetenzen: Liste der konsolidierten Kompetenzen aus der Aggregation
            kompetenz_results: Optional - Original-Ergebnisse für Dokumenten-Mapping
            
        Returns:
            Dict mapping competency_name -> node_id
        """
        from llm.graph.neo4j_client import GraphDatabase
        
        db = GraphDatabase()
        competency_ids = {}
        
        self.logger.info(f" Erstelle Competency Nodes für {len(konsolidierte_kompetenzen)} KONSOLIDIERTE Kompetenzen...")
        
        # Falls wir die Original-Ergebnisse haben, baue ein Mapping auf
        doc_competency_mapping = {}
        if kompetenz_results:
            for result in kompetenz_results:
                doc_name = result.filename if hasattr(result, 'filename') else result.get('filename', 'Unknown')
                kompetenzen = result.kompetenzen if hasattr(result, 'kompetenzen') else result.get('kompetenzen', [])
                doc_competency_mapping[doc_name] = kompetenzen
        
        # Erstelle Competency Nodes für jede konsolidierte Kompetenz
        for competency_name in konsolidierte_kompetenzen:
            # Generiere eindeutige ID
            competency_id = f"comp_{competency_name[:50].lower().replace(' ', '_').replace('/', '_').replace('-', '_')}"
            
            # Bestimme Bloom Level basierend auf dem Kompetenz-Namen, bissi unsauber aktuell, theoretisch auch wieder mit LLM ermittelbar, aber keine Zeit zur Implementierung gerade
            bloom_level = "apply"  # Default
            if any(word in competency_name.lower() for word in ["versteht", "kennt", "weiß"]):
                bloom_level = "understand"
            elif any(word in competency_name.lower() for word in ["implementiert", "entwickelt", "erstellt"]):
                bloom_level = "apply"
            elif any(word in competency_name.lower() for word in ["analysiert", "untersucht", "evaluiert"]):
                bloom_level = "analyze"
            elif any(word in competency_name.lower() for word in ["entwirft", "konzipiert", "optimiert"]):
                bloom_level = "create"

            # auch bissi unsauber hier die direkt cypher Query, aber vorerst i.o. macht was es soll. Aber habe eigentlich framework hierfür
            create_comp_query = """
            MERGE (c:Competency {name: $name})
            ON CREATE SET 
                c.competency_id = $comp_id,
                c.description = $description,
                c.bloom_level = $bloom_level,
                c.is_consolidated = true,
                c.created_at = datetime()
            ON MATCH SET
                c.is_consolidated = true,
                c.updated_at = datetime()
            RETURN c.competency_id as id
            """
            
            result = db.execute_query(create_comp_query, {
                "comp_id": competency_id,
                "name": competency_name,
                "description": f"Konsolidierte Kompetenz aus Phase 4 Aggregation",
                "bloom_level": bloom_level
            })
            
            competency_ids[competency_name] = competency_id
            self.logger.debug(f" Competency Node erstellt: {competency_name[:50]}...")
            
            # Falls wir das Dokument-Mapping haben, erstelle TEACHES Beziehungen
            if doc_competency_mapping:
                # Finde Dokumente, die ähnliche Kompetenzen haben
                for doc_name, doc_competencies in doc_competency_mapping.items():
                    # Einfache Ähnlichkeitsprüfung - kann später verbessert werden
                    for orig_competency in doc_competencies:
                        if any(word in orig_competency.lower() for word in competency_name.lower().split()[:3]):
                            create_teaches_query = """
                            MATCH (d:Document)
                            WHERE d.file_path CONTAINS $doc_name
                            MATCH (c:Competency {competency_id: $comp_id})
                            MERGE (d)-[r:TEACHES]->(c)
                            ON CREATE SET 
                                r.confidence = 0.8,
                                r.extracted_at = datetime(),
                                r.original_competency = $orig_comp
                            RETURN d.doc_id as doc_id
                            """
                            
                            db.execute_query(create_teaches_query, {
                                "doc_name": doc_name,
                                "comp_id": competency_id,
                                "orig_comp": orig_competency
                            })
                            break  # Nur eine Beziehung pro Dokument
        
        self.logger.info(f" {len(competency_ids)} Competency Nodes erstellt")
        return competency_ids
    
    def _create_competency_id(self, name: str) -> str:
        """Erstellt eine eindeutige ID für eine Kompetenz"""
        import re
        # Normalisiere den Namen für die ID
        normalized = name.lower()
        normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
        normalized = normalized.replace(' ', '_')
        # Begrenze auf 50 Zeichen
        return f"comp_{normalized[:50]}"
    
    def create_assignment_requires_relationships(self, assignment_name: str, required_competencies: List[Any], 
                                                 course_id: str = None) -> int:
        """
        Erstellt REQUIRES Beziehungen zwischen einem Assignment und den benötigten Kompetenzen.
        Findet existierende Kompetenzen oder erstellt neue bei Bedarf.
        
        Args:
            assignment_name: Name des Assignments
            required_competencies: Liste der benötigten Kompetenzen (Strings oder Dicts)
            course_id: Optionale Kurs-ID für Kontext
            
        Returns:
            Anzahl erstellter Beziehungen
        """
        from llm.graph.neo4j_client import GraphDatabase
        
        db = GraphDatabase()
        created_count = 0
        
        self.logger.info(f" Erstelle Assignment Node für: {assignment_name}")
        
        # Erstelle Assignment Node
        assignment_id = f"assign_{assignment_name[:30].lower().replace(' ', '_')}"
        
        create_assign_query = """
        MERGE (a:Assignment {assignment_id: $assignment_id})
        ON CREATE SET 
            a.name = $name,
            a.course_id = $course_id,
            a.created_at = datetime()
        ON MATCH SET
            a.updated_at = datetime()
        RETURN a.assignment_id as id
        """
        
        db.execute_query(create_assign_query, {
            "assignment_id": assignment_id,
            "name": assignment_name,
            "course_id": course_id or "unknown"
        })
        
        # Verarbeite Kompetenzen - können Strings oder Dicts sein
        for competency_item in required_competencies:
            # Extrahiere Kompetenz-Name aus Dict oder verwende String direkt
            if isinstance(competency_item, dict):
                competency_name = competency_item.get('Lernziel', str(competency_item))
                messbarkeit = competency_item.get('Messbarkeit', '')
            else:
                competency_name = str(competency_item)
                messbarkeit = ''
            
            # Versuche zuerst existierende Kompetenz zu finden
            find_competency_query = """
            MATCH (c:Competency)
            WHERE toLower(c.name) CONTAINS toLower($search_term)
               OR toLower($search_term) CONTAINS toLower(c.name)
            RETURN c.competency_id as id, c.name as name
            ORDER BY 
                CASE 
                    WHEN toLower(c.name) = toLower($search_term) THEN 0
                    WHEN toLower(c.name) STARTS WITH toLower($search_term) THEN 1
                    ELSE 2
                END,
                length(c.name)
            LIMIT 1
            """
            
            # Suche mit vereinfachtem Begriff (erste paar Wörter)
            search_term = ' '.join(competency_name.split()[:5])
            result = db.execute_query(find_competency_query, {"search_term": search_term})
            
            if result and len(result) > 0:
                # Existierende Kompetenz gefunden
                comp_id = result[0]['id']
                comp_name = result[0]['name']
                self.logger.info(f"    Verwende existierende Kompetenz: {comp_name}")
            else:
                # Erstelle neue Kompetenz wenn keine gefunden
                comp_id = self._create_competency_id(competency_name)
                create_comp_query = """
                MERGE (c:Competency {competency_id: $comp_id})
                ON CREATE SET 
                    c.name = $name,
                    c.bloom_level = 'Anwenden',
                    c.source = 'assignment_analysis',
                    c.messbarkeit = $messbarkeit,
                    c.created_at = datetime()
                RETURN c.competency_id as id
                """
                
                db.execute_query(create_comp_query, {
                    "comp_id": comp_id,
                    "name": competency_name,
                    "messbarkeit": messbarkeit
                })
                self.logger.info(f"    Neue Kompetenz erstellt: {competency_name}")
            
            # Erstelle REQUIRES Beziehung
            create_requires_query = """
            MATCH (a:Assignment {assignment_id: $assignment_id})
            MATCH (c:Competency {competency_id: $comp_id})
            MERGE (a)-[r:REQUIRES]->(c)
            ON CREATE SET 
                r.strength = 'high',
                r.created_at = datetime()
            RETURN a.name as assignment, c.name as competency
            """
            
            result = db.execute_query(create_requires_query, {
                "assignment_id": assignment_id,
                "comp_id": comp_id
            })
            
            data, columns = result
            if data:
                created_count += 1
                self.logger.debug(f" Assignment '{assignment_name}' REQUIRES '{competency_name}'")
            else:
                self.logger.warning(f" Kompetenz '{competency_name}' nicht gefunden")
        
        self.logger.info(f" {created_count} REQUIRES Beziehungen für Assignment '{assignment_name}' erstellt")
        return created_count

    def _save_relationships_to_neo4j(self, relationships: List[Dict], clusters: Dict[str, List[str]], kompetenz_results: List[KompetenzResult] = None):
        """
        Speichert die gefundenen Beziehungen und Cluster strukturiert in Neo4j.
        Erstellt ThemeCluster als eigene Nodes für bessere Hierarchie.
        NEU: Erstellt auch Competency Nodes aus den Extraktionsergebnissen.
        """
        try:
            from llm.graph.neo4j_client import GraphDatabase
            
            db = GraphDatabase()
            
            self.logger.info(f" Speichere {len(relationships)} Beziehungen und {len(clusters)} Cluster in Neo4j...")
            
            # NEU: Erstelle Competency Nodes ZUERST - aber das machen wir jetzt in Phase 4!
            
            # 1. Erstelle Document-Knoten falls nicht vorhanden (direkte Cypher-Queries)
            all_docs = set()
            for rel in relationships:
                all_docs.add(rel['doc1'])
                all_docs.add(rel['doc2'])
            
            for doc_name in all_docs:
                # Suche existierende Nodes über file_path statt neue zu erstellen
                # doc_name ist z.B. "gdp01.pdf", wir suchen nach file_path der das enthält
                self.logger.debug(f" Suche Document-Node für: {doc_name}")
                
                find_doc_query = """
                MATCH (d:Document)
                WHERE d.file_path CONTAINS $filename
                RETURN d.doc_id as doc_id, d.file_path as file_path
                """
                result = db.execute_query(find_doc_query, {"filename": doc_name})
                data, columns = result  # execute_query gibt (data, columns) zurück
                
                self.logger.debug(f" Query-Result für {doc_name}: {len(data)} Nodes gefunden")
                if data:
                    for row in data:
                        self.logger.debug(f"   - Gefunden: doc_id={row[0]}, file_path={row[1]}")
                
                if not data:  # Prüfe ob Daten-Liste leer ist
                    # Nur wenn kein existierender Node gefunden wurde, erstelle einen neuen
                    self.logger.warning(f" Kein Document-Node für {doc_name} gefunden - erstelle neuen")
                    create_doc_query = """
                    MERGE (d:Document {doc_id: $doc_id})
                    ON CREATE SET d.title = $title, d.doc_type = 'slide', d.created_at = datetime()
                    """
                    db.execute_query(create_doc_query, {"doc_id": doc_name, "title": doc_name})
                    self.logger.info(f" Neuer Document-Node erstellt: {doc_name}")
                    
            # 2. Erstelle Beziehungen (direkte Cypher-Queries)
            relationships_created = 0
            relationships_failed = 0
            
            for rel in relationships:
                doc1_filename = rel['doc1']
                doc2_filename = rel['doc2']
                rel_type = rel.get('type', 'RELATED').upper().split('|')[0].strip()  # Nur erster Typ, falls doch Multi-Type
                strength = rel.get('strength', 0.5)
                reason = rel.get('reason', 'LLM-analysierte Beziehung')
                
                self.logger.debug(f" Erstelle Beziehung: {doc1_filename} -[{rel_type}]-> {doc2_filename}")
                
                try:
                    # Finde Nodes über file_path statt doc_id
                    create_rel_query = f"""
                    MATCH (d1:Document)
                    WHERE d1.file_path CONTAINS $doc1_filename
                    MATCH (d2:Document)
                    WHERE d2.file_path CONTAINS $doc2_filename
                    MERGE (d1)-[r:{rel_type}]->(d2)
                    ON CREATE SET r.strength = $strength, r.reason = $reason
                    RETURN d1.doc_id as d1_id, d2.doc_id as d2_id
                    """
                    
                    result = db.execute_query(create_rel_query, {
                        "doc1_filename": doc1_filename,
                        "doc2_filename": doc2_filename,
                        "strength": strength,
                        "reason": reason
                    })
                    
                    data, columns = result
                    if data:
                        self.logger.debug(f" Beziehung erstellt zwischen {data[0][0]} und {data[0][1]}")
                        relationships_created += 1
                    else:
                        self.logger.warning(f" Keine Nodes gefunden für Beziehung {doc1_filename} -> {doc2_filename}")
                        relationships_failed += 1
                        
                except Exception as e:
                    self.logger.error(f" Fehler bei Beziehung {doc1_filename} -> {doc2_filename}: {e}")
                    relationships_failed += 1
            
            # Theme-Properties werden jetzt in _create_cluster_nodes gesetzt
            
            # 3. NEU: Erstelle ThemeCluster Nodes
            if kompetenz_results:
                cluster_ids = self._create_cluster_nodes(clusters, kompetenz_results)
                
                # 4. NEU: Erstelle Cluster-zu-Cluster Beziehungen
                cluster_rel_count = self._create_cluster_relationships(cluster_ids, relationships, clusters)
                
                self.logger.info(f" Neo4j: {relationships_created} Dokument-Beziehungen, {len(cluster_ids)} Cluster, {cluster_rel_count} Cluster-Beziehungen erstellt")
            else:
                # Fallback: Nur Theme als Property speichern
                for theme, docs in clusters.items():
                    for doc_name in docs:
                        update_theme_query = """
                        MATCH (d:Document)
                        WHERE d.file_path CONTAINS $filename
                        SET d.theme = $theme
                        """
                        db.execute_query(update_theme_query, {"filename": doc_name, "theme": theme})
                
                self.logger.info(f" Neo4j: {relationships_created} neue Beziehungen erstellt, {relationships_failed} fehlgeschlagen")
            
            if relationships_failed > 0:
                self.logger.warning(f" {relationships_failed} Beziehungen konnten nicht erstellt werden - prüfe ob alle Document-Nodes existieren!")
            
        except Exception as e:
            import traceback
            self.logger.error(f" Neo4j-Speicherung fehlgeschlagen: {e}")
            self.logger.error(f" VOLLSTÄNDIGER FEHLER:")
            self.logger.error(traceback.format_exc())
            # Nicht kritisch - System läuft auch ohne Graph-Speicherung weiter
    
    def evaluate(self, content: Any, **kwargs) -> AggregatedResult:
        """
        Aggregiert mehrere Kompetenz-Ergebnisse zu einem Gesamtbild.
        
        Args:
            content: Liste von KompetenzResult-Objekten oder Dicts
            **kwargs:
                - aggregation_strategy: "merge", "hierarchical", "weighted"
                - kurs_name: Name des Gesamtkurses
                - min_frequency: Minimale Häufigkeit für Aufnahme (default: 1)
        """
        strategy = kwargs.get("aggregation_strategy", "merge")
        kurs_name = kwargs.get("kurs_name", "Unbenannter Kurs")
        min_frequency = kwargs.get("min_frequency", 1)
        
        # Content in einheitliches Format bringen
        kompetenz_list = self._normalize_content(content)
        
        # DEBUG: Überprüfe ob Dateinamen vorhanden sind
        if kompetenz_list and kompetenz_list[0]:
            self.logger.info(f" Erstes Dokument hat filename: {'filename' in kompetenz_list[0]}")
            if 'filename' in kompetenz_list[0]:
                self.logger.info(f"   Filename: {kompetenz_list[0]['filename']}")
        
        if not kompetenz_list:
            return AggregatedResult(
                consolidated_items=[],
                groupings={},
                statistics={"error": "Keine Kompetenzen zum Aggregieren"},
                raw_output="",
                metadata={"provider": self.provider}
            )
        
        # DEBUG: Was kommt an?
        self.logger.info(f" DEBUG: Content type: {type(content)}")
        if isinstance(content, list) and content:
            self.logger.info(f" DEBUG: First item type: {type(content[0])}")
            self.logger.info(f" DEBUG: First item keys: {list(content[0].keys()) if isinstance(content[0], dict) else 'Not a dict'}")
        
        # NEUE FUNKTIONALITÄT: Beziehungsanalyse
        document_relationships = self._analyze_document_relationships(content)
        self.logger.info(f" Dokumentbeziehungen analysiert: {len(document_relationships.get('relationships', []))} Beziehungen gefunden")
        
        # RAG-Anreicherung: Sammle Details zu den wichtigsten Kompetenzen
        enriched_context = {}
        if self.use_rag:
            self.logger.info(f" RAG-Anreicherung für Top-Kompetenzen...")
            
            # Extrahiere die häufigsten Kompetenzen für RAG
            competency_frequency = {}
            for item in kompetenz_list:
                for comp in item.get("kompetenzen", []):
                    competency_frequency[comp] = competency_frequency.get(comp, 0) + 1
            
            # Top 5 häufigste Kompetenzen für RAG
            top_competencies = sorted(competency_frequency.items(), 
                                    key=lambda x: x[1], reverse=True)[:5]
            
            for competency, count in top_competencies:
                self.logger.debug(f" Suche Details für '{competency}' (erwähnt {count}x)")
                
                # Generiere intelligente RAG-Query
                context_info = {"kurs_name": kurs_name}
                rag_query = self._generate_competency_rag_query(competency, context_info)
                
                # Hole verwandte Inhalte
                try:
                    related_docs = self.get_rag_context(rag_query, k=3)
                    if related_docs:
                        enriched_context[competency] = {
                            "query": rag_query,
                            "details": related_docs[:3],  # Top 3 relevante Chunks
                            "frequency": count
                        }
                        self.logger.debug(f" {len(related_docs)} Details gefunden für '{competency}'")
                    else:
                        self.logger.debug(f" Keine Details gefunden für '{competency}'")
                        
                except Exception as e:
                    self.logger.warning(f" RAG-Suche für '{competency}' fehlgeschlagen: {e}")
            
            self.logger.info(f" RAG-Anreicherung abgeschlossen: {len(enriched_context)} Kompetenzen angereichert")
        
        # Prompt basierend auf Strategie (mit RAG-Anreicherung)
        system_prompt = self._build_system_prompt(strategy)
        user_prompt = self._build_user_prompt(kompetenz_list, kurs_name, min_frequency, enriched_context)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        try:
            response = self.llm.invoke(messages)
            self.logger.debug(f"Aggregation Response erhalten")
            
            
            # Bereinige die Antwort von Markdown-Code-Blöcken
            cleaned_content = self._clean_json_response(response.content)
            
            # # DEBUG: Zeige bereinigte Antwort
            # self.logger.info(f" CLEANED RESPONSE ({len(cleaned_content)} Zeichen):")
            # self.logger.info(f"--- START CLEANED ---")
            # self.logger.info(cleaned_content)
            # self.logger.info(f"--- END CLEANED ---")

            # Hier ist das mapping drin, sihet dann so aus
                #              Erstelle Competency Nodes in Neo4j...
                # [2025-08-06 17:02:58,659] [INFO] llm.evaluate.aggregate_evaluator:  CLEANED RESPONSE (5098 Zeichen):
                # [2025-08-06 17:02:58,659] [INFO] llm.evaluate.aggregate_evaluator: --- START CLEANED ---
                # [2025-08-06 17:02:58,659] [INFO] llm.evaluate.aggregate_evaluator: {
                #     "konsolidierte_kompetenzen": [
                #         "Implementiert Java-Programme unter Verwendung von primitiven und Referenzdatentypen",
                #         "Verwendet Kontrollstrukturen wie Schleifen und Verzweigungen zur Steuerung des Programmflusses in Java",
                #         "Entwickelt und dokumentiert Methoden in Java unter Verwendung von Javadoc",
                #         "Verwendet Arrays und iteriert über diese mit Schleifen in Java",
                #         "Implementiert objektorientierte Konzepte wie Vererbung, Polymorphismus und Kapselung in Java",
                #         "Verwendet Strings und String-Methoden zur Manipulation und Verarbeitung von Text in Java",
                #         "Verwendet Git für Versionskontrolle und Zusammenarbeit in Softwareprojekten",
                #         "Analysiert und implementiert grundlegende Algorithmen in Java"
                #     ],
                #     "konsolidierte_kompetenzen_detailliert": [
                #         {
                #             "name": "Implementiert Java-Programme unter Verwendung von primitiven und Referenzdatentypen",
                #             "source_competencies": [
                #                 {"doc": "gdp01.pdf", "original": "Grundlegende Datentypen und Variablen in Java"},
                #                 {"doc": "gdp02.pdf", "original": "Verwendung von primitiven Datentypen und Referenzdatentypen"}
                #             ]
                #         },
                #         {
                #             "name": "Verwendet Kontrollstrukturen wie Schleifen und Verzweigungen zur Steuerung des Programmflusses in Java",
                #             "source_competencies": [
                #                 {"doc": "gdp04.pdf", "original": "Verwendung von Kontrollstrukturen in Java"},
                #                 {"doc": "gdp07.pdf", "original": "Implementierung von Kontrollstrukturen (Schleifen, Fallunterscheidungen)"}
                #             ]
                #         },
                #         {
                #             "name": "Entwickelt und dokumentiert Methoden in Java unter Verwendung von Javadoc",
                #             "source_competencies": [
                #                 {"doc": "gdp05.pdf", "original": "Methoden in Java definieren und verwenden, Javadoc zur Dokumentation nutzen"}
                #             ]
                #         }....
            
            result_json = json.loads(cleaned_content)
            
            return AggregatedResult(
                consolidated_items=result_json.get("konsolidierte_kompetenzen", []),
                # NEU: Detaillierte Konsolidierung mit Source-Tracking
                consolidated_items_detailed=result_json.get("konsolidierte_kompetenzen_detailliert", []),
                groupings=result_json.get("gruppierungen", {}),
                statistics=result_json.get("statistiken", {}),
                raw_output=response.content,
                metadata={
                    "provider": self.provider,
                    "strategy": strategy,
                    "kurs_name": kurs_name,
                    "input_count": len(kompetenz_list),
                    "model": self.llm.model_name if hasattr(self.llm, 'model_name') else 'unknown',
                    "rag_enhanced": self.use_rag,
                    "rag_enriched_competencies": len(enriched_context) if enriched_context else 0,
                    "enriched_details": list(enriched_context.keys()) if enriched_context else [],
                    "document_relationships": document_relationships
                }
            )
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON-Parsing-Fehler bei Aggregation: {e}")
            return AggregatedResult(
                consolidated_items=[],
                groupings={},
                statistics={"error": str(e)},
                raw_output=response.content if response else "",
                metadata={"error": str(e), "provider": self.provider}
            )
    
    def _normalize_content(self, content: Any) -> List[Dict]:
        """Normalisiert verschiedene Input-Formate zu einer Liste von Dicts"""
        normalized = []
        
        if isinstance(content, list):
            for item in content:
                if isinstance(item, KompetenzResult):
                    normalized.append(item.model_dump())
                elif isinstance(item, dict):
                    normalized.append(item)
                else:
                    self.logger.warning(f"Unbekannter Typ in Aggregation: {type(item)}")
        else:
            self.logger.error(f"Content muss eine Liste sein, erhalten: {type(content)}")
        
        return normalized
    
    def _build_system_prompt(self, strategy: str) -> str:
        """Erstellt Strategy-spezifische System-Prompts"""
        base_prompt = """Du bist ein Experte für Curriculumsentwicklung und Kompetenzmodellierung.
Deine Aufgabe ist es, aus mehreren Kompetenz-Extraktionen ein kohärentes Gesamtbild zu erstellen.

WICHTIG: Dir werden sowohl die ursprünglich extrahierten Kompetenzen als auch detaillierte Zusatzinformationen 
aus den Kursdokumenten zur Verfügung gestellt. Nutze diese Details um spezifischere, granularere und 
praxis-orientierte Kompetenzen zu formulieren."""

        strategy_prompts = {
            "merge": """
Verwende eine MERGE-Strategie:
- Fasse ähnliche Kompetenzen zusammen
- Eliminiere Duplikate
- Behalte die präzisesten Formulierungen
- Erstelle eine flache Liste aller relevanten Kompetenzen""",
            
            "hierarchical": """
Verwende eine HIERARCHISCHE Strategie:
- Gruppiere Kompetenzen nach Themenbereichen
- Erstelle Haupt- und Unterkompetenzen
- Ordne nach Bloom'scher Taxonomie
- Zeige Abhängigkeiten zwischen Kompetenzen""",
            
            "weighted": """
Verwende eine GEWICHTETE Strategie:
- Priorisiere häufig genannte Kompetenzen
- Gewichte nach Taxonomiestufe
- Identifiziere Kernkompetenzen vs. ergänzende Kompetenzen
- Erstelle eine nach Wichtigkeit sortierte Liste"""
        }
        
        prompt = base_prompt + strategy_prompts.get(strategy, strategy_prompts["merge"])
        
        prompt += """\n\nKONSOLIDIERUNGS-STRATEGIE:
1. Fasse ähnliche Kompetenzen aus verschiedenen Dokumenten zusammen
2. Eliminiere Duplikate, behalte aber dokumentspezifische Nuancen
3. Gruppiere nach Themenbereichen für bessere Übersicht
4. Ziel: 15-25 KONKRETE, LEHRBARE Kompetenzen für den gesamten Kurs

WICHTIG BEI DER FORMULIERUNG:
- Formuliere KONKRETE, MESSBARE Kompetenzen (nicht "versteht Programmierung" sondern "kann Schleifen zur Iteration über Datenstrukturen implementieren")
- Nutze aktive Verben: implementiert, entwickelt, analysiert, entwirft, optimiert
- Beziehe dich auf SPEZIFISCHE Technologien/Konzepte aus den Dokumenten
- Unterscheide zwischen Grundlagen und fortgeschrittenen Kompetenzen
- VERMEIDE generische Aussagen wie "Grundlagen verstehen" oder "Konzepte anwenden"

BEISPIELE GUTER KOMPETENZEN:
 "Implementiert rekursive Algorithmen zur Lösung von Divide-and-Conquer-Problemen"
 "Entwickelt RESTful APIs mit Spring Boot und dokumentiert diese mit OpenAPI"
 "Analysiert die Zeitkomplexität von Sortieralgorithmen und wählt situationsgerecht aus"
 "Versteht Algorithmen" (zu generisch)
 "Kann programmieren" (nicht messbar)

Antworte immer im folgenden JSON-Format:
{
    "konsolidierte_kompetenzen": ["Kompetenz 1", "Kompetenz 2", ...],
    "konsolidierte_kompetenzen_detailliert": [
        {
            "name": "Kompetenz 1",
            "source_competencies": [
                {"doc": "dateiname1.pdf", "original": "Original-Kompetenz aus diesem Dokument"},
                {"doc": "dateiname2.pdf", "original": "Ähnliche Kompetenz aus anderem Dokument"}
            ]
        }
    ],
    "gruppierungen": {
        "Themenbereich 1": ["Kompetenz A", "Kompetenz B"],
        "Themenbereich 2": ["Kompetenz C", "Kompetenz D"]
    },
    "statistiken": {
        "gesamt_kompetenzen": Anzahl,
        "häufigste_taxonomiestufe": "Stufe",
        "kernkompetenzen": ["Top 3-5 Kompetenzen"],
        "coverage": "Prozent der Vorlesungen die abgedeckt wurden"
    }
}

BEACHTE: Die Arrays "konsolidierte_kompetenzen" und "konsolidierte_kompetenzen_detailliert" müssen die GLEICHE Anzahl und Reihenfolge haben!"""
        
        return prompt
    
    def _build_user_prompt(self, kompetenz_list: List[Dict], kurs_name: str, min_frequency: int, enriched_context: Dict = None) -> str:
        """Baut den User-Prompt für die Aggregation"""
        prompt_parts = [
            f"KURS: {kurs_name}",
            f"ANZAHL EINZELEXTRAKTIONEN: {len(kompetenz_list)}",
            f"MINIMALE HÄUFIGKEIT: {min_frequency}",
            "\nEINZELNE KOMPETENZ-EXTRAKTIONEN:"
        ]
        
        for i, komp in enumerate(kompetenz_list, 1):
            prompt_parts.append(f"\n--- Extraktion {i} ---")
            # WICHTIG: Dateiname für Source-Tracking
            if "filename" in komp:
                prompt_parts.append(f"Datei: {komp['filename']}")
            if "kompetenzen" in komp:
                prompt_parts.append(f"Kompetenzen: {', '.join(komp['kompetenzen'][:5])}")
            if "taxonomiestufe" in komp:
                prompt_parts.append(f"Taxonomiestufe: {komp['taxonomiestufe']}")
            if "metadata" in komp and "kurs_metadaten" in komp["metadata"]:
                meta = komp["metadata"]["kurs_metadaten"]
                if meta:
                    prompt_parts.append(f"Quelle: {meta.get('title', 'Unbekannt')}")
        
        # RAG-ANREICHERUNG: Detaillierte Informationen zu häufigen Kompetenzen
        if enriched_context:
            prompt_parts.append(f"\n DETAILLIERTE INFORMATIONEN (durch RAG-Suche gefunden):")
            prompt_parts.append(f"Für die häufigsten Kompetenzen wurden zusätzliche Details aus den Kursdokumenten gesammelt:")
            
            for competency, context in enriched_context.items():
                prompt_parts.append(f"\n--- DETAILS FÜR '{competency}' (erwähnt {context['frequency']}x) ---")
                prompt_parts.append(f"Suchquery: {context['query']}")
                
                for i, doc in enumerate(context['details'], 1):
                    content = doc.get('content', '')[:500]  # Erste 500 Zeichen
                    metadata = doc.get('metadata', {})
                    source = metadata.get('source_file', 'Unbekannt')
                    
                    prompt_parts.append(f"\n[Detail {i} aus {source}]")
                    prompt_parts.append(content + "...")
        
        prompt_parts.append("\nErstelle daraus ein konsolidiertes, DETAILLIERTES Kompetenzprofil für den gesamten Kurs.")
        prompt_parts.append("Nutze die gefundenen Details um spezifischere und granularere Kompetenzen zu formulieren.")
        
        return "\n".join(prompt_parts)

if __name__ == "__main__":
    print("You tried to run the AggregateEvaluator directly.")