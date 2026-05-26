"""
Matched Molecular Pairs (MMP) Analysis — SAR mining sobre candidatos acumulados.
Agrupa por scaffold Murcko, identifica qué cambios estructurales mejoran el docking score.
"""
from __future__ import annotations

from typing import List, Dict, Tuple
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit.Chem import Descriptors, rdFingerprintGenerator
from rdkit import DataStructs


def _murcko(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return ""
    try:
        return Chem.MolToSmiles(MurckoScaffold.GetScaffoldForMol(mol))
    except Exception:
        return ""


def _heavy_atom_diff(smi_a: str, smi_b: str) -> int:
    """Diferencia en número de átomos pesados (proxy de cambio estructural)."""
    ma = Chem.MolFromSmiles(smi_a)
    mb = Chem.MolFromSmiles(smi_b)
    if ma is None or mb is None:
        return 99
    return abs(ma.GetNumHeavyAtoms() - mb.GetNumHeavyAtoms())


def analyze_mmps(candidates: List[dict]) -> str:
    """
    Analiza pares moleculares emparejados para extraer insight SAR.

    Retorna un string con las observaciones más relevantes para inyectar
    al contexto del reflector LLM.
    """
    valid = [
        c for c in candidates
        if c.get("smiles") and c.get("docking_score") is not None
    ]
    if len(valid) < 5:
        return ""

    # Agrupar por scaffold Murcko
    groups: Dict[str, List[dict]] = {}
    for c in valid:
        sc = _murcko(c["smiles"])
        if sc:
            groups.setdefault(sc, []).append(c)

    insights: List[str] = []

    for scaffold, group in groups.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: x.get("docking_score", 0.0))
        best = group[0]
        worst = group[-1]
        delta = (worst.get("docking_score", 0.0) or 0.0) - (best.get("docking_score", 0.0) or 0.0)
        if abs(delta) < 0.3:
            continue

        best_qed = best.get("qed", 0.0) or 0.0
        best_tox = best.get("admet_toxicity", 0.5) or 0.5
        insights.append(
            f"Scaffold [{scaffold[:35]}]: "
            f"mejor score={best['docking_score']:.2f} kcal/mol (QED={best_qed:.2f}, tox={best_tox:.2f}) "
            f"vs peor={worst['docking_score']:.2f} | Δ={delta:.2f} kcal/mol en {len(group)} análogos."
        )

    # Top 5 insights por delta
    insights.sort(key=lambda x: float(x.split("Δ=")[1].split(" ")[0]) if "Δ=" in x else 0, reverse=True)

    if not insights:
        return ""

    header = "=== MMP SAR ANALYSIS ===\n"
    return header + "\n".join(insights[:5])


def identify_best_substituents(candidates: List[dict]) -> str:
    """
    Identifica correlaciones entre propiedades físicoquímicas y docking score.
    Reporta qué rango de logP, MW, QED correlaciona con mejores scores.
    """
    valid = [
        c for c in candidates
        if c.get("docking_score") is not None and c.get("smiles")
    ]
    if len(valid) < 10:
        return ""

    sorted_by_score = sorted(valid, key=lambda x: x.get("docking_score", 0.0))
    top25 = sorted_by_score[:max(3, len(sorted_by_score) // 4)]
    bottom25 = sorted_by_score[-max(3, len(sorted_by_score) // 4):]

    def avg(lst, key):
        vals = [x.get(key, 0) or 0 for x in lst if x.get(key) is not None]
        return sum(vals) / len(vals) if vals else 0.0

    top_logp = avg(top25, "logp")
    top_mw = avg(top25, "mw")
    top_qed = avg(top25, "qed")
    bot_logp = avg(bottom25, "logp")
    bot_mw = avg(bottom25, "mw")

    lines = [
        "=== CORRELACIONES FISICOQUIMICAS SAR ===",
        f"Top 25% binders: logP={top_logp:.2f}, MW={top_mw:.0f}, QED={top_qed:.2f}",
        f"Bottom 25% binders: logP={bot_logp:.2f}, MW={bot_mw:.0f}",
    ]
    if top_logp > bot_logp + 0.3:
        lines.append("=> Mayor lipofilia correlaciona con mejor binding en este target.")
    elif bot_logp > top_logp + 0.3:
        lines.append("=> Menor lipofilia (mas polar) correlaciona con mejor binding.")
    if top_mw < bot_mw - 20:
        lines.append("=> Moleculas mas pequenas (menor MW) tienen mejor ligand efficiency.")

    return "\n".join(lines)
