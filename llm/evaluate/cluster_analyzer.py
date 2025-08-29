# llm/evaluate/cluster_analyzer.py
"""
Modulare Cluster-basierte Dokumentanalyse.
Reduziert n×n Vergleiche auf intelligente Cluster-Vergleiche.
"""

from typing import List, Dict, Any, Tuple
from llm.evaluate.base import KompetenzResult
from logger import get_logger

class ClusterAnalyzer:
    """
    Analysiert Dokument-Beziehungen basierend auf thematischen Clustern.
    Reduziert Komplexität von O(n²) auf O(k×m) wo k=Cluster, m=Docs pro Cluster.
    """
    
    def __init__(self, llm, logger=None):
        self.llm = llm
        self.logger = logger or get_logger(__name__)
    
    def analyze_relationships(self, 
                             kompetenz_results: List[KompetenzResult],
                             clusters: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Hauptmethode: Analysiert Beziehungen cluster-basiert.
        
        Args:
            kompetenz_results: Liste der Kompetenz-Analysen
            clusters: Thematische Cluster {"Theme": ["doc1.pdf", "doc2.pdf"]}
            
        Returns:
            Dict mit relationships, statistics, bridge_documents
        """
        self.logger.info(f" Starte Cluster-basierte Analyse für {len(clusters)} Cluster")
        
        # 1. Intra-Cluster Beziehungen (innerhalb der Cluster)
        intra_relationships = self._analyze_intra_cluster(kompetenz_results, clusters)
        
        # 2. Inter-Cluster Beziehungen (zwischen Clustern - nur wichtige)
        inter_relationships = self._analyze_inter_cluster(kompetenz_results, clusters)
        
        # 3. Statistiken
        stats = self._calculate_statistics(intra_relationships, inter_relationships)
        
        return {
            "intra_cluster": intra_relationships,
            "inter_cluster": inter_relationships,
            "statistics": stats,
            "clusters": clusters
        }
    
    def _analyze_intra_cluster(self, 
                               kompetenz_results: List[KompetenzResult],
                               clusters: Dict[str, List[str]]) -> List[Dict]:
        """
        Analysiert Beziehungen INNERHALB der Cluster.
        Hier machen detaillierte Vergleiche Sinn.
        """
        relationships = []
        
        # Erstelle Lookup für schnellen Zugriff
        doc_lookup = {r.filename: r for r in kompetenz_results}
        
        for theme, docs in clusters.items():
            if len(docs) < 2:
                continue  # Einzeldokument-Cluster überspringen
                
            self.logger.info(f"   Analysiere Cluster '{theme}' mit {len(docs)} Dokumenten")
            
            # Nur innerhalb des Clusters vergleichen
            for i, doc1_name in enumerate(docs):
                for doc2_name in docs[i+1:]:
                    if doc1_name in doc_lookup and doc2_name in doc_lookup:
                        result1 = doc_lookup[doc1_name]
                        result2 = doc_lookup[doc2_name]
                        
                        # Hier würde der eigentliche Vergleich stattfinden
                        # (ausgelagert in separate Methode)
                        rel = self._compare_documents_simple(result1, result2, theme)
                        if rel:
                            relationships.append(rel)
        
        self.logger.info(f"   {len(relationships)} Intra-Cluster Beziehungen gefunden")
        return relationships
    
    def _analyze_inter_cluster(self,
                               kompetenz_results: List[KompetenzResult], 
                               clusters: Dict[str, List[str]]) -> List[Dict]:
        """
        Analysiert Beziehungen ZWISCHEN Clustern.
        Nur für "Brücken-Dokumente" oder sehr starke Verbindungen.
        """
        relationships = []
        doc_lookup = {r.filename: r for r in kompetenz_results}
        
        # Wähle Repräsentanten pro Cluster (erstes/letztes Dokument)
        cluster_representatives = {}
        for theme, docs in clusters.items():
            if docs:
                # Erstes und letztes als potenzielle Brücken
                cluster_representatives[theme] = {
                    'first': docs[0],
                    'last': docs[-1] if len(docs) > 1 else docs[0]
                }
        
        # Vergleiche nur Repräsentanten zwischen Clustern
        cluster_names = list(cluster_representatives.keys())
        for i, theme1 in enumerate(cluster_names):
            for theme2 in cluster_names[i+1:]:
                reps1 = cluster_representatives[theme1]
                reps2 = cluster_representatives[theme2]
                
                # Prüfe ob starke Verbindung zwischen Clustern existiert
                for doc1_name in [reps1['first'], reps1['last']]:
                    for doc2_name in [reps2['first'], reps2['last']]:
                        if doc1_name in doc_lookup and doc2_name in doc_lookup:
                            result1 = doc_lookup[doc1_name]
                            result2 = doc_lookup[doc2_name]
                            
                            # Nur SEHR starke Verbindungen zwischen Clustern
                            rel = self._check_bridge_relationship(result1, result2, theme1, theme2)
                            if rel:
                                relationships.append(rel)
                                self.logger.info(f"   Brücke gefunden: {theme1} ↔ {theme2}")
        
        self.logger.info(f"   {len(relationships)} Inter-Cluster Beziehungen gefunden")
        return relationships
    
    def _compare_documents_simple(self, 
                                  result1: KompetenzResult,
                                  result2: KompetenzResult,
                                  cluster_theme: str) -> Dict:
        """
        Vereinfachter Dokumentvergleich innerhalb eines Clusters.
        """
        # Gemeinsame Kompetenzen finden
        common = set(result1.kompetenzen) & set(result2.kompetenzen)
        
        if len(common) > 3:  # Signifikante Überlappung
            return {
                "doc1": result1.filename,
                "doc2": result2.filename,
                "type": "RELATED",
                "strength": len(common) / max(len(result1.kompetenzen), len(result2.kompetenzen)),
                "cluster": cluster_theme,
                "common_competencies": list(common)[:5]
            }
        return None
    
    def _check_bridge_relationship(self,
                                   result1: KompetenzResult,
                                   result2: KompetenzResult,
                                   theme1: str,
                                   theme2: str) -> Dict:
        """
        Prüft auf starke Brücken-Beziehungen zwischen Clustern.
        Nur PREREQUISITE oder sehr starke BUILDS_UPON.
        """
        # Hier würde die LLM-Analyse für wichtige Verbindungen stattfinden
        # Vorerst: Einfache Heuristik
        
        # Check für bestimmte Schlüsselwörter die auf Prerequisites hindeuten
        if "Grundlagen" in theme1 and "Fortgeschritten" in theme2:
            return {
                "doc1": result1.filename,
                "doc2": result2.filename,
                "type": "PREREQUISITE",
                "strength": 0.8,
                "cluster_from": theme1,
                "cluster_to": theme2,
                "reason": "Grundlagen-Cluster ist Voraussetzung für Fortgeschrittenen-Cluster"
            }
        
        return None
    
    def _calculate_statistics(self, 
                             intra_relationships: List[Dict],
                             inter_relationships: List[Dict]) -> Dict:
        """
        Berechnet Statistiken über die gefundenen Beziehungen.
        """
        total = len(intra_relationships) + len(inter_relationships)
        
        # Typen zählen
        type_counts = {}
        for rel in intra_relationships + inter_relationships:
            rel_type = rel.get("type", "UNKNOWN")
            type_counts[rel_type] = type_counts.get(rel_type, 0) + 1
        
        return {
            "total_relationships": total,
            "intra_cluster_count": len(intra_relationships),
            "inter_cluster_count": len(inter_relationships),
            "relationship_types": type_counts,
            "density_reduction": f"{total} statt {len(intra_relationships)**2} (n×n)"
        }

if __name__ == "__main__":
    print("ClusterAnalyzer direkt gestartet, nutze den entrypoint")