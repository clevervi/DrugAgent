#!/usr/bin/env python3
"""
DrugAgent - Bucle de Descubrimiento Autónomo Infinito.
El agente decide por sí mismo qué enfermedad y blanco terapéutico atacar a continuación,
descarga los PDBs de RCSB PDB, calcula el sitio activo del ligando nativo, corre
simulaciones completas y alerta cuando haya candidatos in silico prioritarios (no es cura clínica).
"""
import sys
import os
import io
import time
import json
import random
from pathlib import Path
from datetime import datetime

# Configurar logging dual para Streamlit y consola
os.makedirs("output", exist_ok=True)
log_file = "output/agent.log"
with open(log_file, 'w', encoding='utf-8') as f:
    f.write("Iniciando Bucle Autonomo de DrugAgent...\n")

class DualLogger:
    def __init__(self, filepath, stream):
        self.filepath = filepath
        self.stream = stream

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()
        # Eliminar secuencias ANSI de color para el archivo de logs
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_data = ansi_escape.sub('', data)
        try:
            with open(self.filepath, 'a', encoding='utf-8') as f:
                f.write(clean_data)
        except Exception:
            pass

    def flush(self):
        self.stream.flush()
        
    def fileno(self):
        return self.stream.fileno()

# Solucionar problemas de codificacion Unicode en Windows y configurar DualLogger
if sys.platform == 'win32':
    # En Windows, reconfiguramos el buffer usando TextIOWrapper con utf-8
    sys.stdout = DualLogger(log_file, io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace'))
    sys.stderr = DualLogger(log_file, io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace'))
else:
    sys.stdout = DualLogger(log_file, sys.stdout)
    sys.stderr = DualLogger(log_file, sys.stderr)

# Cargar variables de entorno
from dotenv import load_dotenv
load_dotenv('.env')

# Importar Rich para UI bonita
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich import print as rprint
    console = Console()
except ImportError:
    # Fallback si no está instalado (aunque el requirements lo tiene o debería tener)
    console = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator.graph import run_agent
from orchestrator.db import db, init_db

# Lista de blancos biomédicos de alta prioridad (catálogo estático de fallback autónomo)
AUTONOMOUS_TARGET_POOL = [
    {
        "target": "EGFR",
        "pdb_id": "4HJO",
        "therapeutic_area": "Oncología",
        "indication_label": "Cáncer de Pulmón (Mutación de EGFR)",
        "workflow": "de_novo"
    },
    {
        "target": "DPP4",
        "pdb_id": "3HAJ",
        "therapeutic_area": "Metabólica",
        "indication_label": "Diabetes Tipo 2 (Inhibición de DPP-4)",
        "workflow": "de_novo"
    },
    {
        "target": "MPRO",
        "pdb_id": "6LU7",
        "therapeutic_area": "Infecciosas",
        "indication_label": "SARS-CoV-2 Mpro proteasa",
        "workflow": "de_novo"
    },
    {
        "target": "DENV_NS3",
        "pdb_id": "2M9P",
        "therapeutic_area": "Infecciosas",
        "indication_label": "Dengue — NS3 proteasa (I+D antiviral in silico)",
        "workflow": "de_novo"
    },
    {
        "target": "ZIKV_NS3",
        "pdb_id": "7VLI",
        "therapeutic_area": "Infecciosas",
        "indication_label": "Zika — NS2B-NS3 proteasa (I+D antiviral in silico)",
        "workflow": "de_novo"
    },
    {
        "target": "RSV_F",
        "pdb_id": "5C6B",
        "therapeutic_area": "Infecciosas",
        "indication_label": "VRS (RSV) — proteína F, sitio con ligando (I+D in silico)",
        "workflow": "de_novo"
    },
    {
        "target": "BACE1",
        "pdb_id": "1W50",
        "therapeutic_area": "Neurología",
        "indication_label": "Enfermedad de Alzheimer (BACE1)",
        "workflow": "de_novo"
    },
    {
        "target": "HIV1PR",
        "pdb_id": "1HSG",
        "therapeutic_area": "Infecciosas",
        "indication_label": "Inhibición de Proteasa de VIH-1",
        "workflow": "de_novo"
    },
    {
        "target": "KRAS",
        "pdb_id": "6VXX",
        "therapeutic_area": "Oncología",
        "indication_label": "Mutación Oncogénica KRAS G12C",
        "workflow": "de_novo"
    },
    {
        "target": "PD_L1",
        "pdb_id": "3K33",
        "therapeutic_area": "Oncología",
        "indication_label": "PD-L1 (CD274) — inhibición in silico",
        "workflow": "de_novo"
    },
    # ── Nuevos targets expandidos ──────────────────────────────────────────────
    {
        "target": "ABL1",
        "pdb_id": "1IEP",
        "therapeutic_area": "Oncología",
        "indication_label": "BCR-ABL1 — Leucemia Mieloide Crónica (CML)",
        "workflow": "de_novo"
    },
    {
        "target": "CDK2",
        "pdb_id": "1FIN",
        "therapeutic_area": "Oncología",
        "indication_label": "CDK2 — Ciclo Celular, Tumores Sólidos",
        "workflow": "de_novo"
    },
    {
        "target": "BRAF",
        "pdb_id": "4MNE",
        "therapeutic_area": "Oncología",
        "indication_label": "BRAF V600E — Melanoma, Cáncer de Tiroides",
        "workflow": "de_novo"
    },
    {
        "target": "PARP1",
        "pdb_id": "3L3M",
        "therapeutic_area": "Oncología",
        "indication_label": "PARP1 — Cánceres BRCA1/2 (terapia sintética letal)",
        "workflow": "de_novo"
    },
    {
        "target": "JAK2",
        "pdb_id": "3E64",
        "therapeutic_area": "Inflamatoria/Oncológica",
        "indication_label": "JAK2 — Mielofibrosis, Artritis Reumatoide",
        "workflow": "de_novo"
    },
    {
        "target": "HDAC1",
        "pdb_id": "4BKX",
        "therapeutic_area": "Oncología/Epigenética",
        "indication_label": "HDAC1 — Inhibidores Epigenéticos",
        "workflow": "de_novo"
    },
    {
        "target": "AChE",
        "pdb_id": "1EVE",
        "therapeutic_area": "Neurológica",
        "indication_label": "AChE — Alzheimer, Deterioro Cognitivo",
        "workflow": "de_novo"
    },
    {
        "target": "HIV1_INT",
        "pdb_id": "3L2T",
        "therapeutic_area": "Infecciosas",
        "indication_label": "VIH-1 Integrasa — INSTI (Anti-VIH)",
        "workflow": "de_novo"
    },
]

def brainstorm_next_target_with_llm() -> dict:
    """
    Usa Llama-3 en Groq para razonar y decidir autónomamente el próximo target biomédico a investigar,
    considerando cuáles son las prioridades globales de salud.
    """
    local_base = os.environ.get("LOCAL_LLM_BASE_URL", "").strip()
    offline = os.environ.get("OFFLINE_MODE", "False").lower() in ["true", "1", "yes"]
    
    # Si hay LLM Local, intentamos usarlo incluso si estamos en offline o sin keys en la nube
    if local_base:
        if console:
            console.print(f"   [bold cyan]🔌 [LOCAL LLM]: Decidiendo diana terapéutica con LLM local en {local_base}...[/bold cyan]")
        else:
            print(f"   🔌 [LOCAL LLM]: Decidiendo diana terapéutica con LLM local en {local_base}...")
            
        try:
            from utils.local_llm import LocalChatModel
            from langchain_core.messages import SystemMessage, HumanMessage
            model_name = os.environ.get("LOCAL_LLM_MODEL", "llama3")
            llm = LocalChatModel(base_url=local_base, model_name=model_name)
            
            system_prompt = """Eres la Mente Científica Principal (Orquestador Autónomo) de DrugAgent.
Tu tarea es decidir qué enfermedad y qué receptor proteico (con su respectivo ID PDB válido de RCSB PDB) debemos investigar hoy.
Debes seleccionar una diana terapéutica relevante (cánceres resistentes, superbacterias, neurodegeneración, virus con alta carga de I+D global o brotes recientes — p. ej. prioridades tipo WHO R&D Blueprint cuando tengas un PDB válido en RCSB).
NO afirmes que la enfermedad carece de toda terapia o vacuna: DrugAgent no consulta registros regulatorios en tiempo real y eso varía por país y año.
Asegúrate de proporcionar un ID PDB existente y legítimo (4 caracteres alfanuméricos, ej: '4HJO', '2M9P', '7VLI', '5C6B', '6LU7', '1HSG').

Devuelve un JSON estrictamente estructurado sin explicaciones adicionales:
{
    "target": "Nombre de la proteína en mayúsculas (ej: BACE1)",
    "pdb_id": "PDB ID válido de 4 letras (ej: 1W50)",
    "therapeutic_area": "Área terapéutica en español (ej: Oncología, Neurología, Infecciosas)",
    "indication_label": "Detalle clínico completo de la enfermedad en español (ej: Cáncer de Pulmón resistente a Gefitinib)",
    "workflow": "de_novo o lead_opt",
    "justification": "Breve párrafo de justificación científica de por qué este blanco es de alta prioridad mundial."
}
"""
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content="Decide de forma autónoma cuál es nuestro próximo blanco de investigación prioritaria.")
            ]
            
            response = llm.invoke(messages)
            res_text = response.content
            
            start = res_text.find('{')
            end = res_text.rfind('}')
            if start != -1 and end != -1:
                raw_json = res_text[start:end+1]
                data = json.loads(raw_json)
                
                # Normalizar llaves para máxima robustez con LLMs locales
                normalized_data = {}
                for k, v in data.items():
                    normalized_data[k.lower().strip()] = v
                
                target = normalized_data.get("target") or normalized_data.get("name")
                pdb_id = normalized_data.get("pdb_id") or normalized_data.get("pdb") or normalized_data.get("pdbid")
                area = normalized_data.get("therapeutic_area") or normalized_data.get("area")
                indication = normalized_data.get("indication_label") or normalized_data.get("indication") or normalized_data.get("disease")
                workflow = normalized_data.get("workflow", "de_novo")
                justification = normalized_data.get("justification", "Prioridad mundial de salud")
                
                if target and pdb_id and area and indication:
                    from utils.target_validation import validate_mission_dict
                    result = validate_mission_dict({
                        "target": str(target).strip().upper(),
                        "pdb_id": str(pdb_id).strip().upper(),
                        "therapeutic_area": str(area).strip(),
                        "indication_label": str(indication).strip(),
                        "workflow": str(workflow).strip(),
                        "justification": str(justification).strip(),
                    })
                    if console:
                        console.print("\n[bold cyan]🧠 [Decisión Autónoma LLM Local]:[/bold cyan]")
                        console.print(f"   [yellow]Diana:[/yellow]         {result['target']} (PDB: {result['pdb_id']})")
                        console.print(f"   [yellow]Área:[/yellow]          {result['therapeutic_area']}")
                        console.print(f"   [yellow]Indicación:[/yellow]    {result['indication_label']}")
                        console.print(f"   [yellow]Justificación:[/yellow] {result['justification']}")
                    else:
                        print(f"\n🧠 [Decisión Autónoma LLM Local]:")
                        print(f"   Diana:         {result['target']} (PDB: {result['pdb_id']})")
                        print(f"   Área:          {result['therapeutic_area']}")
                        print(f"   Indicación:    {result['indication_label']}")
                        print(f"   Justificación: {result['justification']}")
                    return result
        except Exception as e_local:
            print(f"   ⚠️ Falló decisión con LLM local ({e_local}). Rebotando...")

    if (offline and not local_base) or local_base:
        if console:
            console.print("   [bold magenta]🔌 [MODO OFFLINE/LOCAL]: Seleccionando diana terapéutica de la piscina local...[/bold magenta]")
        else:
            print("   🔌 [MODO OFFLINE/LOCAL]: Seleccionando diana terapéutica de la piscina local...")
        return random.choice(AUTONOMOUS_TARGET_POOL)

    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_key or groq_key.startswith("gsk_REEMPLAZA") or local_base:
        print("   ℹ️ Entorno local activo o API cloud no disponible. Seleccionando de la piscina biomédica pre-curada...")
        return random.choice(AUTONOMOUS_TARGET_POOL)
        
    try:
        from langchain_groq import ChatGroq
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import SystemMessage, HumanMessage
        
        llm = ChatGroq(
            model=os.environ.get("GROQ_HEAVY_MODEL", "llama-3.3-70b-versatile"),
            temperature=0.7,
            max_tokens=1024,
            groq_api_key=groq_key
        )
        
        system_prompt = """Eres la Mente Científica Principal (Orquestador Autónomo) de DrugAgent.
Tu tarea es decidir qué enfermedad y qué receptor proteico (con su respectivo ID PDB válido de RCSB PDB) debemos investigar hoy.
Debes seleccionar una diana terapéutica relevante (cánceres resistentes, superbacterias, neurodegeneración, virus con alta carga de I+D global o brotes recientes — p. ej. prioridades tipo WHO R&D Blueprint cuando tengas un PDB válido en RCSB).
NO afirmes que la enfermedad carece de toda terapia o vacuna: DrugAgent no consulta registros regulatorios en tiempo real y eso varía por país y año.
Asegúrate de proporcionar un ID PDB existente y legítimo (4 caracteres alfanuméricos, ej: '4HJO', '2M9P', '7VLI', '5C6B', '6LU7', '1HSG').

Devuelve un JSON estrictamente estructurado sin explicaciones adicionales:
{
    "target": "Nombre de la proteína en mayúsculas (ej: BACE1)",
    "pdb_id": "PDB ID válido de 4 letras (ej: 1W50)",
    "therapeutic_area": "Área terapéutica en español (ej: Oncología, Neurología, Infecciosas)",
    "indication_label": "Detalle clínico completo de la enfermedad en español (ej: Cáncer de Pulmón resistente a Gefitinib)",
    "workflow": "de_novo o lead_opt",
    "justification": "Breve párrafo de justificación científica de por qué este blanco es de alta prioridad mundial."
}
"""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content="Decide de forma autónoma cuál es nuestro próximo blanco de investigación prioritaria.")
        ]
        
        response = llm.invoke(messages)
        res_text = response.content
        
        # Extraer JSON
        start = res_text.find('{')
        end = res_text.rfind('}')
        if start != -1 and end != -1:
            data = json.loads(res_text[start:end+1])
            # Validar campos básicos
            if all(k in data for k in ["target", "pdb_id", "therapeutic_area", "indication_label"]):
                from utils.target_validation import validate_mission_dict
                data = validate_mission_dict({
                    **data,
                    "target": str(data["target"]).strip().upper(),
                    "pdb_id": str(data["pdb_id"]).strip().upper(),
                })
                if console:
                    console.print("\n[bold cyan]🧠 [Decisión Autónoma LLM]:[/bold cyan]")
                    console.print(f"   [yellow]Diana:[/yellow]         {data['target']} (PDB: {data['pdb_id']})")
                    console.print(f"   [yellow]Área:[/yellow]          {data['therapeutic_area']}")
                    console.print(f"   [yellow]Indicación:[/yellow]    {data['indication_label']}")
                    console.print(f"   [yellow]Justificación:[/yellow] {data.get('justification')}")
                else:
                    print(f"\n🧠 [Decisión Autónoma LLM]:")
                    print(f"   Diana:         {data['target']} (PDB: {data['pdb_id']})")
                    print(f"   Área:          {data['therapeutic_area']}")
                    print(f"   Indicación:    {data['indication_label']}")
                    print(f"   Justificación: {data.get('justification')}")
                return data
                
    except Exception as e:
        if console:
            console.print(f"   [bold yellow]⚠️ Error con Groq ({e}). Intentando con Gemini como respaldo...[/bold yellow]")
        else:
            print(f"   ⚠️ Error con Groq ({e}). Intentando con Gemini como respaldo...")
            
        try:
            gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
            if gemini_key:
                from langchain_google_genai import ChatGoogleGenerativeAI
                gemini_model = os.environ.get("GEMINI_HEAVY_MODEL", "gemini-2.5-flash")
                llm = ChatGoogleGenerativeAI(model=gemini_model, temperature=0.7, google_api_key=gemini_key)
                response = llm.invoke(messages)
                res_text = response.content
                start = res_text.find('{')
                end = res_text.rfind('}')
                if start != -1 and end != -1:
                    data = json.loads(res_text[start:end+1])
                    if all(k in data for k in ["target", "pdb_id", "therapeutic_area", "indication_label"]):
                        from utils.target_validation import validate_mission_dict
                        data = validate_mission_dict({
                            **data,
                            "target": str(data["target"]).strip().upper(),
                            "pdb_id": str(data["pdb_id"]).strip().upper(),
                        })
                        if console:
                            console.print("\n[bold cyan]🧠 [Decisión Autónoma LLM (GEMINI FALLBACK)]:[/bold cyan]")
                            console.print(f"   [yellow]Diana:[/yellow]         {data['target']} (PDB: {data['pdb_id']})")
                            console.print(f"   [yellow]Área:[/yellow]          {data['therapeutic_area']}")
                            console.print(f"   [yellow]Indicación:[/yellow]    {data['indication_label']}")
                            console.print(f"   [yellow]Justificación:[/yellow] {data.get('justification')}")
                        return data
        except Exception as e2:
            if console:
                console.print(f"   [bold red]⚠️ Error con Gemini ({e2}). Usando piscina pre-curada...[/bold red]")
            else:
                print(f"   ⚠️ Error con Gemini ({e2}). Usando piscina pre-curada...")
        
    return random.choice(AUTONOMOUS_TARGET_POOL)

def run_infinite_loop():
    """
    Ejecuta el ciclo infinito de descubrimiento farmacológico autónomo.
    """
    if console:
        header = Panel(
            "[bold white]El agente elegirá sus propias dianas terapéuticas, buscará mutaciones de alta prioridad,\n"
            "descargará conformeros 3D, y alertará cuando haya candidatos in silico prioritarios (no es cura clínica).\n\n"
            "[italic red]Presione Ctrl+C para finalizar la simulación.[/italic red][/bold white]",
            title="[bold green]🤖 DRUGAGENT - SISTEMA DE DESCUBRIMIENTO MOLECULAR 100% AUTÓNOMO[/bold green]",
            expand=False,
            border_style="green"
        )
        console.print(header)
    else:
        print("\n" + "="*80)
        print("🤖 DRUGAGENT - SISTEMA DE DESCUBRIMIENTO MOLECULAR 100% AUTÓNOMO")
        print("="*80)
        print("El agente elegirá sus propias dianas terapéuticas, buscará mutaciones de alta prioridad,")
        print("descargará conformeros 3D, y alertará cuando haya candidatos in silico prioritarios (no es cura clínica).")
        print("Presione Ctrl+C para finalizar la simulación.")
        print("="*80 + "\n")
    
    init_db()
    
    mission_count = 1
    
    while True:
        if console:
            console.print(f"\n[bold magenta]🚀 [MISIÓN AUTÓNOMA #{mission_count}] Iniciando ciclo científico...[/bold magenta]")
        else:
            print(f"\n🚀 [MISIÓN AUTÓNOMA #{mission_count}] Iniciando ciclo científico...")
            
        # 1. Decidir target autónomamente
        mission = brainstorm_next_target_with_llm()
        target = mission["target"]
        pdb_id = mission["pdb_id"]
        area = mission["therapeutic_area"]
        indication = mission["indication_label"]
        wf = mission.get("workflow", "de_novo")
        
        # Validar PDB ID
        from core.docking import validate_pdb_id
        if not validate_pdb_id(pdb_id):
            if console:
                console.print(f"   [bold red]⚠️ El ID de PDB '{pdb_id}' decidido por el LLM no es válido o no existe en RCSB PDB.[/bold red]")
                console.print("   [bold yellow]🔄 Usando un blanco terapéutico seguro y pre-curado de la piscina autónoma...[/bold yellow]")
            else:
                print(f"   ⚠️ El ID de PDB '{pdb_id}' decidido por el LLM no es válido o no existe en RCSB PDB.")
                print("   🔄 Usando un blanco terapéutico seguro y pre-curado de la piscina autónoma...")
            
            mission = random.choice(AUTONOMOUS_TARGET_POOL)
            target = mission["target"]
            pdb_id = mission["pdb_id"]
            area = mission["therapeutic_area"]
            indication = mission["indication_label"]
            wf = mission.get("workflow", "de_novo")
            
        # Registrar misión en SQLite vía Prisma
        run_record = None
        try:
            run_record = db.run.create(
                data={
                    "target_name": target,
                    "target_pdb_id": pdb_id,
                    "max_iterations": 2, # 2 iteraciones por target para mantener agilidad y rotación continua
                    "status": "running",
                    "workflow_mode": wf,
                    "therapeutic_area": area,
                    "indication_label": indication,
                    "parent_smiles": None
                }
            )
            run_id = run_record.id
        except Exception as e_db:
            print(f"⚠️ Error creando corrida en Prisma DB: {e_db}")
            run_id = f"auto_{int(time.time())}"
            
        start_time = time.time()
        config_dict = {
            "target": target,
            "pdb": pdb_id,
            "iterations": 2,
            "workflow": wf,
            "area": area,
            "indication": indication,
            "parent_smiles": None,
            "timestamp": datetime.now().isoformat(),
            "mode": "autonomous"
        }
        config_snapshot_json = json.dumps(config_dict)
        
        if run_record:
            try:
                db.run.update(
                    where={"id": run_id},
                    data={"config_snapshot": config_snapshot_json}
                )
            except Exception:
                pass
            
        if console:
            console.print(f"📋 Ejecutando Pipeline LangGraph para [bold]{target}[/bold] ({pdb_id}) [Run ID: [blue]{run_id}[/blue]]...")
        else:
            print(f"📋 Ejecutando Pipeline LangGraph para {target} ({pdb_id}) [Run ID: {run_id}]...")
            
        # 2. Ejecutar el orquestador científico
        try:
            from utils.mlflow_logger import start_discovery_run, end_discovery_run
            
            # Iniciar telemetría de MLflow para esta misión autónoma
            mlflow_run_id = start_discovery_run(
                target_name=target,
                target_pdb_id=pdb_id,
                workflow_mode=wf,
                therapeutic_area=area,
                indication_label=indication,
                max_iterations=2,
                db_run_id=run_id
            )
            
            # Enlazar mlflow_run_id en Prisma DB
            if mlflow_run_id and run_record:
                try:
                    db.run.update(
                        where={"id": run_id},
                        data={"mlflow_run_id": mlflow_run_id}
                    )
                except Exception:
                    pass
            
            result = run_agent(
                target_name=target,
                target_pdb_id=pdb_id,
                max_iterations=2, # Agilidad para bucle infinito
                db_run_id=run_id,
                workflow_mode=wf,
                therapeutic_area=area,
                indication_label=indication
            )
            
            # Finalizar run en DB
            duration = time.time() - start_time
            docking_mode = result.get("docking_mode", "real") if isinstance(result, dict) else "real"
            if run_record:
                try:
                    db.run.update(
                        where={"id": run_id},
                        data={
                            "status": "completed",
                            "end_time": datetime.now(),
                            "docking_mode": docking_mode,
                            "duration_sec": duration
                        }
                    )
                except Exception:
                    pass
                
            if console:
                console.print(f"[bold green]✓ Misión #{mission_count} completada con éxito en {duration:.1f}s.[/bold green]")
            else:
                print(f"✓ Misión #{mission_count} completada con éxito en {duration:.1f}s.")
                
            # Finalizar telemetría de MLflow con éxito
            best_score = result.get("best_score", 0.0) if isinstance(result, dict) else 0.0
            top_candidates = result.get("top_candidates", []) if isinstance(result, dict) else []
            best_smiles = top_candidates[0].get("smiles", "") if top_candidates else ""
            total_candidates = len(result.get("all_candidates", [])) if isinstance(result, dict) else 0
            insights_count = len(result.get("insights", [])) if isinstance(result, dict) else 0
            skills_count = len(result.get("new_skills_generated", [])) if isinstance(result, dict) else 0

            try:
                from utils.evidence_report import generate_evidence_pack
                generate_evidence_pack(
                    target_name=target,
                    target_pdb_id=pdb_id,
                    top_candidates=top_candidates,
                    run_id=run_id,
                    therapeutic_area=area,
                    indication_label=indication,
                )
            except Exception as ev_err:
                print(f"⚠️ Evidencia ChEMBL omitida: {ev_err}")

            try:
                from utils.pdf_generator import generate_pdf_report
                generate_pdf_report(run_id=run_id)
            except Exception:
                pass
            
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
            
            # Mostrar resumen de descubrimientos históricos
            try:
                breakthrough_path = Path("data/breakthroughs.json")
                if breakthrough_path.exists():
                    with open(breakthrough_path, "r", encoding="utf-8") as f:
                        bt_list = json.load(f)
                    n_bt = len(bt_list)
                    if n_bt > 0:
                        if console:
                            console.print(f"\n[bold gold3]🏆 Total de candidatos in silico de alta prioridad registrados: {n_bt}[/bold gold3]")
                            latest = bt_list[-1]
                            console.print(f"   [yellow]Último avance:[/yellow] {latest['target_name']} ({latest['target_pdb_id']}) para {latest['indication_label']}")
                        else:
                            print(f"\n🏆 Total de candidatos in silico de alta prioridad registrados: {n_bt}")
                            latest = bt_list[-1]
                            print(f"   Último avance: {latest['target_name']} ({latest['target_pdb_id']}) para {latest['indication_label']}")
            except Exception:
                pass
                
        except Exception as e_run:
            import traceback
            duration = time.time() - start_time
            
            # Finalizar telemetría de MLflow con fallo
            try:
                from utils.mlflow_logger import end_discovery_run
                end_discovery_run(
                    status="failed",
                    error_message=f"{str(e_run)}\n\n{traceback.format_exc()}",
                    duration_sec=duration
                )
            except Exception:
                pass
                
            if console:
                console.print(f"[bold red]❌ Error durante la ejecución de la misión #{mission_count}:[/bold red] {e_run}")
            else:
                print(f"❌ Error durante la ejecución de la misión #{mission_count}: {e_run}")
            if run_record:
                try:
                    db.run.update(
                        where={"id": run_id},
                        data={
                            "status": "failed",
                            "end_time": datetime.now(),
                            "error_message": f"{str(e_run)}\n\n{traceback.format_exc()}",
                            "duration_sec": duration
                        }
                    )
                except Exception:
                    pass

        if console:
            console.print(f"\n[dim]⏳ Misión #{mission_count} concluida. Esperando 5 segundos para descansar APIs...[/dim]")
        else:
            print(f"\n⏳ Misión #{mission_count} concluida. Esperando 5 segundos para descansar APIs...")
        mission_count += 1
        time.sleep(5)

if __name__ == "__main__":
    try:
        run_infinite_loop()
    except KeyboardInterrupt:
        if console:
            console.print("\n[bold yellow]👋 Bucle autónomo detenido por el usuario. Descubrimientos resguardados en base de datos.[/bold yellow]")
        else:
            print("\n👋 Bucle autónomo detenido por el usuario. Descubrimientos resguardados en base de datos.")
        sys.exit(0)
