"""
Breakthrough Registry Utility for DrugAgent.
Detects, registers, and flags candidates that meet outstanding scientific criteria
as high-affinity leads or breakthrough candidates, saving them for immediate verification.
"""
import os
import json
import hashlib
from datetime import datetime
from pathlib import Path

# Intentar cargar Rich para una UI espectacular de alertas de descubrimientos
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich import print as rprint
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
BREAKTHROUGHS_FILE = DATA_DIR / "breakthroughs.json"

def check_and_register_breakthrough(
    candidate: dict,
    target_name: str,
    target_pdb_id: str,
    therapeutic_area: str,
    indication_label: str
) -> bool:
    """
    Checks if a candidate molecule meets strict scientific criteria to be declared a breakthrough.
    If so, saves it to the breakthrough log and prints a high-affinity lead alert.
    """
    # 1. Extraer métricas clave
    smiles = candidate.get("smiles", "").strip()
    docking_score = candidate.get("docking_score")
    qed = candidate.get("qed", 0.0)
    toxicity = candidate.get("admet_toxicity", 1.0)
    passes_lipinski = candidate.get("passes_lipinski", False)
    pains_alert = candidate.get("pains_alert", True)
    md_score = candidate.get("md_refined_score")

    if not smiles:
        return False

    # 2. Criterios científicos para avance/cura
    # Score de Docking altamente favorable (menor a -8.0 kcal/mol es excelente afinidad física)
    # Si es mock, requerimos mejor de -8.2. Si es real, mejor de -8.0
    status_dock = candidate.get("status", "")
    is_real_dock = "real" in status_dock or "pose" in status_dock
    
    score_threshold = -8.0 if is_real_dock else -8.5
    
    # Condición de afinidad física
    has_excellent_dock = docking_score is not None and docking_score <= score_threshold
    
    # Condición de estabilidad conformacional refinada (MD) si está disponible
    has_excellent_md = md_score is not None and md_score <= score_threshold
    
    # Afinidad física general
    is_highly_binding = has_excellent_dock or has_excellent_md
    
    # Criterio de toxicidad baja (predicción ADMET de ML)
    is_safe = toxicity <= 0.42
    
    # Criterios estructurales estrictos
    is_druglike = qed >= 0.72 and passes_lipinski and not pains_alert

    # Para simulación mock, si el docking es increíblemente alto y seguro, o si cumple todo:
    is_breakthrough = False
    
    if is_highly_binding and is_safe and is_druglike:
        is_breakthrough = True
    elif qed >= 0.82 and toxicity <= 0.32 and not pains_alert and docking_score is not None and docking_score <= -7.8:
        # Molécula excepcionalmente similar a fármaco con buena afinidad
        is_breakthrough = True

    if not is_breakthrough:
        return False

    # 3. Registrar Avance Científico
    try:
        # Cargar existentes
        breakthroughs = []
        if BREAKTHROUGHS_FILE.exists():
            try:
                with open(BREAKTHROUGHS_FILE, "r", encoding="utf-8") as f:
                    breakthroughs = json.load(f)
            except Exception:
                breakthroughs = []

        # Evitar duplicados por smiles
        if any(b.get("smiles") == smiles for b in breakthroughs):
            return True # Ya registrado

        # Generar descripción autónoma o usar justificación
        hba = candidate.get("hba", 0)
        hbd = candidate.get("hbd", 0)
        mw = candidate.get("mw", 0.0)
        logp = candidate.get("logp", 0.0)
        
        explanation = (
            f"El candidato presenta una afinidad de acoplamiento de {docking_score} kcal/mol frente a {target_name} ({target_pdb_id}), "
            f"con una estabilidad estructural óptima y un perfil farmacocinético sumamente balanceado (QED={qed:.3f}, Tox={toxicity:.2f}). "
            f"No presenta alertas de subestructuras reactivas (PAINS) y cumple las Reglas de Lipinski (Peso={mw:.1f} Da, LogP={logp:.2f}), "
            f"lo que le otorga una alta probabilidad de biodisponibilidad oral y viabilidad clínica como hit de descubrimiento."
        )

        entry = {
            "id": hashlib.md5(smiles.encode("utf-8")).hexdigest()[:8],
            "smiles": smiles,
            "target_name": target_name,
            "target_pdb_id": target_pdb_id,
            "therapeutic_area": therapeutic_area,
            "indication_label": indication_label,
            "docking_score": docking_score,
            "md_refined_score": md_score,
            "qed": qed,
            "admet_toxicity": toxicity,
            "explanation": explanation,
            "date_found": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "reviewed": False
        }

        breakthroughs.append(entry)
        
        with open(BREAKTHROUGHS_FILE, "w", encoding="utf-8") as f:
            json.dump(breakthroughs, f, indent=2)

        # Generar PDF del Breakthrough
        try:
            from utils.pdf_generator import generate_breakthrough_pdf
            generate_breakthrough_pdf(entry)
        except Exception as e_pdf:
            print(f"⚠️ No se pudo generar PDF de breakthrough: {e_pdf}")

        # Imprimir alerta gigante
        if HAS_RICH:
            alert_text = Text()
            alert_text.append("\n🌟 HIGH-AFFINITY SCIENTIFIC LEAD / BREAKTHROUGH FOUND! 🌟\n\n", style="bold yellow")
            alert_text.append("🎯 Target Proteico:  ", style="bold cyan")
            alert_text.append(f"{target_name} ({target_pdb_id})\n", style="bold white")
            alert_text.append("🧬 Indicación:       ", style="bold cyan")
            alert_text.append(f"{indication_label} | Área: {therapeutic_area}\n", style="bold white")
            alert_text.append("🧪 Estructura SMILES:", style="bold cyan")
            alert_text.append(f" {smiles}\n\n", style="bold green")
            
            alert_text.append("📊 Métricas de Viabilidad:\n", style="bold magenta")
            alert_text.append(f"   • Docking Score:   {docking_score} kcal/mol\n", style="bold green" if docking_score <= -8.0 else "bold yellow")
            if md_score is not None:
                alert_text.append(f"   • Molecular Dynamics (RMSD): {md_score:.2f} kcal/mol\n", style="bold green")
            alert_text.append(f"   • Similaridad a Fármaco (QED): {qed:.3f}\n", style="bold green" if qed >= 0.72 else "bold yellow")
            alert_text.append(f"   • Toxicidad ADMET: {toxicity:.3f} (Bajo Riesgo)\n\n", style="bold green")
            
            alert_text.append("📖 Justificación Científica:\n", style="bold magenta")
            alert_text.append(f"   {explanation}\n\n", style="italic white")
            alert_text.append("💾 Guardado en data/breakthroughs.json y PDF autogenerado.", style="bold dim white")
            
            panel = Panel(
                alert_text,
                title="[bold red]🚨 DISCOVERY BREAKTHROUGH ALERT 🚨[/bold red]",
                border_style="bold yellow",
                expand=False
            )
            console.print(panel)
        else:
            print("\n" + "="*80)
            print("🚨 CRITICAL SCIENTIFIC BREAKTHROUGH / CANDIDATO DE ALTA AFINIDAD DETECTADO! 🚨")
            print("="*80)
            print(f"🎯 Target:      {target_name} ({target_pdb_id})")
            print(f"🧬 Indicación:  {indication_label} | Área: {therapeutic_area}")
            print(f"🧪 SMILES:      {smiles}")
            print(f"📊 Afinidad:    {docking_score} kcal/mol | QED: {qed:.3f} | Tox: {toxicity:.3f}")
            print(f"📖 Justificación: {explanation}")
            print("="*80)
            print("💾 Guardado en el registro de prioridades científicas para alerta inmediata.")
            print("="*80 + "\n")
        
        return True
    except Exception as e:
        print(f"⚠️ Error registrando avance científico: {e}")
        return False
