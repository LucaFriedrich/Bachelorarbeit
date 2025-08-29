# llm/evaluate/cluster_relationship_analyzer.py
"""
Optimierte Beziehungsanalyse mit Cluster-basiertem Ansatz.
Reduziert n² Komplexität durch intelligente Gruppierung.
"""

from typing import List, Dict, Any, Tuple
from llm.evaluate.base import KompetenzResult
from logger import get_logger

logger = get_logger(__name__)


class ClusterRelationshipAnalyzer:
    """
    Analysiert Dokument-Beziehungen cluster-basiert statt n².
    
    Strategie:
    1. Nutze existierende Themen-Cluster
    2. Detaillierte Analyse nur innerhalb der Cluster (Intra-Cluster)
    3. Selektive Analyse zwischen Clustern nur für Brücken (Inter-Cluster)
    """
    
    def __init__(self, compare_func, rag_func=None):
        """
        Args:
            compare_func: Funktion zum Vergleichen zweier Dokumente
            rag_func: Optional - Funktion für RAG-Kontext
        """
        self.compare_documents = compare_func
        self.get_rag_context = rag_func
        self.logger = logger
    
    def analyze_with_clusters(self, 
                             kompetenz_results: List[KompetenzResult],
                             clusters: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Hauptmethode: Cluster-basierte Analyse statt n².
        
        Args:
            kompetenz_results: Liste der Kompetenz-Analysen
            clusters: Thematische Cluster {"Theme": ["doc1.pdf", "doc2.pdf"]}
            
        Returns:
            Dict mit relationships und Statistiken
        """
        self.logger.info(f" Cluster-basierte Analyse: {len(clusters)} Cluster, {len(kompetenz_results)} Dokumente")
        
        # Dokument-Lookup für schnellen Zugriff
        doc_lookup = {r.filename: r for r in kompetenz_results}
        
        # 1. INTRA-CLUSTER: Detaillierte Analyse innerhalb der Cluster
        self.logger.info(f"   Analysiere Intra-Cluster Beziehungen...")
        intra_relationships = self._analyze_intra_cluster(doc_lookup, clusters)
        
        # 2. INTER-CLUSTER: Selektive Brücken-Analyse
        self.logger.info(f"   Analysiere Inter-Cluster Brücken...")
        inter_relationships = self._analyze_inter_cluster(doc_lookup, clusters)
        
        # 3. Statistiken
        total_comparisons = len(intra_relationships) + len(inter_relationships)
        max_comparisons = len(kompetenz_results) * (len(kompetenz_results) - 1) // 2
        
        reduction_percent = ((max_comparisons - total_comparisons) / max_comparisons * 100) if max_comparisons > 0 else 0
        
        self.logger.info(f" Optimierung: {total_comparisons} Vergleiche statt {max_comparisons} (-{reduction_percent:.1f}%)")
        
        return {
            "relationships": intra_relationships + inter_relationships,
            "statistics": {
                "total_relationships": total_comparisons,
                "intra_cluster": len(intra_relationships),
                "inter_cluster": len(inter_relationships),
                "complexity_reduction": f"{reduction_percent:.1f}%",
                "clusters_analyzed": len(clusters)
            }
        }
    
    def _analyze_intra_cluster(self, 
                               doc_lookup: Dict[str, KompetenzResult],
                               clusters: Dict[str, List[str]]) -> List[Dict]:
        """
        Analysiert Beziehungen INNERHALB der Cluster.
        Hier sind detaillierte Vergleiche sinnvoll.
        """
        relationships = []
        
        for theme, doc_names in clusters.items():
            if len(doc_names) < 2:
                continue
            
            # Progress-Anzeige für größere Cluster
            if len(doc_names) > 3:
                self.logger.info(f"      Cluster '{theme}': {len(doc_names)} Dokumente")
            
            # Alle Paare innerhalb des Clusters
            for i, doc1_name in enumerate(doc_names):
                for doc2_name in doc_names[i+1:]:
                    if doc1_name in doc_lookup and doc2_name in doc_lookup:
                        result1 = doc_lookup[doc1_name]
                        result2 = doc_lookup[doc2_name]
                        
                        # Vollständige Analyse mit RAG
                        rel = self.compare_documents(result1, result2)
                        if rel:
                            rel['cluster'] = theme
                            rel['analysis_type'] = 'intra_cluster'
                            relationships.append(rel)
        
        self.logger.info(f"   {len(relationships)} Intra-Cluster Beziehungen gefunden")
        return relationships
    
    def _analyze_inter_cluster(self,
                               doc_lookup: Dict[str, KompetenzResult],
                               clusters: Dict[str, List[str]]) -> List[Dict]:
        """
        Analysiert Beziehungen ZWISCHEN Clustern.
        Nur wichtige Brücken-Dokumente.
        """
        relationships = []
        cluster_names = list(clusters.keys())
        
        for i, theme1 in enumerate(cluster_names):
            for theme2 in cluster_names[i+1:]:
                docs1 = clusters[theme1]
                docs2 = clusters[theme2]
                
                if not docs1 or not docs2:
                    continue
                
                # Strategie: Prüfe nur EINE potenzielle Brücke pro Cluster-Paar
                # Nur wenn beide Cluster groß genug sind für sinnvolle Brücken
                if len(docs1) == 1 or len(docs2) == 1:
                    # Skip single-doc clusters - werden schon in Intra-Cluster behandelt
                    continue
                    
                # Nur EINE Brücke: Letztes von Cluster1 -> Erstes von Cluster2
                bridge_candidates = [
                    (docs1[-1], docs2[0]),  # Ende Cluster1 -> Anfang Cluster2
                ]
                
                for doc1_name, doc2_name in bridge_candidates:
                    if doc1_name in doc_lookup and doc2_name in doc_lookup:
                        result1 = doc_lookup[doc1_name]
                        result2 = doc_lookup[doc2_name]
                        
                        # Strengere Kriterien für Inter-Cluster
                        rel = self._check_strong_bridge(result1, result2, theme1, theme2)
                        if rel:
                            relationships.append(rel)
                            self.logger.info(f"   Brücke: {theme1} → {theme2}")
                            break  # Eine starke Brücke reicht
        
        self.logger.info(f"   {len(relationships)} Inter-Cluster Brücken gefunden")
        return relationships
    
    def _check_strong_bridge(self, 
                            result1: KompetenzResult,
                            result2: KompetenzResult,
                            theme1: str,
                            theme2: str) -> Dict:
        """
        Prüft auf starke Brücken-Beziehungen zwischen Clustern.
        Höhere Schwelle als normale Beziehungen.
        """
        rel = self.compare_documents(result1, result2)
        
        if rel:
            strength = rel.get('strength', 0)
            rel_type = rel.get('type', '')
            
            # Nur sehr starke oder wichtige Beziehungen
            if strength > 0.75 or rel_type in ['PREREQUISITE', 'SEQUENCE']:
                rel['cluster_from'] = theme1
                rel['cluster_to'] = theme2
                rel['analysis_type'] = 'inter_cluster'
                rel['bridge'] = True
                return rel
        
        return None
    
    def get_cluster_summary(self, 
                           clusters: Dict[str, List[str]],
                           relationships: List[Dict]) -> Dict[str, Any]:
        """
        Erstellt eine Zusammenfassung der Cluster-Struktur.
        """
        cluster_stats = {}
        
        for theme, docs in clusters.items():
            # Zähle Beziehungen pro Cluster
            intra_count = len([r for r in relationships 
                             if r.get('cluster') == theme])
            
            # Finde verbundene Cluster
            connected_to = set()
            for r in relationships:
                if r.get('cluster_from') == theme:
                    connected_to.add(r.get('cluster_to'))
                elif r.get('cluster_to') == theme:
                    connected_to.add(r.get('cluster_from'))
            
            cluster_stats[theme] = {
                'document_count': len(docs),
                'internal_relationships': intra_count,
                'connected_clusters': list(connected_to),
                'is_isolated': len(connected_to) == 0
            }
        
        return cluster_stats