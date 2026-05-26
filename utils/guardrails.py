# Módulo de Guardrails Quimioinformáticos y Seguridad Estructural (DrugAgent-Local)
# Este módulo audita y valida las estructuras moleculares (SMILES) utilizando patrones SMARTS
# de RDKit para asegurar el cumplimiento ético, bioseguro y legal de las investigaciones.

import logging
from typing import Tuple, Dict
from rdkit import Chem

logger = logging.getLogger("DrugAgent.Guardrails")

# ─── Perfiles de filtrado molecular ───────────────────────────────────────────
# standard: Ro5 estricto, PAINS bloquea, tox < 0.6, SA <= 4.5
# permissive: Ro5 relajado (MW≤800), PAINS solo advierte, tox < 0.8, SA <= 6.0
# cns: tuned para BBB (MW<450, TPSA<90, logP 0-5), PAINS advierte
# natural_products: MW hasta 1000, SA <= 6.5, compatible con macrolidos
FILTER_PROFILES: Dict[str, dict] = {
    "standard": {
        "max_mw": 500, "max_logp": 5.0, "min_logp": -10.0,
        "max_hbd": 5, "max_hba": 10, "max_tpsa": 140.0, "max_rotbonds": 10,
        "pains_block": True, "brenk_block": False,
        "max_toxicity": 0.6, "max_sa_score": 4.5, "high_quality_max_tox": 0.3,
    },
    "permissive": {
        "max_mw": 800, "max_logp": 7.0, "min_logp": -10.0,
        "max_hbd": 10, "max_hba": 15, "max_tpsa": 200.0, "max_rotbonds": 15,
        "pains_block": False, "brenk_block": False,
        "max_toxicity": 0.8, "max_sa_score": 6.0, "high_quality_max_tox": 0.6,
    },
    "cns": {
        "max_mw": 450, "max_logp": 5.0, "min_logp": 0.0,
        "max_hbd": 3, "max_hba": 7, "max_tpsa": 90.0, "max_rotbonds": 8,
        "pains_block": False, "brenk_block": False,
        "max_toxicity": 0.6, "max_sa_score": 5.0, "high_quality_max_tox": 0.4,
    },
    "natural_products": {
        "max_mw": 1000, "max_logp": 7.0, "min_logp": -10.0,
        "max_hbd": 10, "max_hba": 20, "max_tpsa": 250.0, "max_rotbonds": 20,
        "pains_block": False, "brenk_block": False,
        "max_toxicity": 0.7, "max_sa_score": 6.5, "high_quality_max_tox": 0.5,
    },
}


def load_filter_profile() -> dict:
    """Carga el perfil de filtrado desde config/config.yaml. Fallback a 'standard'."""
    try:
        import yaml
        from pathlib import Path
        cfg_path = Path("config/config.yaml")
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            name = cfg.get("filter_profile", "standard")
            profile = FILTER_PROFILES.get(name, FILTER_PROFILES["standard"])
            logger.debug(f"Perfil de filtrado activo: '{name}'")
            return profile
    except Exception as e:
        logger.warning(f"No se pudo cargar perfil de filtrado: {e}")
    return FILTER_PROFILES["standard"]

# Catálogo de Patrones SMARTS Restringidos (Sustancias Controladas, Toxinas y Amenazas Químicas)
RESTRICTED_PATTERNS: Dict[str, str] = {
    "fentanyl_like_core": "c1ccccc1CCN2CCC(N(c3ccccc3)C(=O)[*,C])CC2",  # Esqueleto de piperidina-fenetilo-anilida (fentanilo y derivados)
    "cocaine_like_core": "COC(=O)C1C(OC(=O)c2ccccc2)CC3CCC1N3C",        # Anillo de tropano con benzoiloxi y metoxicarbonilo (cocaína y derivados)
    "mustard_gas_derivatives": "ClCC[S,s,N,n]CCCl",                      # Mostazas de azufre o nitrógeno (agentes vesicantes)
    "organophosphorous_threats": "[P,p](=O)(F)([C,c,N,n])[O,s,o,S]",      # Organofosforados fluorados (esqueleto tipo Sarín/Somán - neurotóxicos)
    "morphinan_opioids": "c1ccc2c3c1oc1c4c(ccc13)CCC1C4CC2N1",           # Morfinanos (heroína, morfina y derivados opioides peligrosos)
}

def validate_molecular_safety(smiles: str) -> Tuple[bool, str]:
    """
    Valida un SMILES molecular frente al catálogo de patrones SMARTS restringidos.
    
    Args:
        smiles (str): Cadena SMILES a evaluar.
        
    Returns:
        Tuple[bool, str]: (is_safe, reason)
                          is_safe: True si la molécula es segura, False si viola algún guardrail.
                          reason: Mensaje explicativo o 'Safe'.
    """
    if not smiles:
        return False, "SMILES vacío o inválido"
        
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return False, f"Estructura SMILES no válida químicamente: '{smiles}'"
            
        # Comparar con cada patrón SMARTS restringido
        for name, smarts in RESTRICTED_PATTERNS.items():
            pattern = Chem.MolFromSmarts(smarts)
            if pattern is None:
                logger.warning(f"Patrón SMARTS inválido en guardrails: {name} ({smarts})")
                continue
                
            if mol.HasSubstructMatch(pattern):
                reason = f"VIOLACIÓN DE BIOCONTROL: Coincidencia detectada con el esqueleto químico restringido '{name}'."
                logger.warning(f"🚨 Guardrail de Seguridad Activado: Molécula '{smiles}' contiene '{name}'")
                return False, reason
                
        return True, "Safe"
        
    except Exception as e:
        logger.error(f"Error durante la validación de seguridad de '{smiles}': {e}")
        return False, f"Error en validador de seguridad: {e}"
