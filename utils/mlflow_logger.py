"""
MLflow Telemetry Logger for DrugAgent.
Provides a robust, non-blocking wrapper to log molecular parameters, metrics, 
generated candidate tables, and PDBQT/PDF scientific artifacts.
"""

import os
import sys
import logging
import hashlib
import shutil
from pathlib import Path
import mlflow

# Windows UTF-8 console output encoding reconfiguration
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Initialize Logger
logger = logging.getLogger("DrugAgent.MLflow")

# Retrieve tracking URI from environment and configure MLflow
TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///./data/mlflow.db")
try:
    mlflow.set_tracking_uri(TRACKING_URI)
except Exception as e:
    logger.warning(f"⚠️ [MLflow Logger]: Failed to set default tracking URI: {e}")

EXPERIMENT_NAME = "DrugAgent-Discovery"
_active_run = None

def start_discovery_run(target_name: str, target_pdb_id: str, workflow_mode: str, 
                        therapeutic_area: str, indication_label: str, max_iterations: int,
                        db_run_id: str = None) -> str:
    """
    Starts a new MLflow run for tracking the molecular discovery process of DrugAgent.
    Logs high-level configurations and LLM choices.
    """
    global _active_run, EXPERIMENT_NAME
    try:
        experiment_prefix = "DrugAgent"
        # Load from config.yaml dynamically
        from pathlib import Path
        import yaml
        config_path = Path("config/config.yaml")
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                    if cfg and "mlflow" in cfg:
                        mlflow_cfg = cfg["mlflow"]
                        if not mlflow_cfg.get("enabled", True):
                            print("📈 [MLflow Logger]: Telemetry is disabled in config.yaml.")
                            return ""
                        experiment_prefix = mlflow_cfg.get("experiment_prefix", "DrugAgent")
                        uri = mlflow_cfg.get("tracking_uri", TRACKING_URI)
                        mlflow.set_tracking_uri(uri)
            except Exception as e:
                logger.warning(f"⚠️ [MLflow Logger]: Failed to parse config/config.yaml: {e}")

        EXPERIMENT_NAME = f"{experiment_prefix}/{therapeutic_area.strip()}/{target_name.strip()}"
        try:
            mlflow.set_experiment(EXPERIMENT_NAME)
        except Exception as e:
            logger.warning(f"⚠️ [MLflow Logger]: Could not set dynamic experiment '{EXPERIMENT_NAME}': {e}")
            mlflow.set_experiment("DrugAgent-Discovery")

        run_name = f"Discover_{target_name}_{target_pdb_id}"
        _active_run = mlflow.start_run(run_name=run_name)
        
        # Log system hyper-parameters
        mlflow.log_param("target_name", target_name)
        mlflow.log_param("target_pdb_id", target_pdb_id)
        mlflow.log_param("workflow_mode", workflow_mode)
        mlflow.log_param("therapeutic_area", therapeutic_area)
        mlflow.log_param("indication_label", indication_label)
        mlflow.log_param("max_iterations", max_iterations)
        
        if db_run_id:
            mlflow.log_param("prisma_run_id", db_run_id)
        
        # Log configured models in environment
        mlflow.log_param("groq_heavy_model", os.environ.get("GROQ_HEAVY_MODEL", "llama-3.3-70b-versatile"))
        mlflow.log_param("groq_light_model", os.environ.get("GROQ_LIGHT_MODEL", "llama-3.1-8b-instant"))
        mlflow.log_param("gemini_heavy_model", os.environ.get("GEMINI_HEAVY_MODEL", "gemini-2.5-flash"))
        mlflow.log_param("gemini_light_model", os.environ.get("GEMINI_LIGHT_MODEL", "gemini-2.5-flash-lite"))
        mlflow.log_param("vina_mode", os.environ.get("VINA_MODE", "windows"))
        
        print(f"📈 [MLflow Logger]: Run initialized. Experiment: '{EXPERIMENT_NAME}'")
        return _active_run.info.run_id
    except Exception as e:
        print(f"⚠️ [MLflow Logger]: Failed to start MLflow run: {e}")
        return ""

def log_iteration_metrics(iteration: int, metrics: dict):
    """
    Logs performance metrics and drug-likeness progress per iteration step.
    """
    if not mlflow.active_run():
        return
    try:
        from pathlib import Path
        import yaml
        config_path = Path("config/config.yaml")
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                    if cfg and "mlflow" in cfg:
                        mlflow_cfg = cfg["mlflow"]
                        if not mlflow_cfg.get("enabled", True) or not mlflow_cfg.get("log_every_iteration", True):
                            return
            except Exception:
                pass
        
        for name, value in metrics.items():
            if value is not None:
                mlflow.log_metric(name, float(value), step=iteration)
    except Exception as e:
        logger.warning(f"⚠️ [MLflow Logger]: Failed to log iteration metrics: {e}")

def log_candidates_table(candidates: list):
    """
    Saves and logs the list of generated molecular candidates as a tabular CSV file artifact.
    """
    if not candidates:
        return
    try:
        import pandas as pd
        df = pd.DataFrame(candidates)
        if not df.empty:
            # Create a clean data/dock_tmp directory if it doesn't exist
            temp_dir = Path("data/dock_tmp")
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = temp_dir / "temp_candidates.csv"
            
            # Save DF to CSV
            df.to_csv(temp_path, index=False, encoding="utf-8")
            mlflow.log_artifact(str(temp_path), artifact_path="molecules")
            try:
                temp_path.unlink()
            except Exception:
                pass
    except Exception as e:
        print(f"⚠️ [MLflow Logger]: Error logging candidates table to MLflow: {e}")

def end_discovery_run(status: str, best_score: float = None, best_smiles: str = None, 
                      total_candidates: int = 0, duration_sec: float = 0.0, 
                      error_message: str = None, top_candidates: list = None,
                      insights_count: int = 0, skills_count: int = 0):
    """
    Concludes the active MLflow run, logging final evaluation metrics, generated reports, 
    and the docked 3D PDBQT poses.
    """
    global _active_run
    if not mlflow.active_run():
        return
        
    try:
        # Log metrics of evaluation
        mlflow.log_metric("total_candidates", total_candidates)
        mlflow.log_metric("duration_sec", duration_sec)
        mlflow.log_metric("insights_count", insights_count)
        mlflow.log_metric("skills_count", skills_count)
        
        if best_score is not None:
            mlflow.log_metric("best_docking_score", best_score)
            mlflow.log_metric("best_binding_affinity_abs", abs(best_score))
            
        if best_smiles:
            mlflow.log_param("best_smiles", best_smiles[:250])
            
        if error_message:
            mlflow.log_param("error_message", error_message[:250])
            
        # Log top molecular candidates as a CSV table
        if top_candidates:
            log_candidates_table(top_candidates)
            
            # Copy and attach the 3D PDBQT conformer of the best candidate
            if best_smiles:
                md5_hash = hashlib.md5(best_smiles.encode("utf-8")).hexdigest()
                best_pose_path = Path(f"data/docked_poses/lig_{md5_hash}.pdbqt")
                if best_pose_path.exists():
                    print(f"   💾 [MLflow Logger]: Copying best docked 3D pose to MLflow artifacts: {best_pose_path.name}")
                    mlflow.log_artifact(str(best_pose_path), artifact_path="docked_poses")
                    
        # Log generated PDF report, results JSON, and the stdout execution log file
        report_json = Path("output/results.json")
        if report_json.exists():
            mlflow.log_artifact(str(report_json), artifact_path="reports")
            
        report_pdf = Path("output/DrugAgent_Report.pdf")
        if report_pdf.exists():
            mlflow.log_artifact(str(report_pdf), artifact_path="reports")
            
        agent_log = Path("output/agent.log")
        if agent_log.exists():
            mlflow.log_artifact(str(agent_log), artifact_path="logs")
            
        # Finalize run with appropriate status
        if status.lower() == "completed":
            mlflow.end_run(status="FINISHED")
            print("📈 [MLflow Logger]: MLflow active run completed and closed (FINISHED).")
        else:
            mlflow.end_run(status="FAILED")
            print("📈 [MLflow Logger]: MLflow active run completed and closed (FAILED).")
            
    except Exception as e:
        print(f"⚠️ [MLflow Logger]: Exception while ending MLflow run: {e}")
        try:
            mlflow.end_run(status="FAILED")
        except Exception:
            pass
    finally:
        _active_run = None
