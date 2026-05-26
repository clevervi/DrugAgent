"""
SDF Exporter — exporta candidatos en formato SDF con propiedades embebidas.
Formato estándar para ChemDraw, Discovery Studio, Schrodinger, OpenBabel.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors


def export_to_sdf(
    candidates: List[dict],
    output_path: str,
    embed_3d: bool = True,
    top_n: Optional[int] = None,
) -> str:
    """
    Exporta candidatos a SDF con propiedades embebidas.

    Args:
        candidates: Lista de dicts con al menos 'smiles' y métricas.
        output_path: Ruta de salida (.sdf).
        embed_3d: Si True, genera conformero 3D con ETKDG.
        top_n: Si se especifica, solo exporta los top N por score.

    Returns:
        Ruta del archivo generado.
    """
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Ordenar por docking_score y filtrar
    sorted_cands = sorted(
        [c for c in candidates if c.get("smiles")],
        key=lambda x: x.get("docking_score", 0.0) or 0.0,
    )
    if top_n:
        sorted_cands = sorted_cands[:top_n]

    writer = Chem.SDWriter(str(out_path))

    exported = 0
    for c in sorted_cands:
        mol = Chem.MolFromSmiles(c["smiles"])
        if mol is None:
            continue

        # Propiedades en el archivo SDF
        mol.SetProp("_Name", c.get("mol_id", f"candidate_{exported}"))
        mol.SetProp("SMILES", c["smiles"])

        props = {
            "Docking_Score_kcal_mol": c.get("docking_score"),
            "QED": c.get("qed"),
            "MW": c.get("mw"),
            "LogP": c.get("logp"),
            "TPSA": c.get("tpsa"),
            "HBD": c.get("hbd"),
            "HBA": c.get("hba"),
            "SA_Score": c.get("sa_score"),
            "ADMET_Toxicity": c.get("admet_toxicity"),
            "ADMET_Absorption": c.get("admet_absorption"),
            "PAINS_Alert": str(c.get("pains_alert", False)),
            "Brenk_Alert": str(c.get("brenk_alert", False)),
            "Ligand_Efficiency": c.get("ligand_efficiency"),
            "Score_Final": c.get("score_final"),
            "Iteration": c.get("iteration"),
            "Status": c.get("status", ""),
        }
        for key, val in props.items():
            if val is not None:
                mol.SetProp(key, str(round(val, 4) if isinstance(val, float) else val))

        if embed_3d:
            try:
                mol_h = Chem.AddHs(mol)
                result = AllChem.EmbedMolecule(mol_h, AllChem.ETKDGv3())
                if result == 0:
                    AllChem.MMFFOptimizeMolecule(mol_h)
                    mol = Chem.RemoveHs(mol_h)
            except Exception:
                pass  # fallback to 2D

        writer.write(mol)
        exported += 1

    writer.close()
    print(f"   [SDF Export] {exported} candidatos exportados a {out_path}")
    return str(out_path)


def export_top_candidates_sdf(run_id: str, candidates: List[dict], top_n: int = 20) -> str:
    """Helper para exportar top candidatos al directorio de outputs del run."""
    out_dir = Path(f"output/sdf/{run_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"top_{top_n}_candidates.sdf"
    return export_to_sdf(candidates, str(output_path), embed_3d=True, top_n=top_n)
