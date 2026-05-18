"""
Nodo Reflector: Groq analiza los resultados y genera insights + nuevas skills.
Este es el componente de auto-mejora del sistema.
"""
import os
import json
import re
from datetime import datetime
from pathlib import Path
import yaml

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
import time

from ..state import AgentState


SKILLS_DIR = Path("./memory/skills")
SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def _persist_insights_to_chroma(target: str, iteration: int, insights) -> None:
    """Guarda insights del reflector en ChromaDB para RAG en el generator."""
    try:
        from utils.memory_db import save_insight_to_memory
        if not insights:
            return
        items = insights if isinstance(insights, list) else [insights]
        for ins in items:
            if isinstance(ins, str) and len(ins.strip()) >= 10:
                save_insight_to_memory(target, iteration, ins.strip())
    except Exception as e:
        print(f"   ⚠️ ChromaDB: no se pudieron persistir insights: {e}")


REFLECTOR_SYSTEM_PROMPT = """Eres el Científico-Reflector de un agente autónomo de drug discovery.

Tu trabajo es analizar los resultados de cada iteración del pipeline de diseño molecular y:
1. Identificar qué funcionó y qué falló
2. Extraer insights científicos accionables
3. Generar nuevas "skills" (procedimientos reutilizables) si identificas un problema recurrente
4. Decidir la estrategia para la próxima iteración

CONTEXTO DEL SISTEMA:
- Target terapéutico: {target_name}
- Pipeline: RDKit scaffold hopping → AutoDock Vina → ADMET filters
- Goal: Maximizar binding affinity (más negativo = mejor) con baja toxicidad

FORMATO DE RESPUESTA (JSON estricto, sin texto extra antes o despues):
{{
    "analysis": "Análisis breve de esta iteración",
    "insights": ["Insight 1", "Insight 2"],
    "next_strategy": "generate|simulate|analyze|reflect|output",
    "strategy_reason": "Por qué esta estrategia",
    "new_skill": {{
        "generate": true/false,
        "name": "nombre_skill_snake_case",
        "description": "Qué hace esta skill",
        "content": "Contenido markdown de la skill"
    }},
    "priority_scaffolds": ["SMILES1", "SMILES2"],
    "terminate": false
}}
"""


def load_skills(skills_dir: Path) -> dict:
    """Carga todas las skills disponibles desde disco."""
    skills = {}
    for skill_file in skills_dir.glob("*.md"):
        skills[skill_file.stem] = skill_file.read_text(encoding="utf-8")
    return skills


def save_new_skill(skill_name: str, content: str, description: str = ""):
    """Guarda una nueva skill generada por el reflector en disco y en la base de datos."""
    skill_path = SKILLS_DIR / f"{skill_name}.md"
    skill_path.write_text(content, encoding="utf-8")
    print(f"   💾 Nueva skill guardada en disco: {skill_name}.md")
    
    try:
        from orchestrator.db import db, init_db
        init_db()
        db.skill.upsert(
            where={
                "name": skill_name
            },
            data={
                "create": {
                    "name": skill_name,
                    "description": description or skill_name,
                    "content": content,
                },
                "update": {
                    "description": description or skill_name,
                    "content": content,
                }
            }
        )
        print(f"   Prisma: Skill '{skill_name}' sincronizada en base de datos SQLite.")
    except Exception as e:
        print(f"   ⚠️ No se pudo guardar la skill en la base de datos Prisma: {e}")


def reflector_node(state: AgentState) -> dict:
    """Nodo reflector: Groq analiza logs y genera insights/skills."""
    iteration = state.get("iteration", 0)
    current_batch = state.get("current_batch", [])
    all_candidates = state.get("all_candidates", [])
    top_candidates = state.get("top_candidates", [])
    failures = state.get("failures", [])
    
    docked_mols = [m for m in current_batch if m.get("docking_score") is not None]
    
    if docked_mols:
        best_this_iter = min(m["docking_score"] for m in docked_mols)
        avg_score = sum(m["docking_score"] for m in docked_mols) / len(docked_mols)
    else:
        best_this_iter = 0.0
        avg_score = 0.0

    try:
        from utils.breakthrough import check_and_register_breakthrough
        target_name = state.get("target_name", "EGFR")
        target_pdb_id = state.get("target_pdb_id", "4HJO")
        therapeutic_area = state.get("therapeutic_area", "Oncología")
        indication_label = state.get("indication_label", "Cáncer de Pulmón (EGFR)")
        
        for cand in current_batch:
            check_and_register_breakthrough(
                cand,
                target_name=target_name,
                target_pdb_id=target_pdb_id,
                therapeutic_area=therapeutic_area,
                indication_label=indication_label
            )
    except Exception as e_break:
        print(f"   ⚠️ Error evaluando avances científicos: {e_break}")

    def run_heuristic_offline():
        next_action = "generate"
        if iteration >= state.get("max_iterations", 50) - 1:
            next_action = "output"
        insight = f"Iteración {iteration}: {len(docked_mols)} moléculas dockeadas. Mejor score: {best_this_iter:.2f}"
        print(f"   ✓ Reflector completado localmente (Heurístico). Insights generados.")
        priority_scaffolds = []
        if docked_mols:
            best_mol = min(docked_mols, key=lambda x: x.get("docking_score", 0.0))
            if best_mol.get("docking_score", 0.0) < -7.5:
                priority_scaffolds = [best_mol.get("smiles")]
        insights_out = [insight, "Optimización de afinidad local basada en dinámica estructural."]
        _persist_insights_to_chroma(state.get("target_name", "EGFR"), iteration, insights_out)
        return {
            "next_action": next_action,
            "insights": insights_out,
            "priority_scaffolds": priority_scaffolds,
            "active_skills": list(load_skills(SKILLS_DIR).keys()),
            "skill_content": load_skills(SKILLS_DIR),
            "iteration_logs": [f"[Iter {iteration}] Reflector (Modo Offline Heurístico): {insight}"],
            "last_updated": datetime.now().isoformat(),
        }

    offline = os.environ.get("OFFLINE_MODE", "False").lower() in ["true", "1", "yes"]
    local_base = os.environ.get("LOCAL_LLM_BASE_URL", "").strip()

    top3_lines = [f"  - SMILES: {(m.get('smiles') or '')[:50]}, score: {m.get('docking_score', 'N/A')}" for m in top_candidates[:3]]
    iteration_summary = f"ITERACION {iteration} - RESUMEN:\nDockeados: {len(docked_mols)}\nScore promedio: {avg_score:.2f}\nTop:\n{chr(10).join(top3_lines)}"
    
    # Inyección de fallos de skills para Auto-Curación (Self-Healing)
    skill_failures = state.get("skill_failures", {})
    if skill_failures:
        iteration_summary += "\n\n❌ ALERTA: SE DETECTARON ERRORES DE EJECUCIÓN EN LAS SKILLS DINÁMICAS:"
        failed_names = []
        for name, err in skill_failures.items():
            failed_names.append(name)
            iteration_summary += f"\n\n--- SKILL DEFECTUOSA: '{name}' ---\nTraceback del error:\n{err}\n"
        primary = failed_names[0] if failed_names else "nombre_skill_snake_case"
        names_csv = ", ".join(repr(n) for n in failed_names)
        iteration_summary += (
            "\n⚠️ INSTRUCCIÓN CRÍTICA DE AUTO-CURACIÓN:\n"
            "Repara la(s) skill(s) fallidas: " + names_csv + ".\n"
            "Firma requerida del código: def <nombre>(batch_size: int, scaffolds: list) -> list[str] (solo SMILES).\n"
            "Retorna la skill corregida en JSON con \"new_skill\": {\n"
            '  "generate": true,\n'
            f'  "name": "{primary}",\n'
            '  "description": "Versión corregida y funcional",\n'
            '  "content": "markdown con bloque ```python ... ```"\n'
            "}\n"
            "(Si hay varias rotas, prioriza una corrección por iteración o nombres distintos por skill.)\n"
        )

    
    system_prompt = REFLECTOR_SYSTEM_PROMPT
    try:
        with open("./config/config.yaml") as f:
            cfg = yaml.safe_load(f)
            system_prompt = cfg.get("prompts", {}).get("reflector_prompt", system_prompt)
    except Exception: pass

    # Safe dictionary class to prevent KeyErrors when formatting customizable prompt strings
    class SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    docked_all = [m for m in all_candidates if m.get("docking_score") is not None]
    best_overall = min(m["docking_score"] for m in docked_all) if docked_all else best_this_iter

    format_dict = {
        "target": state.get("target_name", "EGFR"),
        "target_name": state.get("target_name", "EGFR"),
        "target_pdb_id": state.get("target_pdb_id", "4HJO"),
        "iteration": iteration,
        "max_iterations": state.get("max_iterations", 50),
        "total_candidates": len(all_candidates),
        "best_docking_score": f"{best_overall:.2f}",
        "candidates_data": iteration_summary,
        "memory_context": state.get("memory_context", ""),
    }
    system_prompt = system_prompt.format_map(SafeDict(format_dict))

    response_text = None
    
    if local_base:
        try:
            from utils.local_llm import LocalChatModel
            llm = LocalChatModel(base_url=local_base, model_name=os.environ.get("LOCAL_LLM_MODEL", "llama3"))
            response_text = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=iteration_summary)]).content
        except Exception as e_local:
            print(f"   ⚠️ [Local LLM] Falló: {e_local}")

    if response_text is None and not offline:
        groq_api_key = os.environ.get("GROQ_API_KEY", "")
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(model=os.environ.get("GEMINI_HEAVY_MODEL", "gemini-2.5-flash"), temperature=0.1, google_api_key=os.environ.get("GEMINI_API_KEY"))
            response_text = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=iteration_summary)]).content
        except Exception as e_gemini:
            print(f"   ⚠️ Falló Gemini: {e_gemini}")
            try:
                llm = ChatGroq(model=os.environ.get("GROQ_HEAVY_MODEL", "llama-3.3-70b-versatile"), temperature=0.1, groq_api_key=groq_api_key)
                for attempt in range(3):
                    try:
                        response_text = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=iteration_summary)]).content
                        break
                    except Exception as e:
                        if "429" in str(e) and attempt < 2: time.sleep(6)
                        else: raise e
            except Exception as e_groq:
                print(f"   ⚠️ Groq también falló: {e_groq}")

    if response_text is None:
        return run_heuristic_offline()

    try:
        analysis = {}
        try: analysis = json.loads(response_text)
        except:
            start, end = response_text.find('{'), response_text.rfind('}')
            if start != -1 and end != -1: analysis = json.loads(response_text[start:end+1])
            else: analysis = {"analysis": response_text[:200], "insights": [response_text[:150]], "next_strategy": "generate"}
        
        insights = analysis.get("insights", [response_text[:150]])
        next_action = analysis.get("next_strategy", "generate") if not analysis.get("terminate") else "output"
        
        new_skills = []
        skill_info = analysis.get("new_skill", {})
        if skill_info.get("generate"):
            save_new_skill(skill_info["name"], skill_info["content"], skill_info.get("description", ""))
            new_skills.append(skill_info["name"])

        insights_out = insights if isinstance(insights, list) else [insights]
        _persist_insights_to_chroma(state.get("target_name", "EGFR"), iteration, insights_out)

        return {
            "next_action": next_action,
            "insights": insights_out,
            "priority_scaffolds": analysis.get("priority_scaffolds", []),
            "new_skills_generated": new_skills,
            "active_skills": list(load_skills(SKILLS_DIR).keys()),
            "skill_content": load_skills(SKILLS_DIR),
            "iteration_logs": [f"[Iter {iteration}] Reflector: {analysis.get('analysis', 'OK')}"],
            "last_updated": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "next_action": "generate",
            "priority_scaffolds": [],
            "failures": [str(e)],
            "error_count": state.get("error_count", 0) + 1,
            "active_skills": list(load_skills(SKILLS_DIR).keys()),
            "skill_content": load_skills(SKILLS_DIR),
            "iteration_logs": [f"ERROR en Reflector: {str(e)}"],
            "last_updated": datetime.now().isoformat(),
        }
