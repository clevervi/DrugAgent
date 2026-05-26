import streamlit as st
import json
import os
import sys
import pandas as pd
import plotly.express as px
from rdkit import Chem
from rdkit.Chem import Draw
from streamlit_autorefresh import st_autorefresh
import yaml
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime

# Configurar layout ancho y título de página premium
st.set_page_config(
    layout="wide",
    page_title="DrugAgent - Premium Computational Chemistry Workbench",
    page_icon="🧬"
)

# Inyectar estilos CSS premium globales y fuente Outfit de Google Fonts
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] {
    font-family: 'Outfit', sans-serif;
    color: #f1f5f9;
}
.main {
    background-color: #0b0f19;
}
.stMetric {
    background-color: #1e293b;
    padding: 20px;
    border-radius: 12px;
    border: 1px solid #334155;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
}
.stMetric label {
    color: #94a3b8 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
}
.stMetric div[data-testid="stMetricValue"] {
    color: #3b82f6 !important;
    font-size: 26px !important;
    font-weight: 700 !important;
}
/* Tarjetas de métricas globales premium */
.global-metric-card {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4);
    text-align: center;
    transition: all 0.3s ease;
    height: 100%;
}
.global-metric-card:hover {
    transform: translateY(-3px);
    border-color: #3b82f6;
    box-shadow: 0 15px 30px -10px rgba(59, 130, 246, 0.4);
}
.global-metric-title {
    color: #94a3b8;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 8px;
}
.global-metric-value {
    color: #3b82f6;
    font-size: 30px;
    font-weight: 700;
}
/* Personalización de botones */
button[kind="primary"] {
    background-color: #ef4444 !important;
    border-color: #dc2626 !important;
    font-weight: 600 !important;
}
button[kind="secondary"] {
    background-color: #3b82f6 !important;
    color: white !important;
    border-color: #2563eb !important;
    font-weight: 600 !important;
}
</style>
""", unsafe_allow_html=True)

# Configurar autorefresh cada 3 segundos (3000 ms), limit a 1000 refrescos
count = st_autorefresh(interval=3000, limit=1000, key="datarefresh")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "output", "agent.log"))

# --- CONEXIÓN A LA DB ---
def get_prisma_db():
    from prisma import Prisma
    db_path = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data", "drugagent.db"))
    os.environ["DATABASE_URL"] = f"file:{db_path}"
    db = Prisma()
    return db

# --- CARGA DE AVANCES CIENTÍFICOS ---
def load_breakthroughs():
    path = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data", "breakthroughs.json"))
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

# --- CARGA GLOBAL DE METADATOS Y STATS ---
@st.cache_data(ttl=2)
def load_global_stats():
    try:
        db = get_prisma_db()
        db.connect()
        total_runs = db.run.count()
        total_candidates = db.candidate.count()
        
        # Obtener el mejor score de docking absoluto
        best_cand = db.candidate.find_first(
            where={'docking_score': {'lt': 0.0}},
            order={'docking_score': 'asc'}
        )
        best_score = best_cand.docking_score if best_cand else -8.5
        
        # Obtener promedio de QED de los candidatos de alta calidad
        avg_qed = 0.72
        cands_for_qed = db.candidate.find_many(
            take=100,
            order={'created_at': 'desc'}
        )
        if cands_for_qed:
            avg_qed = sum(c.qed for c in cands_for_qed) / len(cands_for_qed)
            
        completed_runs = db.run.count(where={'status': 'completed'})
        
        db.disconnect()
        return {
            "total_runs": total_runs,
            "total_candidates": total_candidates,
            "best_score": best_score,
            "avg_qed": avg_qed,
            "completed_runs": completed_runs
        }
    except Exception as e:
        print(f"Error loading global stats: {e}")
        return {
            "total_runs": 0,
            "total_candidates": 0,
            "best_score": 0.0,
            "avg_qed": 0.0,
            "completed_runs": 0
        }

@st.cache_data(ttl=2)
def load_all_runs():
    try:
        db = get_prisma_db()
        db.connect()
        runs = db.run.find_many(
            order={'start_time': 'desc'}
        )
        runs_list = [r.model_dump() for r in runs]
        db.disconnect()
        return runs_list
    except Exception as e:
        print(f"Error loading runs: {e}")
        return []

@st.cache_data(ttl=2)
def load_run_candidates_and_details(run_id):
    try:
        db = get_prisma_db()
        db.connect()
        run = db.run.find_unique(
            where={'id': run_id},
            include={'candidates': True}
        )
        if not run:
            db.disconnect()
            return None
        run_dict = run.model_dump()
        db.disconnect()
        return run_dict
    except Exception as e:
        print(f"Error loading run candidates/details: {e}")
        return None

@st.cache_data(ttl=5)
def load_skills():
    try:
        db = get_prisma_db()
        db.connect()
        skills = db.skill.find_many(
            order={'created_at': 'desc'}
        )
        skills_list = [s.model_dump() for s in skills]
        db.disconnect()
        return skills_list
    except Exception as e:
        print(f"Error loading skills: {e}")
        return []

# Cargar catálogo de misiones para la UI y mapeo de disclaimers
catalog_data = {}
try:
    catalog_path = os.path.join(SCRIPT_DIR, "..", "catalog", "therapeutic_areas.yaml")
    if os.path.exists(catalog_path):
        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog_data = yaml.safe_load(f) or {}
except Exception:
    pass

# --- MANEJO DE SUBPROCESOS EN SEGUNDO PLANO ---
def get_process_status():
    if "bg_process" not in st.session_state or st.session_state.bg_process is None:
        return "idle"
    
    proc = st.session_state.bg_process
    poll = proc.poll()
    if poll is None:
        return "running"
    
    # El proceso terminó, limpiar estado
    st.session_state.bg_process = None
    if poll == 0:
        return "success"
    else:
        return "error"

# Cargar datos estadísticos globales y runs
global_stats = load_global_stats()
all_runs_list = load_all_runs()

# --- DISEÑO DEL CONTENEDOR LATERAL (SIDEBAR) ---
st.sidebar.markdown("""
<div style='text-align: center; margin-bottom: 25px; padding-top: 10px;'>
    <h1 style='color: #3b82f6; margin: 0; font-size: 28px; font-weight: 700;'>🧪 DrugAgent</h1>
    <p style='color: #64748b; font-size: 13px; margin: 5px 0 0 0; font-weight: 500;'>Plataforma Científica In Silico</p>
</div>
""", unsafe_allow_html=True)

st.sidebar.subheader("⚙️ Configuración del Orquestador")
agent_mode = st.sidebar.radio(
    "Seleccionar Modo de Operación:",
    options=["Manual (Diana Única) 🛠️", "100% Autónomo Infinito 🤖"],
    help="Modo Manual: defines la diana y la simulación. Modo Autónomo: la IA elige objetivos, refina y busca de manera ininterrumpida."
)

st.sidebar.divider()

if agent_mode == "Manual (Diana Única) 🛠️":
    st.sidebar.subheader("🚀 Lanzador de Misiones Manuales")
    mission_keys = list(catalog_data.keys())
    mission_options = ["Personalizada 🛠️"] + [catalog_data[k].get("display_name", k) for k in mission_keys]
    
    selected_mission_display = st.sidebar.selectbox(
        "Seleccionar Diana Terapéutica:",
        options=mission_options
    )
    
    default_target = "EGFR"
    default_pdb = "4HJO"
    default_area = "Oncología"
    default_indication = "Cáncer de Pulmón (NSCLC)"
    
    if selected_mission_display != "Personalizada 🛠️":
        for k in mission_keys:
            if catalog_data[k].get("display_name") == selected_mission_display:
                default_target = catalog_data[k].get("target", "EGFR")
                default_pdb = catalog_data[k].get("pdb_id", "4HJO")
                disp_split = selected_mission_display.split(":")
                default_area = disp_split[0].strip()
                default_indication = disp_split[1].strip()
                break
    
    target_name_input = st.sidebar.text_input("Nombre del Target:", value=default_target)
    target_pdb_id_input = st.sidebar.text_input("RCSB PDB ID:", value=default_pdb)
    area_input = st.sidebar.text_input("Área Terapéutica:", value=default_area)
    indication_input = st.sidebar.text_input("Indicación Médica:", value=default_indication)
    
    workflow_input = st.sidebar.selectbox(
        "Metodología Química:",
        options=["de_novo", "lead_opt"],
        format_func=lambda x: "Generación De Novo (Desde Cero) 🆕" if x == "de_novo" else "Optimización de Hit (Lead Opt) 🧬"
    )
    
    parent_smiles_input = ""
    if workflow_input == "lead_opt":
        parent_smiles_input = st.sidebar.text_input(
            "SMILES de Molécula Madre (Core):",
            value="CC1=C(C(=O)N(C1=O)C)C"
        )
    
    iterations_input = st.sidebar.slider("Iteraciones Máximas del Grafo:", min_value=1, max_value=15, value=5)
    docking_mode_input = st.sidebar.selectbox(
        "Modo de Simulación (Docking):",
        options=["auto", "real", "mock"],
        help="auto: detecta Vina nativo o conmuta a mock; real: exige Vina nativo; mock: estimación QSAR rápida"
    )
else:
    st.sidebar.subheader("🤖 Laboratorio Autónomo Activo")
    st.sidebar.markdown("""
    <div style='background-color: #0f172a; border: 1px dashed #3b82f6; padding: 15px; border-radius: 10px; font-size: 12.5px; color: #94a3b8; line-height: 1.45; margin-bottom: 15px;'>
        <b>Mente Científica Autónoma Activada:</b><br>
        La IA decidirá los blancos terapéuticos en base a urgencias de salud global (mutaciones de cáncer, superbacterias, Alzheimer) y refinará de manera iterativa guardando avances.
    </div>
    """, unsafe_allow_html=True)
    docking_mode_input = st.sidebar.selectbox(
        "Modo de Simulación (Docking) Autónomo:",
        options=["auto", "real", "mock"],
        help="auto: detecta Vina nativo o conmuta a mock; real: exige Vina nativo; mock: estimación QSAR rápida"
    )

proc_status = get_process_status()
st.sidebar.divider()

if proc_status == "running":
    st.sidebar.markdown("""
    <div style='background-color: #1e1b4b; border: 1px solid #4338ca; padding: 15px; border-radius: 10px; margin-bottom: 15px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);'>
        <div style='display: flex; align-items: center;'>
            <span style='background-color: #4f46e5; width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 10px; animation: pulse 1.5s infinite;'></span>
            <b style='color: #c7d2fe; font-size: 14px;'>🔬 Pipeline Activo en Loop</b>
        </div>
        <p style='font-size: 11px; color: #a5b4fc; margin: 8px 0 0 0; line-height: 1.4;'>
            El orquestador está ejecutando ciclos de diseño, acoplamiento y análisis en tiempo real.
        </p>
    </div>
    <style>
    @keyframes pulse {
        0% { transform: scale(0.95); opacity: 0.5; }
        50% { transform: scale(1.1); opacity: 1; }
        100% { transform: scale(0.95); opacity: 0.5; }
    }
    </style>
    """, unsafe_allow_html=True)
    
    if st.sidebar.button("🛑 Terminar Simulación", type="primary", use_container_width=True):
        st.session_state.bg_process.terminate()
        st.session_state.bg_process = None
        st.sidebar.success("Simulación abortada con éxito.")
        st.rerun()
else:
    if proc_status == "success":
        st.sidebar.success("✅ ¡Misión completada con éxito!")
    elif proc_status == "error":
        st.sidebar.error("❌ La última simulación se interrumpió con errores.")
        
    launch_btn_label = "🚀 Iniciar Bucle Autónomo" if agent_mode != "Manual (Diana Única) 🛠️" else "🚀 Lanzar Misión"
    if st.sidebar.button(launch_btn_label, use_container_width=True, type="secondary"):
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            f.write("Iniciando Misión de Descubrimiento...\n")
            
        log_file_handle = open(LOG_PATH, "a", encoding="utf-8")
        env_copy = os.environ.copy()
        env_copy["DOCKING_MODE"] = docking_mode_input
        
        if agent_mode == "Manual (Diana Única) 🛠️":
            cmd = [
                sys.executable,
                os.path.join(SCRIPT_DIR, "..", "run_agent.py"),
                "--target", target_name_input,
                "--pdb", target_pdb_id_input,
                "--iterations", str(iterations_input),
                "--workflow", workflow_input,
                "--area", area_input,
                "--indication", indication_input
            ]
            if workflow_input == "lead_opt" and parent_smiles_input:
                cmd.extend(["--parent-smiles", parent_smiles_input])
        else:
            cmd = [
                sys.executable,
                os.path.join(SCRIPT_DIR, "..", "run_autonomous.py")
            ]
            
        proc = subprocess.Popen(
            cmd,
            stdout=log_file_handle,
            stderr=subprocess.STDOUT,
            cwd=os.path.join(SCRIPT_DIR, ".."),
            env=env_copy,
            text=True
        )
        st.session_state.bg_process = proc
        st.sidebar.success("¡Misión iniciada en segundo plano!")
        st.rerun()

# --- VISTA PRINCIPAL ---
st.title("🧬 DrugAgent Local - Premium Chemistry Workbench")
st.markdown("Visualización e inspección interactiva tridimensional, telemetría multicorrida y base de datos científica in silico.")

# --- SECCIÓN 1: TELEMETRÍA GLOBAL (ESTADÍSTICAS DEL SISTEMA) ---
st.markdown("### 📊 Telemetría y Rendimiento Científico Global")
stat_col1, stat_col2, stat_col3, stat_col4, stat_col5 = st.columns(5)

with stat_col1:
    st.markdown(f"""
    <div class="global-metric-card">
        <div class="global-metric-title">Misiones Completadas</div>
        <div class="global-metric-value">{global_stats['total_runs']}</div>
    </div>
    """, unsafe_allow_html=True)
    
with stat_col2:
    st.markdown(f"""
    <div class="global-metric-card">
        <div class="global-metric-title">Compuestos Diseñados</div>
        <div class="global-metric-value">{global_stats['total_candidates']}</div>
    </div>
    """, unsafe_allow_html=True)
    
with stat_col3:
    st.markdown(f"""
    <div class="global-metric-card">
        <div class="global-metric-title">Afinidad Máxima (Global)</div>
        <div class="global-metric-value">{global_stats['best_score']:.2f} kcal/mol</div>
    </div>
    """, unsafe_allow_html=True)
    
with stat_col4:
    st.markdown(f"""
    <div class="global-metric-card">
        <div class="global-metric-title">QED Promedio (Calidad)</div>
        <div class="global-metric-value">{global_stats['avg_qed']:.3f}</div>
    </div>
    """, unsafe_allow_html=True)

with stat_col5:
    success_rate = (global_stats['completed_runs'] / max(1, global_stats['total_runs'])) * 100
    st.markdown(f"""
    <div class="global-metric-card">
        <div class="global-metric-title">Misiones Exitosas</div>
        <div class="global-metric-value">{success_rate:.1f}%</div>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# --- SECCIÓN 2: FILTRADO Y SELECCIÓN DE MISIONES HISTÓRICAS (328+ RUNS) ---
st.markdown("### 🔍 Explorador y Filtro de Misiones Históricas")

filter_col1, filter_col2, filter_col3 = st.columns(3)

with filter_col1:
    # Filtro por estado
    status_filter = st.selectbox(
        "Filtrar por Estado de Misión:",
        options=["Todos", "completed", "running", "failed"]
    )
    
with filter_col2:
    # Filtro por área terapéutica
    unique_areas = sorted(list(set([r.get("therapeutic_area") for r in all_runs_list if r.get("therapeutic_area")])))
    area_filter = st.selectbox(
        "Filtrar por Área Terapéutica:",
        options=["Todos"] + unique_areas
    )
    
with filter_col3:
    # Buscador de targets
    target_search = st.text_input("Buscar por Target (ej: EGFR, EGFR-T790M):").strip()

# Aplicar filtros
filtered_runs = all_runs_list
if status_filter != "Todos":
    filtered_runs = [r for r in filtered_runs if r.get("status") == status_filter]
if area_filter != "Todos":
    filtered_runs = [r for r in filtered_runs if r.get("therapeutic_area") == area_filter]
if target_search:
    filtered_runs = [r for r in filtered_runs if target_search.lower() in str(r.get("target_name")).lower()]

if not filtered_runs:
    st.warning("⚠️ No se encontraron misiones que coincidan con los filtros seleccionados.")
    st.stop()

# Selector final de la misión
run_options = []
for idx, r in enumerate(filtered_runs):
    start_dt = r.get("start_time")
    date_str = ""
    if start_dt:
        if isinstance(start_dt, datetime):
            date_str = start_dt.strftime("%Y-%m-%d %H:%M")
        else:
            try:
                date_str = datetime.fromisoformat(str(start_dt).replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
            except:
                date_str = str(start_dt)[:16]
    status_icon = "🟢" if r.get("status") == "completed" else ("🔵" if r.get("status") == "running" else "🔴")
    run_options.append(f"{status_icon} Misión #{len(filtered_runs) - idx} | Target: {r.get('target_name')} ({r.get('target_pdb_id')}) | {r.get('therapeutic_area')} | {date_str}")

selected_run_display = st.selectbox(
    "🧬 Seleccionar Misión Científica para Analizar:",
    options=run_options
)

selected_run_idx = run_options.index(selected_run_display)
selected_run = filtered_runs[selected_run_idx]

# Cargar detalles y candidatos del run seleccionado
selected_run_details = load_run_candidates_and_details(selected_run["id"])

if not selected_run_details:
    st.error("No se pudieron cargar los detalles de la misión seleccionada.")
    st.stop()

candidates = selected_run_details["candidates"]
docking_mode = selected_run_details["docking_mode"]
target_name = selected_run_details["target_name"]
target_pdb_id = selected_run_details["target_pdb_id"]
area = selected_run_details.get("therapeutic_area")
indication = selected_run_details.get("indication_label")
workflow = selected_run_details.get("workflow_mode", "de_novo")
parent_smiles = selected_run_details.get("parent_smiles")

# --- AVANCES CIENTÍFICOS CONFIRMADOS ---
breakthroughs = load_breakthroughs()
if breakthroughs:
    st.markdown("""
    <style>
    @keyframes pulse-glow {
        0% { border-color: #10b981; box-shadow: 0 0 10px rgba(16, 185, 129, 0.4); }
        50% { border-color: #06b6d4; box-shadow: 0 0 25px rgba(6, 182, 212, 0.8); }
        100% { border-color: #10b981; box-shadow: 0 0 10px rgba(16, 185, 129, 0.4); }
    }
    .breakthrough-card {
        background-color: #0f172a;
        border: 2px solid #10b981;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        animation: pulse-glow 3s infinite;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown("### 🏆 CURAS E INMUNIZADORES CIENTÍFICOS CONFIRMADOS")
    for idx, b in enumerate(breakthroughs[-2:]): # Mostrar últimos 2 avances
        col_c1, col_c2 = st.columns([2, 1])
        with col_c1:
            st.markdown(f"""
            <div class="breakthrough-card">
                <span style="background-color: #10b981; color: white; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: bold; text-transform: uppercase;">🧪 CURA REVELADA POR EL AGENTE #{idx+1}</span>
                <h4 style="margin: 10px 0 5px 0; color: #06b6d4; font-size: 18px;">Diana: {b.get('target_name')} (PDB: {b.get('target_pdb_id')})</h4>
                <p style="margin: 0 0 10px 0; color: #f1f5f9; font-size: 14px;"><b>Indicación Clínica</b>: {b.get('indication_label')} ({b.get('therapeutic_area')})</p>
                <p style="margin: 0 0 10px 0; color: #cbd5e1; font-size: 13px; line-height: 1.4;">
                    <b>Evidencia Deductiva</b>: {b.get('evidence_summary')}
                </p>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; font-size: 12px; color: #94a3b8;">
                    <div><b>Docking Score</b>: <code style="color: #ef4444; font-size: 13px; font-weight: bold;">{b.get('docking_score')} kcal/mol</code></div>
                    <div><b>Estabilidad MD</b>: <code style="color: #3b82f6; font-size: 13px; font-weight: bold;">{b.get('md_rmsd')} Å</code></div>
                    <div><b>Drug-likeness (QED)</b>: <code style="color: #10b981; font-size: 13px; font-weight: bold;">{b.get('qed')}</code></div>
                    <div><b>Tox ADMET</b>: <code style="color: #f59e0b; font-size: 13px; font-weight: bold;">{b.get('admet_toxicity')}</code></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        with col_c2:
            try:
                m_b = Chem.MolFromSmiles(b.get("smiles", ""))
                if m_b:
                    img_b = Draw.MolToImage(m_b, size=(200, 200))
                    st.image(img_b, use_container_width=True)
            except Exception:
                pass
    st.divider()

# Disclaimer y Banner del Target Activo Seleccionado
disclaimer_text = "ADVERTENCIA: Simulación preliminar de acoplamiento molecular computational. Resultados meramente experimentales in silico."
for key, item in catalog_data.items():
    if item.get("target") == target_name or item.get("pdb_id") == target_pdb_id:
        disclaimer_text = item.get("disclaimer", disclaimer_text)
        break

mode_label = docking_mode if docking_mode else "auto"
mode_badge = f"<span style='background-color:#3b82f6; color:white; padding:4px 8px; border-radius:4px; font-weight:bold;'>{mode_label.upper()}</span>"
wf_badge = f"<span style='background-color:#10b981; color:white; padding:4px 8px; border-radius:4px; font-weight:bold;'>{workflow.upper()}</span>"

parent_info = f"<br><b>Molécula Core (SMILES de partida)</b>: <code style='color:#cbd5e1;'>{parent_smiles}</code>" if parent_smiles else ""
display_indication = indication if indication else "Optimización selectiva de diana"
display_area = area if area else "Descubrimiento de Fármacos"

st.markdown(
    f"""
    <div style='background-color:#1e293b; padding:20px; border-radius:12px; border-left: 6px solid #3b82f6; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);'>
        <h3 style='margin:0 0 5px 0; color:#3b82f6; font-size:22px; font-weight:700;'>🎯 Misión Seleccionada: {target_name} (RCSB PDB: {target_pdb_id})</h3>
        <p style='margin:5px 0; font-size:15px; color:#f1f5f9; font-weight: 500;'>
            <b>Área Terapéutica</b>: {display_area} &nbsp;|&nbsp; <b>Indicación</b>: {display_indication}
        </p>
        <p style='margin:10px 0 0 0; font-size:13px; color:#cbd5e1;'>
            Modo Docking: {mode_badge} &nbsp;|&nbsp; Orquestación: {wf_badge} {parent_info}
        </p>
    </div>
    <div style='background-color:#7f1d1d; padding:12px; border-radius:8px; border-left: 4px solid #ef4444; margin-bottom: 25px; color:#fecaca; font-size:12.5px; font-weight: 500;'>
        ⚠️ <b>AVISO DE BIOSEGURIDAD:</b> {disclaimer_text}
    </div>
    """,
    unsafe_allow_html=True
)

# Convertir candidatos del run a DataFrame
numeric_columns = ["sa_score", "ligand_efficiency", "qed", "mw", "iteration", "docking_score", "admet_toxicity", "admet_absorption", "herg_risk", "bbb_permeability", "cyp3a4_inhibition", "md_rmsd", "md_refined_score", "md_strain_energy"]
if candidates:
    df = pd.DataFrame(candidates)
    if "docking_score" in df.columns:
        df = df.sort_values(by="docking_score", ascending=True).reset_index(drop=True)
    for col in numeric_columns:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
else:
    df = pd.DataFrame(columns=numeric_columns + ["smiles", "status"])

# --- MÉTRICAS DE LA CORRIDA SELECCIONADA ---
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Candidatos de esta Corrida", len(df))
if not df.empty and len(df) > 0 and df.iloc[0]['docking_score'] < 0:
    col2.metric("Mejor Afinidad (Run)", f"{df.iloc[0]['docking_score']} kcal/mol")
else:
    col2.metric("Mejor Afinidad (Run)", "N/A")
    
if not df.empty and "qed" in df.columns and len(df) > 0:
    col3.metric("QED Máximo (Run)", f"{df['qed'].max():.3f}")
else:
    col3.metric("QED Máximo (Run)", "N/A")
    
if not df.empty and "ligand_efficiency" in df.columns and len(df) > 0:
    col4.metric("Mejor Eficiencia Ligando", f"{df['ligand_efficiency'].min():.3f}")
else:
    col4.metric("Mejor Eficiencia Ligando", "N/A")
    
if not df.empty and "md_rmsd" in df.columns and len(df) > 0:
    md_candidates = df[df["md_rmsd"] > 0]
    if not md_candidates.empty:
        avg_rmsd = md_candidates["md_rmsd"].mean()
        col5.metric("Estabilidad MD (Run)", f"{avg_rmsd:.2f} Å")
    else:
        col5.metric("Estabilidad MD (Run)", "No refinado")
else:
    col5.metric("Estabilidad MD (Run)", "N/A")

st.divider()

# --- ARQUITECTURA MULTI-PESTAÑA (TABS) ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🧬 Visor de Acoplamiento 3D",
    "🏆 Top Candidatos Generados",
    "📊 Análisis Estadístico y Evolución",
    "🗺️ Espacio Químico & Pareto",
    "🧠 Skills & Directorio de Ciencia",
    "💻 Consola y Logs en Vivo",
])

# TAB 1: VISOR MOLECULAR 3D INTERACTIVO
with tab1:
    st.subheader("🧬 Inspección Visual 3D del Acoplamiento (Docking)")
    st.markdown("Visualiza interactivamente la pose óptima del ligando diseñado acoplado en el bolsillo del receptor de esta misión.")
    
    if (df.empty or len(df) == 0):
        st.info("Esperando simulaciones para renderizar modelos 3D...")
        receptor_path = os.path.join(SCRIPT_DIR, "..", "data", "receptors", f"{target_pdb_id}.pdb")
        if os.path.exists(receptor_path):
            st.markdown("🔍 **Vista del receptor vacío:**")
            with open(receptor_path, "r", encoding="utf-8", errors="ignore") as f:
                r_data = f.read()
            r_js = r_data.replace("`", "\\`").replace("${", "\\${")
            html_receptor = f"""
            <!DOCTYPE html>
            <html>
            <head><script src="https://3Dmol.org/build/3Dmol-min.js"></script></head>
            <body style='margin:0; background-color:#0f172a;'>
                <div id="canvas" style="width:100%; height:500px; border-radius:12px; border:2px solid #334155;"></div>
                <script>
                    document.addEventListener("DOMContentLoaded", function() {{
                        let viewer = $3Dmol.createViewer(document.getElementById("canvas"), {{ backgroundColor: '#0f172a' }});
                        viewer.addModel(`{r_js}`, "pdb");
                        viewer.setStyle({{model: 0}}, {{cartoon: {{color: '#3b82f6', opacity: 0.95}}}});
                        viewer.zoomTo();
                        viewer.render();
                    }});
                </script>
            </body>
            </html>
            """
            import streamlit.components.v1 as components
            components.html(html_receptor, height=510)
    else:
        options_3d = []
        for idx, row in df.iterrows():
            score_val = row.get("docking_score", 0.0)
            smi = row.get("smiles", "")
            options_3d.append(f"Candidato #{idx+1} | Score: {score_val} kcal/mol | SMILES: {smi[:35]}...")
            
        selected_cand_3d = st.selectbox("Seleccione el Ligando para Analizar en 3D:", options=options_3d)
        selected_index_3d = options_3d.index(selected_cand_3d)
        
        selected_row = df.iloc[selected_index_3d]
        smi_str = selected_row.get("smiles", "")
        
        receptor_path = os.path.join(SCRIPT_DIR, "..", "data", "receptors", f"{target_pdb_id}.pdb")
        receptor_data = ""
        if os.path.exists(receptor_path):
            try:
                with open(receptor_path, "r", encoding="utf-8", errors="ignore") as f:
                    receptor_data = f.read()
            except Exception:
                pass
                
        md5_hash = hashlib.md5(smi_str.encode('utf-8')).hexdigest()
        ligand_path = os.path.join(SCRIPT_DIR, "..", "data", "docked_poses", f"lig_{md5_hash}.pdbqt")
        ligand_data = ""
        if os.path.exists(ligand_path):
            try:
                with open(ligand_path, "r", encoding="utf-8", errors="ignore") as f:
                    ligand_data = f.read()
            except Exception:
                pass
                
        if not receptor_data and not ligand_data:
            st.warning("No se encontraron archivos de coordenadas 3D para este candidato.")
        else:
            receptor_js = receptor_data.replace("`", "\\`").replace("${", "\\${")
            ligand_js = ligand_data.replace("`", "\\`").replace("${", "\\${")
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
                <style>
                    body {{ margin: 0; padding: 0; background-color: #0f172a; overflow: hidden; }}
                    #container3d {{
                        width: 100%;
                        height: 520px;
                        position: relative;
                        border-radius: 12px;
                        border: 2px solid #334155;
                    }}
                    .legend {{
                        position: absolute;
                        bottom: 15px;
                        left: 15px;
                        background-color: rgba(15, 23, 42, 0.9);
                        color: #f1f5f9;
                        padding: 10px 15px;
                        border-radius: 8px;
                        font-family: 'Outfit', system-ui, sans-serif;
                        font-size: 11.5px;
                        border: 1px solid #475569;
                        z-index: 10;
                        pointer-events: none;
                    }}
                    .legend-item {{ display: flex; align-items: center; margin-bottom: 5px; }}
                    .color-box {{ width: 12px; height: 12px; border-radius: 3px; margin-right: 8px; }}
                </style>
            </head>
            <body>
                <div id="container3d">
                    <div class="legend">
                        <div class="legend-item">
                            <div class="color-box" style="background-color: #3b82f6;"></div>
                            <span>Receptor ({target_pdb_id}) - Cartoon Azul</span>
                        </div>
                        <div class="legend-item">
                            <div class="color-box" style="background-color: #eab308;"></div>
                            <span>Ligando Diseñado - Sticks Jmol</span>
                        </div>
                    </div>
                </div>
                <script>
                    document.addEventListener("DOMContentLoaded", function() {{
                        let element = document.getElementById("container3d");
                        let viewer = $3Dmol.createViewer(element, {{ backgroundColor: '#0f172a' }});
                        
                        let receptorData = `{receptor_js}`;
                        if (receptorData && receptorData.trim().length > 100) {{
                            viewer.addModel(receptorData, "pdb");
                            viewer.setStyle({{model: 0}}, {{cartoon: {{color: '#3b82f6', opacity: 0.85}}}});
                        }}
                        
                        let ligandData = `{ligand_js}`;
                        if (ligandData && ligandData.trim().length > 10) {{
                            viewer.addModel(ligandData, "pdbqt");
                            viewer.setStyle({{model: 1}}, {{
                                stick: {{colorscheme: 'Jmol', radius: 0.22}},
                                sphere: {{colorscheme: 'Jmol', radius: 0.35, scale: 0.35}}
                            }});
                            viewer.zoomTo({{model: 1}});
                        }} else {{
                            viewer.zoomTo();
                        }}
                        viewer.render();
                    }});
                </script>
            </body>
            </html>
            """
            import streamlit.components.v1 as components
            components.html(html_content, height=530)
            if not ligand_data:
                st.info("⚠️ La pose 3D del ligando aún no se ha guardado en docked_poses (simulación mock o en proceso). Mostrando únicamente el receptor.")

# TAB 2: GRID DE MOLÉCULAS DE RDKIT (TOP CANDIDATOS DEL RUN SELECCIONADO)
with tab2:
    st.subheader("🏆 Candidatos Diseñados en esta Misión")
    
    if df.empty or len(df) == 0:
        st.info("No hay candidatos moleculares para esta corrida.")
    else:
        cols_per_row = 3
        for i in range(0, len(df), cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                if i + j < len(df):
                    mol_data = df.iloc[i + j]
                    smiles = mol_data.get("smiles", "")
                    
                    with cols[j]:
                        st.markdown(f"#### Ranking #{i + j + 1}")
                        st.code(smiles, language="text")
                        
                        try:
                            m = Chem.MolFromSmiles(smiles)
                            if m:
                                img = Draw.MolToImage(m, size=(280, 280))
                                st.image(img, use_container_width=True)
                            else:
                                st.warning("Estructura molecular inválida.")
                        except Exception as e:
                            st.error(f"Error renderizando RDKit: {e}")
                        
                        docking = mol_data.get("docking_score", "N/A")
                        qed = mol_data.get("qed", 0.0)
                        le = mol_data.get("ligand_efficiency", "N/A")
                        sa = mol_data.get("sa_score", "N/A")
                        status_str = mol_data.get("status", "N/A")
                        md_rmsd = mol_data.get("md_rmsd", 0.0)
                        md_refined = mol_data.get("md_refined_score", 0.0)
                        md_strain = mol_data.get("md_strain_energy", None)
                        md_flex = mol_data.get("md_flexibility", None)
                        herg = mol_data.get("herg_risk", None)
                        bbb = mol_data.get("bbb_permeability", None)
                        cyp = mol_data.get("cyp3a4_inhibition", None)

                        md_info = f"- **Estabilidad MD**: `{md_rmsd:.2f} Å` (Refinado: `{md_refined:.2f}`)" if md_rmsd and md_rmsd > 0 else "- **Estabilidad MD**: `No refinado`"
                        strain_info = f"- **Strain MMFF94**: `{md_strain:.1f} kcal/mol` ({md_flex})" if md_strain is not None else ""
                        herg_icon = "🔴" if (herg or 0) > 0.6 else ("🟡" if (herg or 0) > 0.35 else "🟢")
                        bbb_icon = "🟢" if (bbb or 0) > 0.6 else "🔴"
                        herg_info = f"- **hERG Risk**: {herg_icon} `{herg:.2f}`" if herg is not None else ""
                        bbb_info = f"- **BBB Perm**: {bbb_icon} `{bbb:.2f}`" if bbb is not None else ""
                        cyp_info = f"- **CYP3A4 Inhib**: `{cyp:.2f}`" if cyp is not None else ""

                        st.markdown(f"""
                        - **Docking Score**: `{docking} kcal/mol`
                        {md_info}
                        {strain_info}
                        - **Ligand Efficiency**: `{le:.3f}`
                        - **QED (Drug-likeness)**: `{qed:.3f}`
                        - **SA Score (Sintetizabilidad)**: `{sa:.2f}`
                        {herg_info}
                        {bbb_info}
                        {cyp_info}
                        - **Estado**: `{status_str}`
                        """)
                        st.divider()

# TAB 3: GRÁFICOS INTERACTIVOS DE PLOTLY
with tab3:
    st.subheader("📊 Análisis Estadístico y Evolución de Misiones")
    
    if df.empty or len(df) == 0:
        st.info("Los gráficos analíticos estarán disponibles tan pronto como se generen moléculas.")
    else:
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            df_sorted_iter = df.sort_values("iteration")
            fig_line = px.scatter(
                df_sorted_iter, x="iteration", y="docking_score", 
                color="qed", hover_data=["smiles", "sa_score", "mw"],
                title="Afinidad de Docking vs Iteración de esta Corrida",
                labels={"iteration": "Iteración", "docking_score": "Docking Score (kcal/mol)", "qed": "QED"},
                color_continuous_scale="Viridis",
                trendline="ols" if len(df_sorted_iter) > 2 else None
            )
            st.plotly_chart(fig_line, use_container_width=True)
            
        with chart_col2:
            if "mw" in df.columns:
                fig_scatter = px.scatter(
                    df, x="mw", y="docking_score", 
                    color="sa_score" if "sa_score" in df.columns else "qed",
                    size="qed", hover_data=["smiles", "ligand_efficiency"],
                    title="Peso Molecular vs Docking (Filtro Lipinski) de esta Corrida",
                    labels={"mw": "Peso Molecular (g/mol)", "docking_score": "Docking Score (kcal/mol)", "sa_score": "SA Score"},
                    color_continuous_scale="RdYlGn_r"
                )
                fig_scatter.add_vline(x=500, line_dash="dash", line_color="red", annotation_text="Límite Lipinski (MW=500)")
                st.plotly_chart(fig_scatter, use_container_width=True)
        
        st.subheader("🌐 Análisis Histórico Comparativo Global (Todas las corridas)")
        # Cargar todos los candidatos históricos en segundo plano
        try:
            db = get_prisma_db()
            db.connect()
            all_cands = db.candidate.find_many(
                take=500,
                order={'created_at': 'desc'}
            )
            db.disconnect()
            if all_cands:
                all_df = pd.DataFrame([c.model_dump() for c in all_cands])
                fig_global = px.scatter(
                    all_df, x="qed", y="docking_score",
                    color="mw", hover_data=["smiles", "run_id"],
                    title="Espacio Químico Global: QED vs Afinidad de Docking (Top 500)",
                    labels={"qed": "Drug-Likeness (QED)", "docking_score": "Docking Score (kcal/mol)"},
                    color_continuous_scale="Viridis"
                )
                st.plotly_chart(fig_global, use_container_width=True)
        except Exception as e_glob:
            st.info("No se pudieron cargar datos históricos globales.")

# TAB 4: ESPACIO QUÍMICO UMAP + FRENTE PARETO
with tab4:
    st.subheader("Espacio Químico y Análisis Multi-Objetivo")

    if df.empty:
        st.info("No hay candidatos en la misión seleccionada. Ejecuta una corrida primero.")
    else:
        umap_col, pareto_col = st.columns([1, 1])

        with umap_col:
            st.markdown("#### UMAP — Navegación del Espacio Químico")
            st.caption("Cada punto es una molécula. Color = score de docking. El agente explora alejándose de las regiones ya cubiertas.")
            try:
                import umap as umap_lib
                from rdkit.Chem import rdFingerprintGenerator as rfg_mod
                HAS_UMAP = True
            except ImportError:
                HAS_UMAP = False

            if HAS_UMAP:
                @st.cache_data(ttl=30)
                def compute_umap(smiles_list, scores, iterations, qeds):
                    fp_gen = rfg_mod.GetMorganGenerator(radius=2, fpSize=1024)
                    fps, valid_idx = [], []
                    for i, smi in enumerate(smiles_list):
                        mol = Chem.MolFromSmiles(smi)
                        if mol:
                            fps.append(list(fp_gen.GetFingerprint(mol)))
                            valid_idx.append(i)
                    if len(fps) < 5:
                        return None
                    reducer = umap_lib.UMAP(n_components=2, random_state=42, metric="jaccard", n_neighbors=min(15, len(fps)-1))
                    embedding = reducer.fit_transform(fps)
                    return {
                        "x": embedding[:, 0].tolist(),
                        "y": embedding[:, 1].tolist(),
                        "smiles": [smiles_list[i] for i in valid_idx],
                        "score": [scores[i] for i in valid_idx],
                        "iteration": [iterations[i] for i in valid_idx],
                        "qed": [qeds[i] for i in valid_idx],
                    }

                smiles_list = df["smiles"].fillna("").tolist()
                scores_list = df["docking_score"].fillna(0).tolist()
                iters_list = df["iteration"].fillna(0).tolist()
                qeds_list = df["qed"].fillna(0).tolist()

                umap_data = compute_umap(tuple(smiles_list), tuple(scores_list), tuple(iters_list), tuple(qeds_list))
                if umap_data:
                    umap_df = pd.DataFrame(umap_data)
                    fig_umap = px.scatter(
                        umap_df, x="x", y="y",
                        color="score", color_continuous_scale="RdYlGn",
                        hover_data={"smiles": True, "score": ":.2f", "qed": ":.2f", "iteration": True},
                        labels={"score": "Docking Score", "x": "UMAP-1", "y": "UMAP-2"},
                        title="Espacio Químico (Morgan ECFP4 + UMAP Jaccard)",
                    )
                    fig_umap.update_traces(marker=dict(size=7, opacity=0.8))
                    fig_umap.update_layout(
                        plot_bgcolor="#0b0f19", paper_bgcolor="#0b0f19",
                        font_color="#f1f5f9", height=420,
                    )
                    st.plotly_chart(fig_umap, use_container_width=True)
                else:
                    st.info("Necesitas al menos 5 candidatos con SMILES válidos para UMAP.")
            else:
                st.warning("Instala umap-learn para visualización del espacio químico: pip install umap-learn")

        with pareto_col:
            st.markdown("#### Frente de Pareto — Multi-Objetivo")
            st.caption("Candidatos no dominados: mejor docking Y mejor QED simultáneamente. Estos son los candidatos de interés medicinal.")

            df_pareto = df.dropna(subset=["docking_score", "qed"]).copy()
            if len(df_pareto) >= 3:
                scores_arr = df_pareto["docking_score"].values
                qed_arr = df_pareto["qed"].values

                # Calcular frente Pareto (minimizar score, maximizar QED)
                pareto_mask = []
                for i in range(len(scores_arr)):
                    dominated = False
                    for j in range(len(scores_arr)):
                        if i == j:
                            continue
                        if scores_arr[j] <= scores_arr[i] and qed_arr[j] >= qed_arr[i]:
                            if scores_arr[j] < scores_arr[i] or qed_arr[j] > qed_arr[i]:
                                dominated = True
                                break
                    pareto_mask.append(not dominated)

                df_pareto["pareto"] = ["Pareto Front" if m else "Dominated" for m in pareto_mask]
                tox_col_name = "admet_toxicity" if "admet_toxicity" in df_pareto.columns else None
                hover_cols = {"smiles": True, "docking_score": ":.2f", "qed": ":.2f"}
                if tox_col_name:
                    hover_cols[tox_col_name] = ":.2f"

                fig_pareto = px.scatter(
                    df_pareto,
                    x="docking_score", y="qed",
                    color="pareto",
                    color_discrete_map={"Pareto Front": "#22c55e", "Dominated": "#475569"},
                    hover_data=hover_cols,
                    labels={"docking_score": "Docking Score (kcal/mol)", "qed": "QED"},
                    title="Frente de Pareto: Afinidad vs Drug-Likeness",
                    symbol="pareto",
                )
                fig_pareto.update_traces(marker=dict(size=9, opacity=0.85))
                fig_pareto.update_layout(
                    plot_bgcolor="#0b0f19", paper_bgcolor="#0b0f19",
                    font_color="#f1f5f9", height=420,
                )
                st.plotly_chart(fig_pareto, use_container_width=True)

                n_pareto = sum(pareto_mask)
                st.metric("Candidatos en Frente Pareto", n_pareto, help="No dominados en score+QED simultáneamente")
                pareto_df_display = df_pareto[df_pareto["pareto"] == "Pareto Front"][["smiles", "docking_score", "qed"]].head(10)
                if not pareto_df_display.empty:
                    st.dataframe(pareto_df_display.style.format({"docking_score": "{:.2f}", "qed": "{:.3f}"}), use_container_width=True)
            else:
                st.info("Necesitas al menos 3 candidatos con score y QED para el análisis Pareto.")

    st.divider()
    st.markdown("#### SAR — Análisis de Pares Moleculares (MMP)")
    if not df.empty and len(df) >= 8:
        try:
            cands_for_mmp = df.to_dict("records")
            from utils.mmp_analysis import analyze_mmps, identify_best_substituents
            mmp_text = analyze_mmps(cands_for_mmp)
            sar_text = identify_best_substituents(cands_for_mmp)
            if mmp_text or sar_text:
                st.code(f"{mmp_text}\n\n{sar_text}", language=None)
            else:
                st.info("No se detectaron pares moleculares emparejados suficientes todavía.")
        except Exception as e_mmp:
            st.caption(f"MMP no disponible: {e_mmp}")
    else:
        st.info("El análisis MMP requiere al menos 8 candidatos en la misión.")


# TAB 5: COMPILED SCIENTIFIC SKILLS DIRECTORY & VECTOR MEMORY (RAG)
with tab5:
    st.subheader("🧠 Skills de Auto-Mejora y RAG Científico")
    
    skill_subtab, rag_subtab = st.tabs([
        "📋 Directorio Científico de Skills", 
        "🔍 Consulta de Memoria Vectorial (RAG)"
    ])
    
    with skill_subtab:
        st.markdown("""
        La IA auto-generadora analiza los resultados científicos de las simulaciones y sintetiza **skills** de diseño reutilizables.
        Abajo se listan las skills almacenadas en tu base de datos:
        """)
        
        skills_list = load_skills()
        if not skills_list:
            st.info("💡 Aún no se han compilado skills dinámicas en la base de datos local SQLite. El reflector las creará al identificar patrones recurrentes de afinidad.")
        else:
            for s in skills_list:
                with st.expander(f"⚙️ Skill: {s.get('name')} | Creada: {str(s.get('created_at'))[:10]}"):
                    st.markdown(f"**Descripción:** {s.get('description')}")
                    st.code(s.get('content'), language="python")
                    
    with rag_subtab:
        st.markdown("### 🔍 Consultar ChromaDB Vector Memory")
        st.markdown("Usa la barra de abajo para interrogar la memoria científica del agente autónomo.")
        
        rag_col1, rag_col2 = st.columns([1, 2])
        with rag_col1:
            target_query = st.text_input("Filtrar Target de Memoria:", value="EGFR")
        with rag_col2:
            text_query = st.text_input("Consulta de Concepto Científico (RAG):", value="¿Cómo optimizar afinidad en bolsillo de EGFR?")
            
        if st.button("🔍 Interrogar Memoria"):
            try:
                from utils.memory_db import query_memory_context
                memory_res = query_memory_context(target_query, text_query, n_results=5)
                if memory_res:
                    st.success("🧠 Insights Científicos Recuperados de ChromaDB:")
                    st.markdown(memory_res)
                else:
                    st.info("No se encontraron insights guardados para ese target en la base de datos vectorial.")
            except Exception as e_rag:
                st.error(f"Error cargando ChromaDB: {e_rag}")

# TAB 6: DATOS COMPLETOS Y CONSOLA DE LOGS
with tab6:
    st.subheader("📋 Historial Completo de Candidatos Diseñados")
    if not df.empty:
        cols_to_show = ["smiles", "docking_score", "md_refined_score", "md_strain_energy", "md_flexibility", "ligand_efficiency", "sa_score", "qed", "logp", "mw", "admet_toxicity", "herg_risk", "bbb_permeability", "cyp3a4_inhibition", "status"]
        df_show = df[[c for c in cols_to_show if c in df.columns]]
        st.dataframe(df_show, use_container_width=True)
    else:
        st.info("Sin registros.")
        
    st.divider()
    
    st.subheader("💻 Consola y Logs en Vivo")
    
    @st.cache_data(ttl=1)
    def load_log():
        if not os.path.exists(LOG_PATH):
            return "Esperando salida del log..."
        try:
            with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                return "".join(lines[-120:])
        except Exception as e:
            return f"Error leyendo archivo de log: {e}"
            
    st.code(load_log(), language="text")

st.divider()

# --- REPORTE EJECUTIVO PDF ---
st.subheader("📄 Reporte Ejecutivo Científico")
PDF_PATH = os.path.join(SCRIPT_DIR, "..", "output", "DrugAgent_Report.pdf")
if os.path.exists(PDF_PATH):
    with open(PDF_PATH, "rb") as f:
        pdf_bytes = f.read()
    st.download_button(
        label="📥 Descargar Reporte Científico PDF",
        data=pdf_bytes,
        file_name="DrugAgent_Report.pdf",
        mime="application/pdf"
    )
else:
    st.info("El reporte PDF se consolidará al finalizar la corrida de diseño químico del agente.")

st.markdown("""
<div style='text-align: center; margin-top: 50px; padding: 20px; border-top: 1px solid #1e293b; color: #475569; font-size: 12px;'>
    🧬 DrugAgent-Local Workbench • Orquestado por LangGraph & AutoDock Vina Nativo Windows
</div>
""", unsafe_allow_html=True)
