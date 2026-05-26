"""
Nodo Generator: moléculas candidatas vía RDKit (scaffold hopping / mutación)
y opcionalmente LLM local o cloud. REINVENT4 no está integrado en runtime.
"""
import random
import uuid
import json
import os
from typing import List
from datetime import datetime

from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from rdkit import Chem
from rdkit import RDLogger
from rdkit.Chem import Descriptors, QED, Crippen, rdMolDescriptors, AllChem, rdFingerprintGenerator
from rdkit import DataStructs

# Supresión de logs de RDKit (errores de kekulización esperados durante mutación aleatoria)
RDLogger.DisableLog('rdApp.*')
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

from ..state import AgentState, MoleculeCandidate
import time
from pathlib import Path


def _load_skill_exec_allowlist() -> set:
    """
    Nombres de archivo (sin .md) permitidos para ejecutar bloques ```python en memory/skills/.
    config.yaml → skills.exec_allowlist (lista). Lista vacía = ningún exec.
    """
    try:
        import yaml
        p = Path("config/config.yaml")
        if not p.exists():
            return set()
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        raw = (cfg.get("skills") or {}).get("exec_allowlist")
        if raw is None:
            return set()
        return {str(x).strip() for x in raw if str(x).strip()}
    except Exception:
        return set()


def _normalize_llm_molecule_list(parsed):
    """
    El prompt pide un arreglo JSON [{\"smiles\": \"...\"}], pero LLMs locales suelen devolver
    un objeto {\"molecules\": [...]} o {\"candidates\": ...}. Si se hace for sobre un dict,
    se iteran las claves (str) y falla item.get('smiles').
    """
    if parsed is None:
        return []
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ("molecules", "candidates", "data", "items", "results", "compounds", "ligands", "outputs", "smiles_list"):
            v = parsed.get(key)
            if isinstance(v, list) and v:
                return v
        if isinstance(parsed.get("smiles"), str) and parsed.get("smiles").strip():
            return [parsed]
        for v in parsed.values():
            if isinstance(v, list) and v and all(isinstance(x, (dict, str)) for x in v):
                return v
    return []


def _iter_smiles_from_llm_rows(rows):
    for item in rows:
        if isinstance(item, str):
            s = item.strip()
            if s:
                yield s
            continue
        if isinstance(item, dict):
            smi = item.get("smiles") or item.get("SMILES") or item.get("smile")
            if isinstance(smi, str) and smi.strip():
                yield smi.strip()


# Scaffolds conocidos para inhibidores de kinasas (EGFR-like)
KINASE_SCAFFOLDS = [
    "c1ccc(Nc2nccc(-c3cccnc3)n2)cc1",          # Pyrimidine core (erlotinib-like)
    "c1cnc(Nc2ccc(F)cc2)nc1",                    # Pyrimidine aniline
    "O=C(Nc1ccc(Cl)cc1)c1cnccn1",               # Pyrazine amide
    "c1ccc(CNc2ncnc3ccccc23)cc1",               # Quinazoline (gefitinib-like)
    "CC(=O)Nc1ccc(-c2ccc(Nc3nccc(-c4cccnc4)n3)cc2)cc1",  # Extended
    "c1ccc(-c2cc(-c3ccccc3)nc(N)n2)cc1",        # Aminopyrimidine
    "O=C(c1ccc(F)cc1)Nc1nc2ccccc2s1",          # Benzothiazole
    "Nc1nc(Cl)nc(-c2ccccc2)n1",                 # Chloropyrimidine
]


def lipinski_filter(mol, profile: dict = None) -> bool:
    """Filtro Lipinski/Veber configurable por perfil de filtrado."""
    if mol is None:
        return False
    p = profile or {}
    mw = Descriptors.ExactMolWt(mol)
    logp = Crippen.MolLogP(mol)
    hbd = rdMolDescriptors.CalcNumHBD(mol)
    hba = rdMolDescriptors.CalcNumHBA(mol)
    tpsa = rdMolDescriptors.CalcTPSA(mol)
    rotbonds = rdMolDescriptors.CalcNumRotatableBonds(mol)
    return (
        mw <= p.get("max_mw", 500) and
        p.get("min_logp", -10.0) <= logp <= p.get("max_logp", 5.0) and
        hbd <= p.get("max_hbd", 5) and
        hba <= p.get("max_hba", 10) and
        tpsa <= p.get("max_tpsa", 140.0) and
        rotbonds <= p.get("max_rotbonds", 10)
    )


def compute_properties(mol) -> dict:
    """Calcula propiedades físico-químicas de una molécula."""
    return {
        "mw": Descriptors.ExactMolWt(mol),
        "logp": Crippen.MolLogP(mol),
        "hbd": rdMolDescriptors.CalcNumHBD(mol),
        "hba": rdMolDescriptors.CalcNumHBA(mol),
        "tpsa": rdMolDescriptors.CalcTPSA(mol),
        "qed": QED.qed(mol),
        "passes_lipinski": lipinski_filter(mol),
    }


def mutate_smiles(smiles: str) -> str:
    """Mutación de SMILES por sustitución de grupos funcionales (fallback)."""
    substitutions = [
        ("F", "Cl"), ("Cl", "F"), ("Cl", "Br"),
        ("N", "O"), ("O", "N"), ("c", "n"),
        ("CH3", "CF3"), ("NH2", "OH"),
        ("OC", "NC"), ("CC", "CCC"),
    ]
    result = smiles
    if random.random() < 0.5 and substitutions:
        old, new = random.choice(substitutions)
        if old in result:
            positions = [i for i in range(len(result)) if result.startswith(old, i)]
            if positions:
                pos = random.choice(positions)
                result = result[:pos] + new + result[pos+len(old):]
    return result


def brics_generate_from_scaffold(scaffold_smi: str, pool_scaffolds: list) -> str:
    """
    Generación molecular mediante descomposición BRICS y recombinación de fragmentos.
    Produce moléculas quimicamente más plausibles que la mutación de strings.
    Fallback a mutate_smiles si falla.
    """
    from rdkit.Chem.BRICS import BRICSDecompose, BRICSBuild
    mol = Chem.MolFromSmiles(scaffold_smi)
    if mol is None:
        return mutate_smiles(scaffold_smi)
    try:
        primary_frags = list(BRICSDecompose(mol, minFragmentSize=3))
        if not primary_frags:
            return mutate_smiles(scaffold_smi)

        # Mezclar fragmentos de 1-2 scaffolds adicionales aleatorios
        extra_frags: list = []
        sample_pool = random.sample(pool_scaffolds, min(2, len(pool_scaffolds)))
        for esmi in sample_pool:
            emol = Chem.MolFromSmiles(esmi)
            if emol:
                extra_frags.extend(BRICSDecompose(emol, minFragmentSize=3))

        all_frag_smiles = list(set(primary_frags + extra_frags))
        frag_mols = [Chem.MolFromSmiles(f) for f in all_frag_smiles]
        frag_mols = [fm for fm in frag_mols if fm is not None]
        if not frag_mols:
            return mutate_smiles(scaffold_smi)

        selected_frags = random.sample(frag_mols, min(6, len(frag_mols)))
        for nm in BRICSBuild(selected_frags):
            try:
                new_smi = Chem.MolToSmiles(nm)
                if new_smi and Chem.MolFromSmiles(new_smi):
                    return new_smi
            except Exception:
                continue
    except Exception:
        pass
    return mutate_smiles(scaffold_smi)


def check_similarity_blacklist(smiles: str, blacklist_smiles: list, threshold: float = 0.85) -> bool:
    """
    Compara smiles contra la lista de smiles prohibidos (blacklist_smiles) usando similitud Morgan/Tanimoto.
    Retorna True si smiles es idéntico o tiene una similitud >= threshold.
    """
    if not blacklist_smiles:
        return False
    mol = Chem.MolFromSmiles(smiles)
    if not mol:
        return False
    
    try:
        fp_gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
        query_fp = fp_gen.GetFingerprint(mol)
    except Exception:
        return False
        
    for target_smi in blacklist_smiles:
        if smiles == target_smi:
            return True
        t_mol = Chem.MolFromSmiles(target_smi)
        if not t_mol:
            continue
        try:
            target_fp = fp_gen.GetFingerprint(t_mol)
            similarity = DataStructs.TanimotoSimilarity(query_fp, target_fp)
            if similarity >= threshold:
                return True
        except Exception:
            continue
    return False


class DeepGenerativeModel:
    """
    Adaptador para modelos generativos profundos (REINVENT4 / GFlowNet).
    Actualmente opera en 'Proxy Mode' usando Scaffold Hopping + Mutación 
    dirigida hasta que el backend GPU esté disponible.
    """
    def __init__(self, use_gpu_backend: bool = False):
        self.use_gpu_backend = use_gpu_backend
        if self.use_gpu_backend:
            print("⏳ Inicializando modelo generativo REINVENT4 en GPU...")
            
    def generate_batch(self, n: int, scaffolds: List[str], previous_smiles: List[str], skills: dict, workflow_mode: str = "de_novo", parent_smiles: str = None, target: str = "EGFR", memory_context: str = "") -> List[str]:
        if self.use_gpu_backend:
            pass

        # Cargar perfil de filtrado (standard / permissive / cns / natural_products)
        from utils.guardrails import load_filter_profile
        _profile = load_filter_profile()

        valid_smiles = []

        # Compilar lista negra de SMILES descubiertos recientemente / breakthroughs
        blacklist_smiles = []
        try:
            breakthrough_path = Path("data/breakthroughs.json")
            if breakthrough_path.exists():
                with open(breakthrough_path, "r", encoding="utf-8") as f:
                    bt_list = json.load(f)
                for item in bt_list:
                    smi = item.get("smiles")
                    if smi and smi not in blacklist_smiles:
                        blacklist_smiles.append(smi)
        except Exception as e_bt:
            print(f"   ⚠️ Error cargando avances para lista negra de similitud: {e_bt}")
            
        # Añadir candidatos previos del estado actual si existen
        if previous_smiles:
            for smi in previous_smiles:
                if smi not in blacklist_smiles:
                    blacklist_smiles.append(smi)
        
        # Cargar prompt base e inyectar configuraciones
        import yaml
        generator_prompt_tmpl = """
Eres un experto en química computacional. Diseña {n} moléculas inhibidoras para la diana terapéutica: {target}.
MODO DE GENERACIÓN: {workflow_mode}.

RESTRICCIONES ESTRICTAS:
1. Deben ser cadenas SMILES sintácticamente válidas (parseables por RDKit).
2. Deben cumplir la Regla de los 5 de Lipinski (Peso < 500, LogP < 5).
3. Evitar subestructuras tóxicas o reactivas (PAINS).
{optional_parent_or_scaffolds}
{memory_context_section}
Responde ÚNICAMENTE con un arreglo JSON válido, sin bloques de código Markdown ni texto adicional. Formato:
[
  {{"smiles": "c1ccccc1"}},
  {{"smiles": "CC(=O)O"}}
]
"""
        try:
            with open("./config/config.yaml", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            generator_prompt_tmpl = cfg.get("prompts", {}).get("generator_prompt", generator_prompt_tmpl)
        except Exception:
            pass

        if workflow_mode == "lead_opt" and parent_smiles:
            optional_parent_or_scaffolds = f"\nUsa esta molécula como punto de partida y aplica bioisosterismo para optimizarla: {parent_smiles}\n"
        else:
            optional_parent_or_scaffolds = f"\nUsa estos scaffolds como base estructural sugerida: {', '.join(scaffolds[:3])}\n"

        memory_context_section = ""
        if memory_context:
            memory_context_section = f"\nCONTEXTO DE CORRIDAS PREVIAS (RAG):\nAquí hay lecciones y aprendizajes científicos previos recuperados de la base de datos de conocimiento:\n{memory_context}\n"

        prompt = generator_prompt_tmpl.format(
            n=n,
            target=target,
            workflow_mode=workflow_mode,
            optional_parent_or_scaffolds=optional_parent_or_scaffolds,
            memory_context_section=memory_context_section
        )

        # 0. INTENTO DE GENERACIÓN POR LOCAL LLM
        local_base = os.environ.get("LOCAL_LLM_BASE_URL", "").strip()
        if local_base:
            print(f"   🔌 [LOCAL LLM]: Generando moléculas con LLM local en {local_base}...")
            try:
                from utils.local_llm import LocalChatModel
                model_name = os.environ.get("LOCAL_LLM_MODEL", "llama3")
                # Forzar temperatura=0.8 para aumentar la diversidad y creatividad del LLM local
                llm = LocalChatModel(base_url=local_base, model_name=model_name, temperature=0.8)
                response = llm.invoke(prompt)
                
                content = response.content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                
                data = json.loads(content.strip())
                rows = _normalize_llm_molecule_list(data)
                for smi in _iter_smiles_from_llm_rows(rows):
                    mol = Chem.MolFromSmiles(smi)
                    if mol and lipinski_filter(mol, _profile):
                        canonical = Chem.MolToSmiles(mol)
                        if canonical not in valid_smiles and (not previous_smiles or canonical not in previous_smiles):
                            if check_similarity_blacklist(canonical, blacklist_smiles, threshold=0.85):
                                print(f"   [DIVERSIDAD]: Molécula rechazada por alta similitud Tanimoto (>=0.85).")
                                continue
                            from utils.guardrails import validate_molecular_safety
                            is_safe, _ = validate_molecular_safety(canonical)
                            if is_safe:
                                valid_smiles.append(canonical)

                if valid_smiles:
                    print(f"   [Local LLM] Se generaron {len(valid_smiles)} SMILES válidos y estructuralmente diversos.")
                    n_missing = n - len(valid_smiles)
                    if n_missing <= 0:
                        return valid_smiles
                    n = n_missing
            except Exception as e_local:
                print(f"   [Local LLM] Falló la generación local ({e_local}). Rebotando a fallbacks...")

        # 1. INTENTO DE GENERACIÓN POR IA CLOUD (Gemini o Groq)
        offline = os.environ.get("OFFLINE_MODE", "False").lower() in ["true", "1", "yes"]
        if offline and not local_base:
            print("   🔌 [MODO OFFLINE]: Omitiendo APIs en la nube. Usando generador heurístico local...")
        elif not offline and not local_base:
            gemini_api_key = os.getenv("GEMINI_API_KEY", "")
            if gemini_api_key:
                try:
                    gemini_model = os.getenv("GEMINI_HEAVY_MODEL", "gemini-2.5-flash")
                    llm = ChatGoogleGenerativeAI(temperature=0.8, model=gemini_model, google_api_key=gemini_api_key)
                    response = llm.invoke(prompt)
                    
                    content = response.content.strip()
                    if content.startswith("```json"):
                        content = content[7:]
                    if content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                        
                    data = json.loads(content.strip())
                    rows = _normalize_llm_molecule_list(data)
                    for smi in _iter_smiles_from_llm_rows(rows):
                        mol = Chem.MolFromSmiles(smi)
                        if mol and lipinski_filter(mol, _profile):
                            canonical = Chem.MolToSmiles(mol)
                            if canonical not in valid_smiles and (not previous_smiles or canonical not in previous_smiles):
                                if check_similarity_blacklist(canonical, blacklist_smiles, threshold=0.85):
                                    continue
                                from utils.guardrails import validate_molecular_safety
                                is_safe, _ = validate_molecular_safety(canonical)
                                if is_safe:
                                    valid_smiles.append(canonical)

                    if valid_smiles:
                        print(f"   [Gemini LLM] Se generaron {len(valid_smiles)} SMILES válidos.")
                        n_missing = n - len(valid_smiles)
                        if n_missing <= 0:
                            return valid_smiles
                        n = n_missing
                except Exception as e:
                    print(f"   [Gemini LLM] Falló la generación ({e}). Intentando con Groq como respaldo...")
                    try:
                        groq_key = os.getenv("GROQ_API_KEY", "")
                        if groq_key and not groq_key.startswith("gsk_REEMPLAZA"):
                            from langchain_groq import ChatGroq
                            groq_model = os.getenv("GROQ_HEAVY_MODEL", "llama-3.3-70b-versatile")
                            llm_groq = ChatGroq(model=groq_model, temperature=0.8, max_tokens=2048, groq_api_key=groq_key)
                            response = llm_groq.invoke(prompt)

                            content = response.content.strip()
                            if content.startswith("```json"):
                                content = content[7:]
                            if content.startswith("```"):
                                content = content[3:]
                            if content.endswith("```"):
                                content = content[:-3]

                            data = json.loads(content.strip())
                            rows = _normalize_llm_molecule_list(data)
                            for smi in _iter_smiles_from_llm_rows(rows):
                                mol = Chem.MolFromSmiles(smi)
                                if mol and lipinski_filter(mol, _profile):
                                    canonical = Chem.MolToSmiles(mol)
                                    if canonical not in valid_smiles and (not previous_smiles or canonical not in previous_smiles):
                                        if check_similarity_blacklist(canonical, blacklist_smiles, threshold=0.85):
                                            continue
                                        from utils.guardrails import validate_molecular_safety
                                        is_safe, _ = validate_molecular_safety(canonical)
                                        if is_safe:
                                            valid_smiles.append(canonical)

                            if valid_smiles:
                                print(f"   [Groq LLM] Se generaron {len(valid_smiles)} SMILES válidos.")
                                n_missing = n - len(valid_smiles)
                                if n_missing <= 0:
                                    return valid_smiles
                                n = n_missing
                    except Exception as e_groq:
                        print(f"   [Groq LLM] Falló la generación de IA ({e_groq}). Usando fallback proxy heurístico...")

        # RAG Offline: Extraer scaffolds de la memoria si no tenemos LLM
        if memory_context:
            import re
            potential_smiles = re.findall(r'[A-Za-z0-9@+\-\[\]\(\)\\\/=#$,]{6,}', memory_context)
            extracted_scaffolds = []
            for ps in potential_smiles:
                if not ps.startswith("http") and not ps.startswith("file") and not ps.startswith("mol_"):
                    try:
                        mol = Chem.MolFromSmiles(ps)
                        if mol:
                            canonical = Chem.MolToSmiles(mol)
                            if canonical not in extracted_scaffolds and canonical not in scaffolds:
                                extracted_scaffolds.append(canonical)
                    except Exception:
                        pass
            if extracted_scaffolds:
                print(f"   🧠 [RAG Offline] Encontrados {len(extracted_scaffolds)} scaffolds científicos en memoria para mutación heurística:")
                for esmi in extracted_scaffolds[:3]:
                    print(f"      - {esmi}")
                scaffolds = (extracted_scaffolds * 4) + scaffolds
            
        # 2a. MODO REPURPOSING: seed desde compuestos activos de ChEMBL
        if workflow_mode == "repurposing":
            chembl_seeds = []
            try:
                from utils.chembl_client import fetch_approved_drugs_for_target
                chembl_seeds = fetch_approved_drugs_for_target(target, limit=20)
                if chembl_seeds:
                    print(f"   [Repurposing] {len(chembl_seeds)} compuestos activos obtenidos de ChEMBL para {target}")
            except Exception as e_chembl:
                print(f"   [Repurposing] No se pudo obtener de ChEMBL: {e_chembl}. Usando scaffolds locales.")
            if not chembl_seeds:
                chembl_seeds = scaffolds[:5]

            fp_gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
            from utils.guardrails import validate_molecular_safety
            for seed_smi in chembl_seeds:
                if len(valid_smiles) >= n:
                    break
                seed_mol = Chem.MolFromSmiles(seed_smi)
                if seed_mol is None:
                    continue
                seed_fp = fp_gen.GetFingerprint(seed_mol)
                attempts_seed = 0
                while len(valid_smiles) < n and attempts_seed < 30:
                    attempts_seed += 1
                    candidate = brics_generate_from_scaffold(seed_smi, scaffolds)
                    mol = Chem.MolFromSmiles(candidate)
                    if mol is None or not lipinski_filter(mol, _profile):
                        continue
                    sim = DataStructs.TanimotoSimilarity(seed_fp, fp_gen.GetFingerprint(mol))
                    if sim < 0.40:
                        continue
                    canonical = Chem.MolToSmiles(mol)
                    if canonical in valid_smiles or (previous_smiles and canonical in previous_smiles):
                        continue
                    if check_similarity_blacklist(canonical, blacklist_smiles, threshold=0.85):
                        continue
                    is_safe, _ = validate_molecular_safety(canonical)
                    if is_safe:
                        valid_smiles.append(canonical)
            if valid_smiles:
                print(f"   [Repurposing BRICS] Generados {len(valid_smiles)} análogos de activos ChEMBL.")
                return valid_smiles

        # 2b. MODO LEAD OPTIMIZATION con BRICS
        if workflow_mode == "lead_opt" and parent_smiles:
            parent_mol = Chem.MolFromSmiles(parent_smiles)
            if parent_mol:
                fp_gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
                parent_fp = fp_gen.GetFingerprint(parent_mol)
                from utils.guardrails import validate_molecular_safety
                attempts = 0
                max_attempts = n * 50
                use_brics = True

                while len(valid_smiles) < n and attempts < max_attempts:
                    attempts += 1
                    candidate = brics_generate_from_scaffold(parent_smiles, scaffolds) if use_brics else mutate_smiles(parent_smiles)
                    # Alterna entre BRICS y mutación para diversidad
                    use_brics = not use_brics

                    mol = Chem.MolFromSmiles(candidate)
                    if mol is None or not lipinski_filter(mol, _profile):
                        continue
                    cand_fp = fp_gen.GetFingerprint(mol)
                    similarity = DataStructs.TanimotoSimilarity(parent_fp, cand_fp)
                    if similarity < 0.50:
                        continue
                    canonical = Chem.MolToSmiles(mol)
                    is_safe, _ = validate_molecular_safety(canonical)
                    if not is_safe:
                        continue
                    if canonical in valid_smiles or (previous_smiles and canonical in previous_smiles):
                        continue
                    if check_similarity_blacklist(canonical, blacklist_smiles, threshold=0.85):
                        continue
                    valid_smiles.append(canonical)

                print(f"   [Lead Opt BRICS] Completado con {len(valid_smiles)} análogos.")
                return valid_smiles

        # 3. PROXY MODE: BRICS Scaffold Hopping (primario) + mutación string (fallback)
        from utils.guardrails import validate_molecular_safety
        attempts = 0
        max_attempts = n * 15

        while len(valid_smiles) < n and attempts < max_attempts:
            attempts += 1
            scaffold = random.choice(scaffolds)
            # BRICS con probabilidad 0.7, mutación string con 0.3
            if random.random() < 0.70:
                candidate = brics_generate_from_scaffold(scaffold, scaffolds)
            else:
                candidate = scaffold
                for _ in range(random.randint(1, 3)):
                    candidate = mutate_smiles(candidate)

            mol = Chem.MolFromSmiles(candidate)
            if mol is None or not lipinski_filter(mol, _profile):
                continue
            canonical = Chem.MolToSmiles(mol)
            is_safe, _ = validate_molecular_safety(canonical)
            if not is_safe:
                continue
            if canonical in valid_smiles or (previous_smiles and canonical in previous_smiles):
                continue
            if check_similarity_blacklist(canonical, blacklist_smiles, threshold=0.85):
                continue
            valid_smiles.append(canonical)

        return valid_smiles


def generator_node(state: AgentState) -> dict:
    """Nodo generador: produce batch de moléculas candidatas."""
    iteration = state.get("iteration", 0) + 1
    
    offline = os.environ.get("OFFLINE_MODE", "False").lower() in ["true", "1", "yes"]
    if offline:
        print(f"\n[Iter {iteration}] 🔬 GENERATOR [MODO OFFLINE]: Generando candidatos moleculares localmente...")
    else:
        print(f"\n[Iter {iteration}] 🔬 GENERATOR: Generando candidatos moleculares (Esperando 4s para rate-limit)...")
        time.sleep(4)
    
    # 1. Consulta RAG a ChromaDB para guiar la generación con lecciones previas (Opción C)
    memory_context = ""
    try:
        from utils.memory_db import query_memory_context
        target = state.get("target_name", "EGFR")
        memory_context = query_memory_context(target, f"insights e indicaciones científicas para diseñar inhibidores de {target}")
        if memory_context:
            print("   🧠 ChromaDB: Recuperado contexto de memoria vectorial para guiar la generación:")
            for line in memory_context.split('\n'):
                print(f"      {line}")
    except Exception as e:
        print(f"   ⚠️ No se pudo recuperar memoria de ChromaDB: {e}")
        
    # Obtener SMILES previos para evitar duplicados
    previous_smiles = [c["smiles"] for c in state.get("all_candidates", [])]
    
    # Obtener scaffolds sugeridos dinámicamente por la IA/Reflector
    priority_scaffolds = state.get("priority_scaffolds", [])
    active_scaffolds = KINASE_SCAFFOLDS.copy()
    if priority_scaffolds:
        # LLMs sometimes return motif notation (e.g. "O=C(Ar1)Ar2") instead of real SMILES; filter those out
        valid_priority = [s for s in priority_scaffolds if isinstance(s, str) and Chem.MolFromSmiles(s) is not None]
        n_bad = len(priority_scaffolds) - len(valid_priority)
        if n_bad:
            print(f"   ⚠️ {n_bad} scaffold(s) del Reflector descartados (SMILES inválido)")
        if valid_priority:
            print(f"   🎯 Generando con {len(valid_priority)} scaffolds priorizados por el Reflector!")
            active_scaffolds = (valid_priority * 3) + KINASE_SCAFFOLDS
        else:
            print(f"   ⚠️ Ningún scaffold del Reflector es SMILES válido; usando scaffolds base.")
    
    # Tamaño del batch (adaptivo: empieza pequeño)
    batch_size = min(20 + iteration * 2, 50)
    
    # Compilación y Ejecución en Caliente de la Skill si contiene código Python (Soporte dict y str)
    skills_data = state.get("skill_content", {})
    if not isinstance(skills_data, dict) and not isinstance(skills_data, str):
        skills_data = {}
    
    # Doble seguridad: cargar/sincronizar directamente desde el disco ./memory/skills
    if isinstance(skills_data, dict):
        try:
            from pathlib import Path
            SKILLS_DIR = Path("./memory/skills")
            if SKILLS_DIR.exists():
                for skill_file in SKILLS_DIR.glob("*.md"):
                    skills_data[skill_file.stem] = skill_file.read_text(encoding="utf-8")
        except Exception as e_load:
            print(f"   ⚠️ Error de sincronización al leer skills de disco: {e_load}")

    custom_func = None
    active_skill_name = None
    exec_allowlist = _load_skill_exec_allowlist()
    if isinstance(skills_data, dict) and not exec_allowlist:
        print("   ℹ️ skills.exec_allowlist vacío: no se ejecutará código Python desde memory/skills (solo guía markdown).")

    if isinstance(skills_data, dict):
        for s_name in sorted(skills_data.keys()):
            if s_name not in exec_allowlist:
                continue
            s_content = skills_data[s_name]
            if isinstance(s_content, str) and "```python" in s_content:
                try:
                    code_block = s_content.split("```python")[1].split("```")[0]
                    local_scope = {}
                    exec(code_block, globals(), local_scope)
                    for name, val in local_scope.items():
                        if callable(val):
                            custom_func = val
                            active_skill_name = s_name
                            print(f"   🎯 Skill de código compilada (allowlist) desde '{s_name}': '{name}'")
                            break
                    if custom_func:
                        break
                except Exception as es:
                    print(f"   ⚠️ Error compilando skill '{s_name}' en caliente: {es}")

    if not custom_func and isinstance(skills_data, str) and "```python" in skills_data and "dynamic_string_skill" in exec_allowlist:
        try:
            code_block = skills_data.split("```python")[1].split("```")[0]
            local_scope = {}
            exec(code_block, globals(), local_scope)
            for name, val in local_scope.items():
                if callable(val):
                    custom_func = val
                    active_skill_name = "dynamic_string_skill"
                    print(f"   🎯 Skill de código compilada exitosamente desde string: '{name}'")
                    break
        except Exception as es:
            print(f"   ⚠️ Error compilando skill string en caliente: {es}")

    # Instanciar el modelo generativo (proxy mode)
    gen_model = DeepGenerativeModel(use_gpu_backend=False)
    
    try:
        smiles_list = []
        skill_failures_dict = {}
        # Intentar usar la skill dinámica si fue compilada
        if custom_func:
            try:
                smiles_list = custom_func(batch_size, active_scaffolds)
                print(f"   ✓ Generación completada por la skill dinámica compilada ({len(smiles_list)} hits).")
            except Exception as e_skill:
                import traceback
                error_tb = traceback.format_exc()
                print(f"   ⚠️ Error ejecutando la skill dinámica: {e_skill}. Fallback al proxy...")
                skill_failures_dict[active_skill_name or "unknown_skill"] = error_tb
                custom_func = None
                
        if not custom_func:
            smiles_list = gen_model.generate_batch(
                n=batch_size,
                scaffolds=active_scaffolds,
                previous_smiles=previous_smiles,
                skills={},
                workflow_mode=state.get("workflow_mode", "de_novo"),
                parent_smiles=state.get("parent_smiles", None),
                target=target,
                memory_context=memory_context
            )
        
        # Crear objetos MoleculeCandidate
        candidates: List[MoleculeCandidate] = []
        for smi in smiles_list:
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                continue
            
            props = compute_properties(mol)
            
            candidate: MoleculeCandidate = {
                "smiles": smi,
                "mol_id": f"mol_{iteration}_{str(uuid.uuid4())[:6]}",
                "iteration": iteration,
                **props,
                "docking_score": None,
                "binding_affinity": None,
                "admet_toxicity": None,
                "admet_solubility": None,
                "admet_absorption": None,
                "herg_risk": None,
                "bbb_permeability": None,
                "cyp3a4_inhibition": None,
                "pains_alert": False,
                "brenk_alert": False,
                "sa_score": None,
                "ligand_efficiency": None,
                "md_rmsd": None,
                "md_refined_score": None,
                "md_strain_energy": None,
                "md_flexibility": None,
                "status": "generated",
                "score_final": None,
                "uncertainty": None,
            }
            candidates.append(candidate)
        
        print(f"[Iter {iteration}] ✓ Generados {len(candidates)} candidatos válidos (de {batch_size} intentados)")
        
        # Log del promedio de QED de la iteración
        qed_prom = sum(c['qed'] for c in candidates)/len(candidates) if candidates else 0.0
        log = f"[Iter {iteration}] Generator: {len(candidates)} moléculas generadas. QED promedio: {qed_prom:.3f}"
        
        return {
            "iteration": iteration,
            "current_batch": candidates,
            "next_action": "simulate",
            "iteration_logs": [log],
            "memory_context": memory_context or state.get("memory_context", ""),
            "skill_failures": skill_failures_dict,
            "last_updated": datetime.now().isoformat(),
        }
        
    except Exception as e:
        error_msg = f"[Iter {iteration}] ERROR en Generator: {str(e)}"
        print(f"❌ {error_msg}")
        return {
            "iteration": iteration,
            "current_batch": [],
            "next_action": "reflect",
            "failures": [error_msg],
            "error_count": state.get("error_count", 0) + 1,
            "skill_failures": {},
            "last_updated": datetime.now().isoformat(),
        }
