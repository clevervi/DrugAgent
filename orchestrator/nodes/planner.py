"""
Nodo Planner: Groq planifica la estrategia inicial del agente.
"""
import os
from datetime import datetime

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
import time

from ..state import AgentState


def planner_node(state: AgentState) -> dict:
    """Planificador inicial: establece estrategia para el target dado."""
    target = state.get("target_name", "EGFR")
    
    # Cargar prompt personalizado desde config.yaml
    import yaml
    planner_prompt_tmpl = "En 2 oraciones: ¿Cuáles son las características clave que debe tener un inhibidor de {target}? Sé muy conciso y científico."
    try:
        with open("./config/config.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        planner_prompt_tmpl = cfg.get("prompts", {}).get("planner_prompt", planner_prompt_tmpl)
    except Exception:
        pass
    prompt_text = planner_prompt_tmpl.format(target=target)

    # Verificar si se configuró un LLM local
    local_base = os.environ.get("LOCAL_LLM_BASE_URL", "").strip()
    if local_base:
        print(f"\n🎯 PLANNER [LOCAL LLM]: Planificando estrategia usando Local LLM para {target}...")
        try:
            from utils.local_llm import LocalChatModel
            model_name = os.environ.get("LOCAL_LLM_MODEL", "llama3")
            local_llm = LocalChatModel(base_url=local_base, model_name=model_name)
            msg = local_llm.invoke(prompt_text)
            context = msg.content
            print(f"   📋 Contexto (Local LLM): {context[:100]}...")
            return {
                "memory_context": context,
                "next_action": "generate",
                "iteration_logs": [f"[Plan] Planner: estrategia definida para {target} (Local LLM)"],
                "last_updated": datetime.now().isoformat(),
            }
        except Exception as e:
            print(f"   ⚠️ Local LLM falló en Planner ({e}). Rebotando a fallbacks...")

    offline = os.environ.get("OFFLINE_MODE", "False").lower() in ["true", "1", "yes"]
    if offline:
        print(f"\n🎯 PLANNER [MODO OFFLINE]: Planificando estrategia local para target {target}...")
        context = f"Inhibidores de {target}: optimizar afinidad de acoplamiento físico, estabilidad estructural y perfil farmacocinético local."
        print(f"   ✓ Planner completado localmente.")
        return {
            "memory_context": context,
            "next_action": "generate",
            "iteration_logs": [f"[Plan] Planner: estrategia definida para {target} (Modo Offline)"],
        }
        
    print(f"\n🎯 PLANNER: Planificando estrategia para target {target} (Esperando 4s para rate-limit)...")
    time.sleep(4)
    
    groq_api_key = os.environ.get("GROQ_API_KEY", "")
    
    if groq_api_key and not groq_api_key.startswith("gsk_REEMPLAZA"):
        try:
            llm = ChatGroq(
                model=os.environ.get("GROQ_LIGHT_MODEL", "llama-3.1-8b-instant"),  # Modelo ligero para planning
                temperature=0.1,
                max_tokens=512,
                groq_api_key=groq_api_key,
            )
            
            msg = llm.invoke([HumanMessage(content=prompt_text)])
            context = msg.content
            print(f"   📋 Contexto: {context[:100]}...")
        except Exception as e:
            print(f"   ⚠️ Groq falló en Planner ({e}). Intentando Gemini...")
            gemini_key = os.environ.get("GEMINI_API_KEY", "")
            if gemini_key:
                try:
                    from langchain_google_genai import ChatGoogleGenerativeAI
                    gemini_model = os.environ.get("GEMINI_LIGHT_MODEL", "gemini-2.5-flash-lite")
                    llm_fb = ChatGoogleGenerativeAI(model=gemini_model, temperature=0.1, google_api_key=gemini_key)
                    msg_fb = llm_fb.invoke([HumanMessage(content=prompt_text)])
                    context = msg_fb.content
                    print(f"   📋 Contexto (Gemini): {context[:100]}...")
                except Exception as e2:
                    print(f"   ⚠️ Gemini falló ({e2}). Usando contexto base.")
                    context = f"Inhibidores de {target}: optimizar binding affinity y drug-likeness."
            else:
                context = f"Inhibidores de {target}: optimizar binding affinity y drug-likeness."
    else:
        context = f"Inhibidores de {target}: optimizar binding affinity y drug-likeness."
    
    print(f"   ✓ Planner completado. Iniciando generación...")
    
    return {
        "memory_context": context,
        "next_action": "generate",
        "iteration_logs": [f"[Plan] Planner: estrategia definida para {target}"],
        "last_updated": datetime.now().isoformat(),
    }
