#!/usr/bin/env python3
"""
DrugAgent - Entry point principal.
Corre el loop cerrado completo de drug discovery.
"""
import sys
import io
import os
import argparse

import logging

# Configurar logging a archivo
os.makedirs("output", exist_ok=True)
log_file = "output/agent.log"
# Limpiar el log viejo si existe al inicio
with open(log_file, 'w', encoding='utf-8') as f:
    f.write("Iniciando DrugAgent...\n")

class DualLogger:
    def __init__(self, filepath, stream):
        self.filepath = filepath
        self.stream = stream

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()
        with open(self.filepath, 'a', encoding='utf-8') as f:
            f.write(data)

    def flush(self):
        self.stream.flush()
        
    def fileno(self):
        return self.stream.fileno()

sys.stdout = DualLogger(log_file, io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace'))
sys.stderr = DualLogger(log_file, io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace'))

# Cargar .env
from dotenv import load_dotenv
load_dotenv('.env')

# Asegurar API key si no estamos en OFFLINE_MODE ni con LOCAL_LLM_BASE_URL
offline_mode = os.environ.get('OFFLINE_MODE', 'False').lower() in ['true', '1', 'yes']
local_llm_base = os.environ.get('LOCAL_LLM_BASE_URL', '').strip()

if not offline_mode and not local_llm_base:
    groq_key = os.environ.get('GROQ_API_KEY', '').strip()
    gemini_key = os.environ.get('GEMINI_API_KEY', '').strip()
    
    has_groq = groq_key and not groq_key.startswith('gsk_REEMPLAZA')
    has_gemini = gemini_key and not gemini_key.startswith('AIzaSy_REEMPLAZA')
    
    if not (has_groq or has_gemini):
        raise ValueError(
            "❌ ERROR DE SEGURIDAD: No se ha detectado ninguna API Key válida (Groq o Gemini) en su archivo .env.\n"
            "Para ejecutar de forma 100% local, configure OFFLINE_MODE=True o especifique LOCAL_LLM_BASE_URL."
        )


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DrugAgent - Closed-Loop Drug Discovery")
    parser.add_argument("--target", default="EGFR", help="Target terapeutico (default: EGFR)")
    parser.add_argument("--pdb", default="4HJO", help="PDB ID de la proteina (default: 4HJO)")
    parser.add_argument("--iterations", type=int, default=10, help="Numero de iteraciones (default: 10)")
    parser.add_argument("--workflow", default="de_novo", choices=["de_novo", "lead_opt"], help="Workflow mode (de_novo o lead_opt)")
    parser.add_argument("--area", default="Oncología", help="Area terapeutica (ej. Oncologia, Diabetes Tipo 2, SARS-CoV-2)")
    parser.add_argument("--indication", default="Cáncer de Pulmón (EGFR)", help="Indicacion clinica detallada")
    parser.add_argument("--parent-smiles", default=None, help="SMILES padre de partida para lead_opt")
    args = parser.parse_args()

    from core.docking import validate_pdb_id
    if not validate_pdb_id(args.pdb):
        raise ValueError(
            f"❌ ERROR: El ID de PDB '{args.pdb}' especificado no es válido o no existe en RCSB PDB.\n"
            f"Por favor, verifique el ID del receptor e intente de nuevo."
        )

    from utils.target_validation import resolve_target_pdb
    resolved = resolve_target_pdb(args.target, args.pdb)
    for w in resolved.warnings:
        print(f"   [WARN] {w}")
    args.target = resolved.target_name
    args.pdb = resolved.pdb_id

    from orchestrator.graph import run_agent
    from orchestrator.db import db, init_db
    import json
    
    # Crear el Run en la base de datos con los nuevos campos
    init_db()
    run_record = db.run.create(
        data={
            "target_name": args.target,
            "target_pdb_id": args.pdb,
            "max_iterations": args.iterations,
            "status": "running",
            "workflow_mode": args.workflow,
            "therapeutic_area": args.area,
            "indication_label": args.indication,
            "parent_smiles": args.parent_smiles
        }
    )
    
    # Inyectar run_id y workflows al graph
    import time
    from datetime import datetime
    start_time = time.time()
    
    config_dict = {
        "target": args.target,
        "pdb": args.pdb,
        "iterations": args.iterations,
        "workflow": args.workflow,
        "area": args.area,
        "indication": args.indication,
        "parent_smiles": args.parent_smiles,
        "timestamp": datetime.now().isoformat()
    }
    config_snapshot_json = json.dumps(config_dict)
    
    from utils.mlflow_logger import start_discovery_run, end_discovery_run
    
    result = None
    try:
        # Guardar config snapshot inicial
        db.run.update(
            where={"id": run_record.id},
            data={"config_snapshot": config_snapshot_json}
        )
        
        # Iniciar telemetría de MLflow
        mlflow_run_id = start_discovery_run(
            target_name=args.target,
            target_pdb_id=args.pdb,
            workflow_mode=args.workflow,
            therapeutic_area=args.area,
            indication_label=args.indication,
            max_iterations=args.iterations,
            db_run_id=run_record.id
        )
        
        # Enlazar mlflow_run_id en Prisma DB
        if mlflow_run_id:
            db.run.update(
                where={"id": run_record.id},
                data={"mlflow_run_id": mlflow_run_id}
            )
        
        result = run_agent(
            target_name=args.target,
            target_pdb_id=args.pdb,
            max_iterations=args.iterations,
            db_run_id=run_record.id,
            workflow_mode=args.workflow,
            therapeutic_area=args.area,
            indication_label=args.indication,
            parent_smiles=args.parent_smiles
        )
        
        # Finalizar el Run en la DB exitosamente
        duration = time.time() - start_time
        docking_mode = result.get("docking_mode", "mock") if isinstance(result, dict) else "mock"
        db.run.update(
            where={"id": run_record.id},
            data={
                "status": "completed",
                "end_time": datetime.now(),
                "docking_mode": docking_mode,
                "duration_sec": duration
            }
        )
        print(f"\n💾 Corrida {run_record.id} ({docking_mode}) finalizada exitosamente en Prisma DB en {duration:.1f}s.")
        
        # Finalizar telemetría de MLflow con éxito
        best_score = result.get("best_score", 0.0) if isinstance(result, dict) else 0.0
        top_candidates = result.get("top_candidates", []) if isinstance(result, dict) else []
        best_smiles = top_candidates[0].get("smiles", "") if top_candidates else ""
        total_candidates = len(result.get("all_candidates", [])) if isinstance(result, dict) else 0
        insights_count = len(result.get("insights", [])) if isinstance(result, dict) else 0
        skills_count = len(result.get("new_skills_generated", [])) if isinstance(result, dict) else 0
        
        # Paquete de evidencia pública (ChEMBL) antes de cerrar MLflow
        try:
            from utils.evidence_report import generate_evidence_pack
            generate_evidence_pack(
                target_name=args.target,
                target_pdb_id=args.pdb,
                top_candidates=top_candidates,
                run_id=run_record.id,
                therapeutic_area=args.area,
                indication_label=args.indication,
            )
        except Exception as ev_err:
            print(f"⚠️ Evidencia ChEMBL omitida: {ev_err}")

        end_discovery_run(
            status="completed",
            best_score=best_score,
            best_smiles=best_smiles,
            total_candidates=total_candidates,
            duration_sec=duration,
            top_candidates=top_candidates,
            insights_count=insights_count,
            skills_count=skills_count
        )
        
    except Exception as e:
        import traceback
        print(f"❌ FALLO CRÍTICO EN EL AGENTE: {e}")
        duration = time.time() - start_time
        
        # Finalizar telemetría de MLflow con fallo
        end_discovery_run(
            status="failed",
            error_message=f"{str(e)}\n\n{traceback.format_exc()}",
            duration_sec=duration
        )
        
        try:
            db.run.update(
                where={"id": run_record.id},
                data={
                    "status": "failed",
                    "end_time": datetime.now(),
                    "error_message": f"{str(e)}\n\n{traceback.format_exc()}",
                    "duration_sec": duration
                }
            )
            print(f"💾 Corrida {run_record.id} marcada como FALLIDA en Prisma DB.")
        except Exception as db_err:
            print(f"⚠️ No se pudo registrar el fallo en Prisma DB: {db_err}")
        raise e
    finally:
        from orchestrator.db import close_db
        close_db()
    
    # Generar el PDF final
    try:
        from utils.pdf_generator import generate_pdf_report
        generate_pdf_report(run_id=run_record.id)
    except Exception as e:
        print(f"Error generando PDF: {e}")
