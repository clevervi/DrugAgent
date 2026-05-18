"""
MD Simulator Node — proxy de estabilidad (no OpenMM/GROMACS).
Ajusta scores con RMSD sintético determinista; etiquetar como in silico en informes.
"""
from ..state import AgentState
from utils.scoring import deterministic_noise
import time

def md_simulator_node(state: AgentState) -> dict:
    """
    Ejecuta simulaciones de Dinámica Molecular cortas sobre los mejores candidatos
    para confirmar la estabilidad del complejo Ligando-Receptor.
    """
    print("🌊 [MD Simulator] Evaluando estabilidad conformacional...")
    
    top_candidates = state.get("top_candidates", [])
    if not top_candidates:
        return {"next_action": "reflect"}
        
    # Aquí iría el setup de OpenMM
    # Para desarrollo, implementamos un proxy de simulación
    simulated_candidates = []
    for idx, c in enumerate(top_candidates):
        # Simular una caída en la afinidad debido a fluctuaciones térmicas (RMSD)
        docking_score = c.get("docking_score")
        base_score = float(docking_score) if docking_score is not None else 0.0
        smiles = c.get("smiles", "")
        
        # Proxy RMSD (Root Mean Square Deviation) de la pose tras 1ns (simulado y determinista)
        rmsd = round(2.25 + deterministic_noise(smiles, scale=1.25), 2)
        
        # Si el RMSD es alto (> 2.5), la pose es inestable y el score empeora
        stability_penalty = 0.0
        if rmsd > 2.5:
            stability_penalty = round(1.25 + deterministic_noise(smiles + "_stability", scale=0.75), 2)
            
        md_score = round(base_score + stability_penalty, 2)
        
        c["md_rmsd"] = rmsd
        c["md_refined_score"] = md_score
        simulated_candidates.append(c)
        
        print(f"    - Mol_{c.get('mol_id', idx)}: RMSD={rmsd}A -> Score Refinado={md_score:.2f}")
        
        # Guardar en Prisma SQLite en vivo
        try:
            from ..db import db, init_db
            init_db()
            run_id = state.get("run_id")
            if run_id:
                db.candidate.update(
                    where={
                        'run_id_smiles': {
                            'run_id': run_id,
                            'smiles': c["smiles"]
                        }
                    },
                    data={
                        'md_rmsd': float(rmsd),
                        'md_refined_score': float(md_score)
                    }
                )
        except Exception as e:
            print(f"    ⚠️ Error actualizando MD en Prisma DB: {e}")
        
    return {
        "top_candidates": simulated_candidates,
        "next_action": "reflect"
    }
