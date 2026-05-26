"""
DrugAgent State Definition
Define el estado compartido del grafo LangGraph.
"""
from typing import TypedDict, Annotated, List, Optional, Dict, Any
import operator
from dataclasses import dataclass, field
from datetime import datetime


class MoleculeCandidate(TypedDict):
    """Candidato molecular con sus métricas."""
    smiles: str
    mol_id: str
    iteration: int
    # Métricas físico-químicas
    mw: float           # Molecular weight
    logp: float         # Lipophilicity
    hbd: int            # H-bond donors
    hba: int            # H-bond acceptors
    tpsa: float         # Topological polar surface area
    qed: float          # Quantitative Estimate of Drug-likeness
    # Métricas de docking
    docking_score: Optional[float]    # kcal/mol (más negativo = mejor)
    binding_affinity: Optional[float]
    # Métricas ADMET básicas
    admet_toxicity: Optional[float]
    admet_solubility: Optional[str]
    admet_absorption: Optional[float]
    # Métricas ADMET avanzadas
    herg_risk: Optional[float]        # Riesgo cardiotóxico hERG [0-1]
    bbb_permeability: Optional[float] # Permeabilidad barrera hematoencefálica [0-1]
    cyp3a4_inhibition: Optional[float]# Inhibición CYP3A4 [0-1]
    # Filtros de seguridad
    pains_alert: bool
    brenk_alert: bool
    passes_lipinski: bool
    # Síntesis y eficiencia
    sa_score: Optional[float]         # Synthetic accessibility [1-10]
    ligand_efficiency: Optional[float]# LE = docking_score / heavy_atoms
    # Dinámica Molecular / Conformacional (MMFF94 proxy)
    md_rmsd: Optional[float]
    md_refined_score: Optional[float]
    md_strain_energy: Optional[float] # Energía strain MMFF94 [kcal/mol]
    md_flexibility: Optional[str]     # "rigid" | "flexible" | "highly_flexible"
    # Estado
    status: str   # "generated", "filtered", "docked", "analyzed", "md_simulated", "approved", "rejected"
    score_final: Optional[float]
    uncertainty: Optional[float]


class AgentState(TypedDict):
    """Estado completo del agente LangGraph."""
    
    # ── Configuración ──────────────────────────────
    target_name: str               # ej. "EGFR"
    target_pdb_id: str             # ej. "4HJO"
    target_pdb_path: str           # Ruta local al archivo PDB
    target_pdbqt_path: str         # Ruta PDBQT preparado
    iteration: int                 # Iteración actual
    max_iterations: int            # Máximo de iteraciones
    
    # ── Moléculas ──────────────────────────────────
    # Acumulador: agrega candidatos de cada iteración
    all_candidates: Annotated[List[MoleculeCandidate], operator.add]
    current_batch: List[MoleculeCandidate]   # Lote actual
    top_candidates: List[MoleculeCandidate]  # Mejores hasta ahora
    
    # ── Métricas de progreso ───────────────────────
    best_score: float              # Mejor docking score hasta ahora
    avg_score_history: Annotated[List[float], operator.add]
    diversity_score: float         # Diversidad del pool actual
    
    # ── Memoria y Skills ──────────────────────────
    active_skills: List[str]       # Nombres de skills cargadas
    skill_content: Dict[str, str]  # Contenido de cada skill
    memory_context: str            # Contexto recuperado de ChromaDB
    priority_scaffolds: Annotated[List[str], operator.add] # Scaffolds priorizados por el Reflector
    skill_failures: Optional[Dict[str, str]] # Registro temporal de fallos de skills en la iteración actual

    
    # ── Logs y Reflección ─────────────────────────
    iteration_logs: Annotated[List[str], operator.add]
    failures: Annotated[List[str], operator.add]
    insights: Annotated[List[str], operator.add]
    new_skills_generated: Annotated[List[str], operator.add]
    
    # ── Control de flujo ──────────────────────────
    next_action: str               # "generate", "simulate", "analyze", "reflect", "output", "end"
    error_count: int
    requires_human_review: bool
    
    # ── Metadata y Workflow ──────────────────────────
    start_time: str
    last_updated: str
    run_id: str
    docking_mode: Optional[str]
    workflow_mode: Optional[str]       # "de_novo" o "lead_opt"
    therapeutic_area: Optional[str]
    indication_label: Optional[str]
    parent_smiles: Optional[str]
