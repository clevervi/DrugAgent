"""
DrugAgent Main Orchestrator
Grafo LangGraph que conecta todos los nodos del agente cerrado.
"""
import uuid
from datetime import datetime
from typing import Literal

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import AgentState
from .nodes.planner import planner_node
from .nodes.generator import generator_node
from .nodes.simulator import simulator_node
from .nodes.analyzer import analyzer_node
from .nodes.reflector import reflector_node
from .nodes.md_simulator import md_simulator_node


# ─────────────────────────────────────────────
# Router: decide el siguiente nodo
# ─────────────────────────────────────────────

def router(state: AgentState) -> Literal["generate", "simulate", "analyze", "reflect", "output", "__end__"]:
    """Router condicional basado en el estado actual."""
    next_action = state.get("next_action", "generate")
    
    if state.get("error_count", 0) >= 10:
        print("⚠️  Demasiados errores consecutivos. Terminando...")
        return "__end__"
    
    if state.get("iteration", 0) >= state.get("max_iterations", 50):
        print(f"✅ Máximo de iteraciones alcanzado ({state['max_iterations']})")
        return "output"
    
    if state.get("requires_human_review", False):
        return "output"
    
    mapping = {
        "generate": "generate",
        "simulate": "simulate",
        "analyze": "analyze",
        "reflect": "reflect",
        "output": "output",
        "end": "__end__",
    }
    return mapping.get(next_action, "generate")


def analyze_router(state: AgentState) -> Literal["output", "md_simulate"]:
    """Router condicional desde el nodo analyze."""
    if state.get("requires_human_review", False) or state.get("next_action") == "output":
        print("⚠️ Se requiere revisión humana o la acción siguiente es output. Redirigiendo a output...")
        return "output"
    return "md_simulate"


def output_node(state: AgentState) -> dict:
    """Nodo final: genera reporte y prepara para revisión humana."""
    top = state.get("top_candidates", [])
    print(f"\n{'='*60}")
    print(f"🧬 DRUGAGENT - RESULTADOS FINALES")
    print(f"{'='*60}")
    print(f"Target: {state.get('target_name', 'N/A')}")
    print(f"Iteraciones: {state.get('iteration', 0)}")
    print(f"Total candidatos generados: {len(state.get('all_candidates', []))}")
    print(f"Top candidatos: {len(top)}")
    
    if top:
        print(f"\n📊 MEJORES CANDIDATOS:")
        for i, mol in enumerate(top[:5], 1):
            print(f"  {i}. SMILES: {mol['smiles'][:50]}...")
            print(f"     Score: {mol.get('docking_score', 'N/A')} kcal/mol")
            print(f"     QED: {mol.get('qed', 'N/A'):.3f}")
            print(f"     Toxicidad: {mol.get('admet_toxicity', 'N/A')}")
    
    print(f"\n💡 INSIGHTS GENERADOS: {len(state.get('insights', []))}")
    print(f"🧠 SKILLS NUEVAS: {len(state.get('new_skills_generated', []))}")
    print(f"{'='*60}\n")
    
    return {"next_action": "end"}


# ─────────────────────────────────────────────
# Construcción del grafo
# ─────────────────────────────────────────────

def build_graph(checkpoint_path: str = "./data/checkpoints.db"):
    """Construye y compila el grafo LangGraph."""
    
    workflow = StateGraph(AgentState)
    
    # Agregar nodos
    workflow.add_node("plan", planner_node)
    workflow.add_node("generate", generator_node)
    workflow.add_node("simulate", simulator_node)
    workflow.add_node("analyze", analyzer_node)
    workflow.add_node("md_simulate", md_simulator_node)
    workflow.add_node("reflect", reflector_node)
    workflow.add_node("output", output_node)
    
    # Punto de entrada
    workflow.set_entry_point("plan")
    
    # Edges estáticos
    workflow.add_edge("plan", "generate")
    workflow.add_edge("generate", "simulate")
    workflow.add_edge("simulate", "analyze")
    
    # Edge condicional desde analyze
    workflow.add_conditional_edges(
        "analyze",
        analyze_router,
        {
            "output": "output",
            "md_simulate": "md_simulate"
        }
    )
    
    workflow.add_edge("md_simulate", "reflect")
    
    # Edge condicional desde reflect
    workflow.add_conditional_edges(
        "reflect",
        router,
        {
            "generate": "generate",
            "simulate": "simulate",
            "analyze": "analyze",
            "reflect": "reflect",
            "output": "output",
            "__end__": END,
        }
    )
    
    workflow.add_edge("output", END)
    
    # MemorySaver: checkpointing en memoria (no requiere sqlite externo)
    memory = MemorySaver()
    graph = workflow.compile(checkpointer=memory)
    
    return graph


# ─────────────────────────────────────────────
# Función principal de ejecución
# ─────────────────────────────────────────────

def run_agent(
    target_name: str = "EGFR",
    target_pdb_id: str = "4HJO",
    max_iterations: int = 20,
    config_path: str = "./config/config.yaml",
    db_run_id: str = None,
    workflow_mode: str = "de_novo",
    therapeutic_area: str = "Oncología",
    indication_label: str = "Cáncer de Pulmón (EGFR)",
    parent_smiles: str = None
):
    """Ejecuta el agente de drug discovery."""
    
    import yaml
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    run_id = db_run_id if db_run_id else str(uuid.uuid4())[:8]
    
    # Estado inicial
    initial_state: AgentState = {
        "target_name": target_name,
        "target_pdb_id": target_pdb_id,
        "target_pdb_path": f"./data/receptors/{target_pdb_id}.pdb",
        "target_pdbqt_path": f"./data/receptors/{target_pdb_id}.pdbqt",
        "iteration": 0,
        "max_iterations": max_iterations,
        "all_candidates": [],
        "current_batch": [],
        "top_candidates": [],
        "best_score": 0.0,
        "avg_score_history": [],
        "diversity_score": 0.0,
        "active_skills": [],
        "skill_content": {},
        "memory_context": "",
        "priority_scaffolds": [],
        "iteration_logs": [],
        "failures": [],
        "insights": [],
        "new_skills_generated": [],
        "next_action": "generate",
        "error_count": 0,
        "requires_human_review": False,
        "start_time": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
        "run_id": run_id,
        "docking_mode": config.get("docking_mode", "auto"),
        "workflow_mode": workflow_mode,
        "therapeutic_area": therapeutic_area,
        "indication_label": indication_label,
        "parent_smiles": parent_smiles,
    }
    
    print(f"\n🚀 DrugAgent iniciado")
    print(f"   Target: {target_name} ({target_pdb_id})")
    print(f"   Run ID: {run_id}")
    print(f"   Workflow: {workflow_mode} | Área: {therapeutic_area}")
    print(f"   Indicación: {indication_label}")
    if parent_smiles:
        print(f"   SMILES Padre: {parent_smiles}")
    print(f"   Max iteraciones: {max_iterations}")
    print(f"   Tiempo inicio: {initial_state['start_time']}\n")
    
    graph = build_graph()
    
    # Configuración del thread para checkpointing
    thread_config = {"configurable": {"thread_id": run_id}}
    
    # Ejecutar
    final_state = graph.invoke(initial_state, config=thread_config)
    
    return final_state


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="DrugAgent - Closed-Loop Drug Discovery")
    parser.add_argument("--target", default="EGFR", help="Target terapéutico")
    parser.add_argument("--pdb", default="4HJO", help="PDB ID de la proteína")
    parser.add_argument("--iterations", type=int, default=20, help="Número de iteraciones")
    parser.add_argument("--workflow", default="de_novo", choices=["de_novo", "lead_opt"], help="Modo de workflow")
    parser.add_argument("--area", default="Oncología", help="Área terapéutica")
    parser.add_argument("--indication", default="Cáncer de Pulmón (EGFR)", help="Indicación clínica")
    parser.add_argument("--parent-smiles", default=None, help="SMILES de partida para optimización")
    args = parser.parse_args()
    
    result = run_agent(
        target_name=args.target,
        target_pdb_id=args.pdb,
        max_iterations=args.iterations,
        workflow_mode=args.workflow,
        therapeutic_area=args.area,
        indication_label=args.indication,
        parent_smiles=args.parent_smiles
    )
