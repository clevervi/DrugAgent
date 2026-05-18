"""
Cliente ligero para la API REST pública de ChEMBL (EBI).
Modo recomendado: API (sin descargar dump SQLite ~35GB).
Documentación: https://chembl.gitbook.io/chembl-interface-documentation/web-services
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

DEFAULT_BASE = "https://www.ebi.ac.uk/chembl/api/data"
ACTIVITY_TYPES = ("IC50", "Ki", "EC50", "Kd", "Potency")


def _get_json(url: str, timeout: float = 45.0) -> dict:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "DrugAgent-Local/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _cache_path(cache_dir: Path, key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)[:120]
    return cache_dir / f"{safe}.json"


def _cached_get(url: str, cache_dir: Optional[Path], cache_key: str, ttl_hours: float = 168.0) -> dict:
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = _cache_path(cache_dir, cache_key)
        if path.exists():
            age_h = (time.time() - path.stat().st_mtime) / 3600.0
            if age_h < ttl_hours:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
    data = _get_json(url)
    if cache_dir:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=0)
    return data


def search_target(query: str, limit: int = 5, cache_dir: Optional[Path] = None) -> List[dict]:
    q = quote(query.strip())
    url = f"{DEFAULT_BASE}/target/search.json?q={q}&limit={limit}"
    data = _cached_get(url, cache_dir, f"target_search_{q}_{limit}")
    return data.get("targets", []) or []


def resolve_target_chembl_id(
    target_name: str,
    evidence_cfg: Optional[dict] = None,
    cache_dir: Optional[Path] = None,
) -> Optional[str]:
    """Resuelve CHEMBL_ID usando catalog/evidence_targets.yaml o búsqueda directa."""
    queries = [target_name]
    if evidence_cfg:
        if evidence_cfg.get("chembl_search"):
            queries.insert(0, evidence_cfg["chembl_search"])
        for alt in evidence_cfg.get("alt_searches") or []:
            queries.append(alt)

    if evidence_cfg and evidence_cfg.get("chembl_target_id"):
        return str(evidence_cfg["chembl_target_id"]).strip()

    seen_ids = set()
    for q in queries:
        for hit in search_target(q, limit=8, cache_dir=cache_dir):
            tid = hit.get("target_chembl_id")
            if not tid or tid in seen_ids:
                continue
            seen_ids.add(tid)
            pref = (hit.get("target_type") or "").upper()
            if pref in ("SINGLE PROTEIN", "PROTEIN COMPLEX", "PROTEIN FAMILY", "CHIMERIC PROTEIN"):
                return tid
            if not evidence_cfg:
                return tid
        if seen_ids:
            return next(iter(seen_ids))
    return None


def fetch_activities(
    target_chembl_id: str,
    limit: int = 50,
    cache_dir: Optional[Path] = None,
) -> List[dict]:
    """Actividades con tipos estándar de afinidad; enriquece con SMILES vía molecule endpoint."""
    params = urlencode({
        "target_chembl_id": target_chembl_id,
        "limit": limit,
        "standard_type__in": ",".join(ACTIVITY_TYPES),
    })
    url = f"{DEFAULT_BASE}/activity.json?{params}"
    data = _cached_get(url, cache_dir, f"activity_{target_chembl_id}_{limit}")
    activities = data.get("activities", []) or []
    rows = []
    mol_cache: Dict[str, dict] = {}

    for act in activities:
        mol_id = act.get("molecule_chembl_id")
        if not mol_id:
            continue
        if mol_id not in mol_cache:
            mol_cache[mol_id] = fetch_molecule(mol_id, cache_dir=cache_dir)
        mol = mol_cache[mol_id]
        smiles = (mol.get("molecule_structures") or {}).get("canonical_smiles") or mol.get("pref_name", "")
        rows.append({
            "molecule_chembl_id": mol_id,
            "canonical_smiles": smiles,
            "standard_type": act.get("standard_type"),
            "standard_value": act.get("standard_value"),
            "standard_units": act.get("standard_units"),
            "pchembl_value": act.get("pchembl_value"),
            "assay_description": (act.get("assay_description") or "")[:200],
            "document_chembl_id": act.get("document_chembl_id"),
        })
    return rows


def fetch_molecule(molecule_chembl_id: str, cache_dir: Optional[Path] = None) -> dict:
    mid = quote(molecule_chembl_id.strip())
    url = f"{DEFAULT_BASE}/molecule/{mid}.json"
    return _cached_get(url, cache_dir, f"mol_{mid}")


def load_evidence_config_for_target(target_name: str) -> dict:
    import yaml
    path = Path("catalog/evidence_targets.yaml")
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        all_cfg = yaml.safe_load(f) or {}
    return all_cfg.get(target_name, {}) or {}
