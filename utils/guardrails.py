# Módulo de Guardrails Quimioinformáticos y Seguridad Estructural (DrugAgent-Local)
# Este módulo audita y valida las estructuras moleculares (SMILES) utilizando patrones SMARTS
# de RDKit para asegurar el cumplimiento ético, bioseguro y legal de las investigaciones.

import logging
from typing import Tuple, Dict
from rdkit import Chem

logger = logging.getLogger("DrugAgent.Guardrails")

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
