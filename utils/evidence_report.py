"""
Genera paquete de evidencia pública (ChEMBL) y comparación con candidatos DrugAgent.
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.chembl_client import (
    fetch_activities,
    load_evidence_config_for_target,
    resolve_target_chembl_id,
)


def _load_evidence_settings() -> dict:
    import yaml
    defaults = {
        "enabled": True,
        "mode": "api",
        "activity_limit": 50,
        "cache_dir": "data/evidence/cache",
        "output_dir": "data/evidence",
    }
    try:
        with open("config/config.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        ev = cfg.get("evidence") or {}
        defaults.update({k: v for k, v in ev.items() if v is not None})
    except Exception:
        pass
    return defaults


def _max_tanimoto(query_smiles: str, reference_smiles_list: List[str]) -> Optional[float]:
    try:
        from rdkit import Chem
        from rdkit import DataStructs
        from rdkit.Chem import rdFingerprintGenerator

        qmol = Chem.MolFromSmiles(query_smiles)
        if qmol is None:
            return None
        gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
        qfp = gen.GetFingerprint(qmol)
        best = 0.0
        for smi in reference_smiles_list:
            if not smi or not isinstance(smi, str):
                continue
            rmol = Chem.MolFromSmiles(smi)
            if rmol is None:
                continue
            rfp = gen.GetFingerprint(rmol)
            sim = DataStructs.TanimotoSimilarity(qfp, rfp)
            if sim > best:
                best = sim
        return round(best, 3)
    except Exception:
        return None


def generate_evidence_pack(
    target_name: str,
    target_pdb_id: str,
    top_candidates: List[dict],
    run_id: str,
    therapeutic_area: str = "",
    indication_label: str = "",
) -> Dict[str, Any]:
    """
    Descarga actividades ChEMBL, guarda CSV + informe MD, opcionalmente artefactos MLflow.
    Retorna dict con paths y metadatos (o error).
    """
    settings = _load_evidence_settings()
    if not settings.get("enabled", True):
        print("   [INFO] Evidencia deshabilitado en config.yaml (evidence.enabled=false).")
        return {"skipped": True, "reason": "disabled"}

    mode = (settings.get("mode") or "api").lower()
    if mode == "sqlite":
        print("   [WARN] Evidencia: mode=sqlite no implementado. Usa evidence.mode=api en config.yaml.")
        return {"skipped": True, "reason": "sqlite_not_implemented"}

    out_root = Path(settings.get("output_dir", "data/evidence"))
    run_dir = out_root / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(settings.get("cache_dir", "data/evidence/cache"))
    limit = int(settings.get("activity_limit", 50))

    evidence_cfg = load_evidence_config_for_target(target_name)
    print(f"\n[Evidencia ChEMBL] Resolviendo target '{target_name}' (PDB {target_pdb_id})...")

    try:
        chembl_tid = resolve_target_chembl_id(target_name, evidence_cfg, cache_dir=cache_dir)
        if not chembl_tid:
            msg = f"No se encontró target ChEMBL para '{target_name}'."
            print(f"   [WARN] {msg}")
            return {"skipped": True, "reason": "target_not_found", "message": msg}

        print(f"   [OK] ChEMBL target: {chembl_tid}")
        activities = fetch_activities(chembl_tid, limit=limit, cache_dir=cache_dir)
        if not activities:
            print("   [WARN] Sin actividades IC50/Ki/EC50 en ChEMBL para este blanco.")

        csv_path = run_dir / "chembl_reference_activities.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            if activities:
                writer = csv.DictWriter(f, fieldnames=list(activities[0].keys()))
                writer.writeheader()
                writer.writerows(activities)
            else:
                f.write("molecule_chembl_id,canonical_smiles,standard_type,standard_value,standard_units\n")

        ref_smiles = [
            r["canonical_smiles"] for r in activities
            if r.get("canonical_smiles") and "SMILES" not in str(r.get("canonical_smiles", "")).upper()[:20]
        ]

        comparison_lines = [
            "# Informe de evidencia pública — DrugAgent",
            "",
            f"- **Fecha:** {datetime.now().isoformat(timespec='seconds')}",
            f"- **Run ID:** {run_id}",
            f"- **Target:** {target_name} | **PDB:** {target_pdb_id}",
            f"- **Área / indicación:** {therapeutic_area} — {indication_label}",
            f"- **ChEMBL target ID:** {chembl_tid}",
            f"- **Actividades de referencia descargadas:** {len(activities)} (tipos: IC50, Ki, EC50, Kd, Potency)",
            "",
            "## Fuentes",
            "- [ChEMBL](https://www.ebi.ac.uk/chembl/) — actividades bioquímicas curadas",
            "- [RCSB PDB](https://www.rcsb.org/) — estructura del receptor",
            "- [WHO R&D Blueprint](https://www.who.int/activities/prioritizing-diseases-for-research-and-development-in-emergency-contexts) — priorización sanitaria (contexto, no consulta automática)",
            "",
            "## Aviso metodológico",
            "Los scores de docking de DrugAgent (kcal/mol) **no son directamente comparables** con IC50/Ki de ChEMBL (nM/µM).",
            "Este informe usa **similitud estructural (Tanimoto)** frente a ligandos con actividad publicada como contexto químico.",
            "",
            "## Candidatos DrugAgent vs referencias ChEMBL",
            "",
            "| Rank | SMILES (truncado) | Docking (kcal/mol) | QED | Tox proxy | Max Tanimoto vs ref. ChEMBL |",
            "|------|-------------------|--------------------|-----|-----------|---------------------------|",
        ]

        sorted_cands = sorted(
            top_candidates,
            key=lambda x: x.get("docking_score", 0.0) or 0.0,
        )[:10]

        for i, cand in enumerate(sorted_cands, 1):
            smi = cand.get("smiles", "")
            smi_short = (smi[:42] + "…") if len(smi) > 45 else smi
            dock = cand.get("docking_score", "N/A")
            qed = cand.get("qed", "N/A")
            tox = cand.get("admet_toxicity", "N/A")
            tani = _max_tanimoto(smi, ref_smiles) if ref_smiles else None
            tani_s = f"{tani:.3f}" if tani is not None else "N/A"
            comparison_lines.append(
                f"| {i} | `{smi_short}` | {dock} | {qed} | {tox} | {tani_s} |"
            )

        comparison_lines.extend([
            "",
            "## Interpretación (guía)",
            "- **Tanimoto > 0.35** hacia un inhibidor conocido: química en espacio similar (revisar patentes / novedad).",
            "- **Tanimoto < 0.25** con muchas referencias: posible scaffold más novedoso (mayor riesgo, mayor oportunidad).",
            "- Siguiente paso experimental sugerido: ensayo enzimático o celular contra el mismo blanco, no solo más docking.",
            "",
            "## Referencias ChEMBL (muestra, mejores pChEMBL)",
            "",
        ])

        by_pchembl = sorted(
            [a for a in activities if a.get("pchembl_value") is not None],
            key=lambda x: float(x["pchembl_value"]),
            reverse=True,
        )[:15]
        for a in by_pchembl:
            comparison_lines.append(
                f"- {a.get('molecule_chembl_id')}: {a.get('standard_type')} = {a.get('standard_value')} {a.get('standard_units')} "
                f"(pChEMBL {a.get('pchembl_value')}); SMILES `{str(a.get('canonical_smiles', ''))[:50]}`"
            )

        md_path = run_dir / "evidence_comparison_report.md"
        md_path.write_text("\n".join(comparison_lines), encoding="utf-8")

        meta = {
            "target_name": target_name,
            "target_pdb_id": target_pdb_id,
            "chembl_target_id": chembl_tid,
            "n_activities": len(activities),
            "n_candidates_compared": len(sorted_cands),
            "generated_at": datetime.now().isoformat(),
        }
        meta_path = run_dir / "evidence_meta.json"
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"   Evidencia guardada en: {run_dir}")
        print(f"      - {csv_path.name}")
        print(f"      - {md_path.name}")

        _log_mlflow_artifacts(run_dir, csv_path, md_path, meta_path)

        return {
            "success": True,
            "run_dir": str(run_dir),
            "csv_path": str(csv_path),
            "report_path": str(md_path),
            "meta_path": str(meta_path),
            "chembl_target_id": chembl_tid,
            "meta": meta,
        }

    except Exception as e:
        print(f"   [WARN] Evidencia ChEMBL: Error ({e}). La corrida continua sin paquete de evidencia.")
        return {"skipped": True, "reason": "error", "message": str(e)}


def _log_mlflow_artifacts(run_dir: Path, csv_path: Path, md_path: Path, meta_path: Path) -> None:
    try:
        import mlflow
        if not mlflow.active_run():
            return
        mlflow.log_artifact(str(csv_path), artifact_path="evidence")
        mlflow.log_artifact(str(md_path), artifact_path="evidence")
        mlflow.log_artifact(str(meta_path), artifact_path="evidence")
        print("   [MLflow] Artefactos de evidencia registrados en evidence/")
    except Exception as e:
        print(f"   [WARN] MLflow: No se pudieron subir artefactos de evidencia: {e}")
