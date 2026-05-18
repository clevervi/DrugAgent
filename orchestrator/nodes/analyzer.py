"""
Nodo Analyzer: Filtros ADMET, PAINS, Brenk + scoring final.
Determina qué candidatos pasan a revisión humana.
"""
from datetime import datetime
from typing import List
import json
import os
import sys

from rdkit import Chem
from rdkit.Chem import Descriptors, QED, Crippen, rdMolDescriptors
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

try:
    from utils import sascorer
except ImportError:
    try:
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
        from utils import sascorer
    except ImportError:
        import rdkit
        sys.path.append(os.path.join(os.path.dirname(rdkit.__file__), 'Contrib', 'SA_Score'))
        try:
            import sascorer
        except ImportError:
            print("Warning: sascorer not found.")
            sascorer = None

from ..state import AgentState, MoleculeCandidate


def setup_pains_filter():
    """Inicializa el filtro PAINS de RDKit."""
    params = FilterCatalogParams()
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
    return FilterCatalog(params)


def setup_brenk_filter():
    """Inicializa el filtro Brenk de RDKit."""
    params = FilterCatalogParams()
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.BRENK)
    return FilterCatalog(params)


# Inicializar filtros una vez (caching)
_PAINS_CATALOG = None
_BRENK_CATALOG = None


def get_pains_catalog():
    global _PAINS_CATALOG
    if _PAINS_CATALOG is None:
        _PAINS_CATALOG = setup_pains_filter()
    return _PAINS_CATALOG


def get_brenk_catalog():
    global _BRENK_CATALOG
    if _BRENK_CATALOG is None:
        _BRENK_CATALOG = setup_brenk_filter()
    return _BRENK_CATALOG


def predict_toxicity_simple(mol) -> float:
    """
    Predictor de toxicidad simple basado en reglas moleculares.
    Score 0 = muy seguro, 1 = muy tóxico.
    En Fase 2 se reemplaza con modelo ADMET real.
    """
    if mol is None:
        return 1.0
    
    tox_score = 0.0
    
    # Alertas estructurales básicas
    mw = Descriptors.ExactMolWt(mol)
    logp = Crippen.MolLogP(mol)
    hbd = rdMolDescriptors.CalcNumHBD(mol)
    tpsa = rdMolDescriptors.CalcTPSA(mol)
    
    # Penalizaciones
    if mw > 550: tox_score += 0.2
    if logp > 5.5: tox_score += 0.2    # Alta lipofilia → toxicidad
    if logp < 0: tox_score += 0.1      # Muy hidrofílico
    if hbd > 5: tox_score += 0.1
    if tpsa > 160: tox_score += 0.1
    
    # Grupos funcionales tóxicos comunes
    toxic_patterns = [
        "N(=O)=O",          # Nitro groups
        "[N+](=O)[O-]",     # Nitro groups alt
        "C(=O)Cl",          # Acid chlorides
        "C(F)(F)F",         # Trifluoromethyl (many)
        "[SH]",             # Thiol
    ]
    
    for pattern in toxic_patterns:
        try:
            patt = Chem.MolFromSmarts(pattern)
            if patt and mol.HasSubstructMatch(patt):
                tox_score += 0.15
        except:
            pass
    
    return min(1.0, tox_score)


from utils.scoring import compute_final_score


def analyzer_node(state: AgentState) -> dict:
    """Nodo analizador: aplica filtros ADMET, PAINS, Brenk y calcula score final."""
    
    import sys
    sys.path.append("utils")
    from utils.ml_admet import MLADMETPredictor
    
    admet_predictor = MLADMETPredictor(use_ml_models=True)
    
    iteration = state.get("iteration", 0)
    current_batch = state.get("current_batch", [])
    
    print(f"\n[Iter {iteration}] 🔍 ANALYZER: Aplicando filtros de seguridad y ADMET...")
    
    if not current_batch:
        return {
            "next_action": "reflect",
            "iteration_logs": [f"[Iter {iteration}] Analyzer: lote vacío"],
        }
    
    pains_catalog = get_pains_catalog()
    brenk_catalog = get_brenk_catalog()
    
    analyzed_batch = []
    approved_count = 0
    rejected_pains = 0
    rejected_brenk = 0
    rejected_tox = 0
    rejected_sa = 0
    rejected_guardrail = 0
    
    for mol_data in current_batch:
        mol_data = dict(mol_data)
        smiles = mol_data["smiles"]
        
        # ── Guardrail de Bioprotección ───────────────────────
        from utils.guardrails import validate_molecular_safety
        is_safe, safety_reason = validate_molecular_safety(smiles)
        mol_data["is_safe"] = is_safe
        mol_data["safety_reason"] = safety_reason
        
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            mol_data["status"] = "rejected"
            analyzed_batch.append(mol_data)
            continue
        
        # ── Filtro PAINS ─────────────────────────────────────
        pains_hit = pains_catalog.GetFirstMatch(mol)
        mol_data["pains_alert"] = pains_hit is not None
        
        # ── Filtro Brenk ─────────────────────────────────────
        brenk_hit = brenk_catalog.GetFirstMatch(mol)
        mol_data["brenk_alert"] = brenk_hit is not None
        
        # ── Toxicidad predicha ────────────────────────────────
        tox = predict_toxicity_simple(mol)
        mol_data["admet_toxicity"] = round(tox, 3)
        
        # Solubilidad estimada (LogP proxy)
        logp = mol_data.get("logp", 3.0)
        if logp < 1: mol_data["admet_solubility"] = "high"
        elif logp < 3: mol_data["admet_solubility"] = "moderate"
        elif logp < 5: mol_data["admet_solubility"] = "low"
        else: mol_data["admet_solubility"] = "very_low"
        
        # ── Nuevas Métricas: SA Score y Ligand Efficiency ────────────────
        if sascorer:
            try:
                mol_data["sa_score"] = round(sascorer.calculateScore(mol), 3)
            except:
                mol_data["sa_score"] = 10.0
        else:
            mol_data["sa_score"] = 1.0
            
        heavy_atoms = mol.GetNumHeavyAtoms()
        docking = mol_data.get("docking_score", 0.0)
        if heavy_atoms > 0 and docking and docking < 0:
            mol_data["ligand_efficiency"] = round(docking / heavy_atoms, 4)
        else:
            mol_data["ligand_efficiency"] = 0.0

        # Predicción ADMET mediante MLADMETPredictor
        mol_data["admet_toxicity"] = admet_predictor.predict_toxicity(smiles)
        mol_data["admet_absorption"] = admet_predictor.predict_absorption(smiles)
        
        # Score final recalculado con la toxicidad refinada de MLADMETPredictor y pesos de config
        mol_data["score_final"] = round(compute_final_score(mol_data), 4)
        
        # Penalizar SA (Synthetic Accessibility) >= 6
        sa_score = mol_data.get("sa_score", 0.0)
        
        # Decisión de Aprobación
        tox = mol_data.get("admet_toxicity", 1.0)
        
        if not is_safe:
            mol_data["status"] = "rejected_guardrail"
            rejected_guardrail += 1
        elif mol_data["pains_alert"]:
            mol_data["status"] = "rejected_pains"
            rejected_pains += 1
        elif tox > 0.6:
            mol_data["status"] = "rejected_toxicity"
            rejected_tox += 1
        elif mol_data.get("sa_score", 0) > 4.5:
            mol_data["status"] = "rejected_sascore"
            rejected_sa += 1
        elif mol_data.get("docking_score") and mol_data["docking_score"] > -5.0:
            mol_data["status"] = "weak_binder"
        else:
            mol_data["status"] = "analyzed"
            approved_count += 1
        
        if mol_data.get("brenk_alert") and mol_data["status"] == "analyzed":
            mol_data["status"] = "analyzed_brenk_warn"
        
        analyzed_batch.append(mol_data)
    
    # Filtrar candidatos para revisión humana
    # Cargar min_docking_score de config.yaml
    min_docking_score = -7.0
    import yaml
    try:
        with open("./config/config.yaml") as f:
            cfg = yaml.safe_load(f)
        min_docking_score = cfg.get("thresholds", {}).get("min_docking_score", -7.0)
    except Exception:
        pass

    # No comparar mock con el umbral rígido real de Vina (-7.0 kcal/mol)
    docking_mode = state.get("docking_mode", "real")
    effective_docking_threshold = min_docking_score if docking_mode == "real" else -5.5
    print(f"   ℹ️ Aplicando umbral de docking efectivo: {effective_docking_threshold} kcal/mol (Modo: {docking_mode})")

    # Solo pasan: docking score < effective_docking_threshold, sin PAINS, toxicidad < 0.3, SA Score <= 4.5, y seguras
    high_quality = [
        m for m in analyzed_batch
        if (m.get("docking_score") or 0) < effective_docking_threshold
        and not m.get("pains_alert", True)
        and (m.get("admet_toxicity") or 1.0) < 0.3
        and (m.get("sa_score", 10.0) <= 4.5)
        and m.get("is_safe", True)
    ]
    
    requires_review = len(high_quality) >= 3  # Revisar cuando hay al menos 3 buenos
    
    print(f"[Iter {iteration}] ✓ Análisis completado:")
    print(f"   Aprobados: {approved_count} | PAINS: {rejected_pains} | Tox alta: {rejected_tox} | SA Difícil: {rejected_sa} | Guardrail: {rejected_guardrail}")
    print(f"   Alta calidad (gate): {len(high_quality)} candidatos")
    
    # === ACTUALIZACIÓN DE ESTADO Y DEDUPLICACIÓN ===
    all_prev = state.get("all_candidates", [])
    combined = all_prev + analyzed_batch
    
    # Deduplicar por SMILES manteniendo el candidato con mejor docking score (más negativo)
    seen = {}
    for c in combined:
        smi = c["smiles"]
        score = c.get("docking_score", 0.0) or 0.0
        if smi not in seen or score < (seen[smi].get("docking_score", 0.0) or 0.0):
            seen[smi] = c
            
    unique_combined = list(seen.values())
    unique_combined.sort(key=lambda x: x.get("docking_score", 0.0) or 0.0)
    
    top_candidates = unique_combined[:10]
    top_dashboard = unique_combined[:20]
    
    # === GUARDADO EN VIVO PARA EL DASHBOARD (PRISMA) ===
    try:
        from ..db import db, init_db
        init_db()
        
        run_id = state.get("run_id")
        
        # Upsert candidates en la base de datos
        for c in top_dashboard:
            # Asegurar que los datos no son None para evitar errores de Prisma
            score_final = c.get("score_final")
            score_final = float(score_final) if score_final is not None else 0.0
            
            db.candidate.upsert(
                where={
                    'run_id_smiles': {
                        'run_id': run_id,
                        'smiles': c["smiles"]
                    }
                },
                data={
                    'create': {
                        'run_id': run_id,
                        'smiles': c["smiles"],
                        'mol_id': c["mol_id"],
                        'iteration': iteration,
                        'mw': float(c.get("mw", 0)),
                        'logp': float(c.get("logp", 0)),
                        'hbd': int(c.get("hbd", 0)),
                        'hba': int(c.get("hba", 0)),
                        'tpsa': float(c.get("tpsa", 0)),
                        'qed': float(c.get("qed", 0)),
                        'docking_score': c.get("docking_score"),
                        'binding_affinity': c.get("binding_affinity"),
                        'admet_toxicity': c.get("admet_toxicity"),
                        'admet_solubility': c.get("admet_solubility"),
                        'admet_absorption': c.get("admet_absorption"),
                        'pains_alert': bool(c.get("pains_alert", False)),
                        'brenk_alert': bool(c.get("brenk_alert", False)),
                        'passes_lipinski': bool(c.get("passes_lipinski", False)),
                        'sa_score': float(c.get("sa_score", 0)),
                        'ligand_efficiency': float(c.get("ligand_efficiency", 0)),
                        'score_final': score_final,
                        'status': c.get("status", "analyzed")
                    },
                    'update': {
                        'iteration': iteration,
                        'docking_score': c.get("docking_score"),
                        'binding_affinity': c.get("binding_affinity"),
                        'admet_toxicity': c.get("admet_toxicity"),
                        'admet_solubility': c.get("admet_solubility"),
                        'pains_alert': bool(c.get("pains_alert", False)),
                        'brenk_alert': bool(c.get("brenk_alert", False)),
                        'sa_score': float(c.get("sa_score", 0)),
                        'ligand_efficiency': float(c.get("ligand_efficiency", 0)),
                        'score_final': score_final,
                        'status': c.get("status", "analyzed")
                    }
                }
            )
    except Exception as e:
        print(f"Error guardando en Prisma DB en vivo: {e}")
    # ==========================================

    # === Log metrics to MLflow iter-by-iter ===
    try:
        try:
            from utils.mlflow_logger import log_iteration_metrics
        except ImportError:
            sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
            from utils.mlflow_logger import log_iteration_metrics

        if log_iteration_metrics:
            scores = [c.get("docking_score") for c in analyzed_batch if c.get("docking_score") is not None]
            best_iter_score = min(scores) if scores else 0.0
            
            tox_vals = [float(c.get("admet_toxicity", 0.0)) for c in analyzed_batch if c.get("admet_toxicity") is not None]
            avg_tox = sum(tox_vals) / len(tox_vals) if tox_vals else 0.0
            
            qed_vals = [float(c.get("qed", 0.0)) for c in analyzed_batch if c.get("qed") is not None]
            avg_qed = sum(qed_vals) / len(qed_vals) if qed_vals else 0.0

            metrics_dict = {
                "batch_size": len(analyzed_batch),
                "best_score": best_iter_score,
                "approved_count": approved_count,
                "high_quality_count": len(high_quality),
                "rejected_pains": rejected_pains,
                "rejected_tox": rejected_tox,
                "rejected_sa": rejected_sa,
                "avg_toxicity": avg_tox,
                "avg_qed": avg_qed
            }
            log_iteration_metrics(iteration, metrics_dict)
            print(f"📈 [Telemetry]: Logged iteration {iteration} metrics to MLflow.")
    except Exception as e:
        print(f"⚠️ [Telemetry]: Error logging iteration metrics: {e}")
    # ==========================================

    return {
        "current_batch": analyzed_batch,
        "all_candidates": analyzed_batch,  # Añade este lote al acumulador del estado
        "top_candidates": top_candidates,  # Sobreescribe con el ranking histórico completo y limpio
        "requires_human_review": requires_review,
        "next_action": "output" if requires_review else "reflect",
        "iteration_logs": [
            f"[Iter {iteration}] Analyzer: {approved_count} aprobados, "
            f"{rejected_pains} PAINS, {rejected_tox} tox, {rejected_sa} bad SA, {len(high_quality)} alta calidad"
        ],
        "last_updated": datetime.now().isoformat(),
    }
