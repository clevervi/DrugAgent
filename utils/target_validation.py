"""
Validación y corrección de pares target / PDB contra el catálogo curado de DrugAgent.
Evita corridas con combinaciones incoherentes (p. ej. PD-L1 + 4HJO que es EGFR).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import yaml

_CATALOG_PATH = Path("catalog/therapeutic_areas.yaml")

# Alias de nombres que devuelven los LLM → clave del catálogo
_TARGET_ALIASES: Dict[str, str] = {
    "PDL1": "PD_L1",
    "PD-L1": "PD_L1",
    "PD_L1": "PD_L1",
    "MPRO": "MPRO",
    "M-PRO": "MPRO",
    "3CLPRO": "MPRO",
    "SARS-COV-2 MPRO": "MPRO",
    "SARS-COV-2 MAIN PROTEASE": "MPRO",
    "COVID MPRO": "MPRO",
    "HIV PROTEASE": "HIV1PR",
    "HIV-1 PROTEASE": "HIV1PR",
    "KRAS G12C": "KRAS",
    "KRAS G12D": "KRAS",
    "DPP-4": "DPP4",
    "DENV NS3": "DENV_NS3",
    "ZIKA NS3": "ZIKV_NS3",
    "ZIKV NS3": "ZIKV_NS3",
    "RSV F": "RSV_F",
}


@dataclass
class ResolvedTarget:
    target_name: str
    pdb_id: str
    warnings: List[str] = field(default_factory=list)
    corrected: bool = False


def normalize_target_name(name: str) -> str:
    if not name:
        return ""
    raw = str(name).strip().upper().replace(" ", "_").replace("-", "_")
    while "__" in raw:
        raw = raw.replace("__", "_")
    return _TARGET_ALIASES.get(raw, _TARGET_ALIASES.get(name.strip().upper(), raw))


def load_target_pdb_registry() -> Dict[str, Set[str]]:
    """target normalizado -> PDB IDs válidos del catálogo."""
    registry: Dict[str, Set[str]] = {}
    if _CATALOG_PATH.is_file():
        with open(_CATALOG_PATH, encoding="utf-8") as f:
            catalog = yaml.safe_load(f) or {}
        for _key, entry in catalog.items():
            if not isinstance(entry, dict):
                continue
            target = normalize_target_name(entry.get("target", ""))
            pdb = str(entry.get("pdb_id", "")).strip().upper()
            if target and pdb:
                registry.setdefault(target, set()).add(pdb)
    # Pool autónomo (por si falta en YAML)
    _POOL = [
        ("EGFR", "4HJO"),
        ("DPP4", "3HAJ"),
        ("MPRO", "6LU7"),
        ("DENV_NS3", "2M9P"),
        ("ZIKV_NS3", "7VLI"),
        ("RSV_F", "5C6B"),
        ("BACE1", "1W50"),
        ("HIV1PR", "1HSG"),
        ("KRAS", "6VXX"),
        ("PD_L1", "3K33"),
    ]
    for target, pdb in _POOL:
        registry.setdefault(target, set()).add(pdb)
    return registry


def resolve_target_pdb(
    target_name: str,
    pdb_id: str,
    *,
    strict: bool = False,
) -> ResolvedTarget:
    """
    Corrige PDB si no coincide con el target en catálogo.
    Si el PDB pertenece a otro target conocido, remapea el nombre del target.
    """
    registry = load_target_pdb_registry()
    warnings: List[str] = []
    target_norm = normalize_target_name(target_name)
    pdb_norm = str(pdb_id or "").strip().upper()

    if len(pdb_norm) != 4:
        msg = f"PDB ID inválido: '{pdb_id}' (se esperan 4 caracteres)"
        if strict:
            raise ValueError(msg)
        warnings.append(msg)
        return ResolvedTarget(target_norm or "UNKNOWN", pdb_norm, warnings, corrected=True)

    valid_pdbs = registry.get(target_norm)
    if valid_pdbs:
        if pdb_norm in valid_pdbs:
            return ResolvedTarget(target_norm, pdb_norm, warnings, corrected=False)
        canonical = sorted(valid_pdbs)[0]
        warnings.append(
            f"PDB '{pdb_norm}' no corresponde a {target_norm} en catálogo; "
            f"usando '{canonical}' ({', '.join(sorted(valid_pdbs))} válidos)."
        )
        return ResolvedTarget(target_norm, canonical, warnings, corrected=True)

    # Target desconocido: inferir por PDB
    owners = [t for t, pdbs in registry.items() if pdb_norm in pdbs]
    if len(owners) == 1:
        warnings.append(
            f"Target '{target_name}' no está en catálogo; PDB {pdb_norm} pertenece a {owners[0]}."
        )
        return ResolvedTarget(owners[0], pdb_norm, warnings, corrected=True)
    if len(owners) > 1:
        warnings.append(
            f"PDB {pdb_norm} ambiguo entre {owners}; usando {owners[0]}."
        )
        return ResolvedTarget(owners[0], pdb_norm, warnings, corrected=True)

    if strict:
        raise ValueError(
            f"Target '{target_name}' / PDB '{pdb_norm}' no están en catalog/therapeutic_areas.yaml"
        )
    warnings.append(
        f"Par {target_norm}/{pdb_norm} no curado; la corrida continúa sin validación estructural estricta."
    )
    return ResolvedTarget(target_norm, pdb_norm, warnings, corrected=False)


def validate_mission_dict(mission: dict, *, strict: bool = False) -> dict:
    """Normaliza un dict de misión autónoma (target, pdb_id, ...)."""
    resolved = resolve_target_pdb(
        mission.get("target", ""),
        mission.get("pdb_id", ""),
        strict=strict,
    )
    for w in resolved.warnings:
        print(f"   [WARN] Validación target/PDB: {w}")
    out = dict(mission)
    out["target"] = resolved.target_name
    out["pdb_id"] = resolved.pdb_id
    return out
