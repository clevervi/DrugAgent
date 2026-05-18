import hashlib
import os
import yaml

def deterministic_noise(smiles: str, scale: float = 1.0) -> float:
    """
    Genera una variación determinista ("ruido determinista") basada en el SMILES de la molécula.
    Garantiza reproducibilidad total eliminando la aleatoriedad física (random.uniform / random.gauss).
    Devuelve un float en el rango [-scale, scale].
    """
    if not smiles:
        return 0.0
    h = hashlib.md5(smiles.encode('utf-8')).hexdigest()
    # Tomar los primeros 8 caracteres hexadecimales y convertirlos a float normalizado [0.0, 1.0]
    val = int(h[:8], 16) / 0xffffffff
    # Mapear al rango [-scale, scale]
    return (val * 2.0 - 1.0) * scale

def load_scoring_weights() -> dict:
    """
    Carga los pesos de scoring y penalidades desde config/config.yaml.
    Si ocurre un error o el archivo no existe, retorna los pesos por defecto.
    """
    default_weights = {
        "docking": 0.50,
        "qed": 0.25,
        "toxicity": 0.25,
        "pains_penalty": 0.30,
        "brenk_penalty": 0.10
    }
    try:
        # Resolver ruta absoluta relativa a este archivo
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, "..", "config", "config.yaml")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                if config and "scoring_weights" in config:
                    return config["scoring_weights"]
    except Exception:
        pass
    return default_weights

def compute_final_score(mol_data: dict) -> float:
    """
    Calcula el score final combinado ponderado para el ranking de candidatos.
    Combina la afinidad de docking, drug-likeness (QED), toxicidad, y penaliza alertas.
    """
    weights = load_scoring_weights()
    
    docking = mol_data.get("docking_score", 0.0) or 0.0
    qed = mol_data.get("qed", 0.5)
    tox = mol_data.get("admet_toxicity", 0.5)
    pains = 1 if mol_data.get("pains_alert", False) else 0
    brenk = 1 if mol_data.get("brenk_alert", False) else 0
    
    # Normalizar docking: -12.0 kcal/mol -> 1.0, 0.0 kcal/mol -> 0.0
    docking_norm = min(1.0, abs(docking) / 12.0)
    
    w_docking = weights.get("docking", 0.50)
    w_qed = weights.get("qed", 0.25)
    w_toxicity = weights.get("toxicity", 0.25)
    p_pains = weights.get("pains_penalty", 0.30)
    p_brenk = weights.get("brenk_penalty", 0.10)
    
    # Suma ponderada principal
    score = (
        docking_norm * w_docking +
        qed * w_qed +
        (1.0 - tox) * w_toxicity
    )
    
    # Penalizaciones por alertas estructurales
    score -= pains * p_pains
    score -= brenk * p_brenk
    
    return max(0.0, score)
