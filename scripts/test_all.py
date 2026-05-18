#!/usr/bin/env python3
"""
Script de test completo para verificar que el entorno DrugAgent está correctamente instalado.
Corre todos los checks necesarios antes del primer loop.
"""
import sys
import os

# Forzar UTF-8 para Windows
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

print("=" * 60)
print("   DrugAgent - Test de Infraestructura")
print("=" * 60)

results = {}

# ─────────────────────────────────────────────
# Test 1: Python version
# ─────────────────────────────────────────────
print("\n[1/8] Python version...")
version = sys.version_info
if version.major == 3 and version.minor >= 11:
    print(f"   ✅ Python {version.major}.{version.minor}.{version.micro}")
    results["python"] = True
else:
    print(f"   ❌ Python {version.major}.{version.minor} - Se requiere 3.11+")
    results["python"] = False

# ─────────────────────────────────────────────
# Test 2: RDKit
# ─────────────────────────────────────────────
print("\n[2/8] RDKit...")
try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, QED, AllChem
    from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
    
    mol = Chem.MolFromSmiles("c1ccc(Nc2nccc(-c3cccnc3)n2)cc1")
    mw = Descriptors.ExactMolWt(mol)
    qed = QED.qed(mol)
    
    # Test filtros
    params = FilterCatalogParams()
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
    catalog = FilterCatalog(params)
    
    print(f"   ✅ RDKit OK | MW: {mw:.2f} | QED: {qed:.3f} | PAINS filter: OK")
    results["rdkit"] = True
except Exception as e:
    print(f"   ❌ RDKit: {e}")
    results["rdkit"] = False

# ─────────────────────────────────────────────
# Test 3: PyTorch + CUDA
# ─────────────────────────────────────────────
print("\n[3/8] PyTorch + CUDA...")
try:
    import torch
    cuda = torch.cuda.is_available()
    print(f"   {'✅' if cuda else '⚠️ '} PyTorch {torch.__version__} | CUDA: {cuda}")
    if cuda:
        gpu_name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"        GPU: {gpu_name} | VRAM: {vram:.1f} GB")
    results["pytorch"] = True
    results["cuda"] = cuda
except Exception as e:
    print(f"   ❌ PyTorch: {e}")
    results["pytorch"] = False
    results["cuda"] = False

# ─────────────────────────────────────────────
# Test 4: LangGraph + LangChain
# ─────────────────────────────────────────────
print("\n[4/8] LangGraph + LangChain...")
try:
    import langgraph
    import langchain
    import langchain_community
    import importlib.metadata
    
    try:
        lg_ver = langgraph.__version__
    except AttributeError:
        try:
            lg_ver = importlib.metadata.version("langgraph")
        except:
            lg_ver = "desconocida"
            
    print(f"   ✅ LangGraph {lg_ver} | LangChain {langchain.__version__}")
    results["langgraph"] = True
except Exception as e:
    print(f"   ❌ LangGraph/LangChain: {e}")
    results["langgraph"] = False

# ─────────────────────────────────────────────
# Test 5: Groq API
# ─────────────────────────────────────────────
print("\n[5/8] Groq API...")
try:
    from langchain_groq import ChatGroq
    from groq import Groq
    
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key or api_key.startswith("gsk_REEMPLAZA"):
        # Intentar cargar desde .env
        try:
            from dotenv import load_dotenv
            load_dotenv(".env")
            api_key = os.environ.get("GROQ_API_KEY", "")
        except:
            pass
    
    if api_key and not api_key.startswith("gsk_REEMPLAZA"):
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "Di 'OK' solo eso."}],
            max_tokens=10
        )
        msg = response.choices[0].message.content
        print(f"   ✅ Groq API conectado | Respuesta: '{msg}'")
        results["groq"] = True
    else:
        print("   ⚠️  GROQ_API_KEY no configurada. Agrega tu key en .env")
        print("        Obtén una gratis en: https://console.groq.com")
        results["groq"] = False
except Exception as e:
    print(f"   ❌ Groq: {e}")
    results["groq"] = False

# ─────────────────────────────────────────────
# Test 6: ChromaDB + MLflow
# ─────────────────────────────────────────────
print("\n[6/8] ChromaDB + MLflow...")
try:
    import chromadb
    import mlflow
    
    client = chromadb.Client()
    col = client.get_or_create_collection("test")
    col.add(documents=["test doc"], ids=["test1"])
    
    print(f"   ✅ ChromaDB {chromadb.__version__} | MLflow {mlflow.__version__}")
    results["memory"] = True
except Exception as e:
    print(f"   ❌ ChromaDB/MLflow: {e}")
    results["memory"] = False

# ─────────────────────────────────────────────
# Test 7: AutoDock Vina
# ─────────────────────────────────────────────
print("\n[7/8] AutoDock Vina...")
try:
    import subprocess
    import platform
    from pathlib import Path
    
    native_vina = Path("tools/vina/vina.exe")
    if platform.system() == "Windows" and native_vina.exists():
        cmd = [str(native_vina), "--version"]
        print(f"   🔎 Detectado Vina nativo Windows en: {native_vina}")
    elif platform.system() == "Windows":
        # Fallback a WSL2 si no existe el nativo
        cmd = ["wsl", "-d", "Ubuntu-22.04", "--", "vina", "--version"]
        print("   🔎 Buscando Vina en WSL2 (Ubuntu-22.04)...")
    else:
        cmd = ["vina", "--version"]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        version_line = (result.stdout + result.stderr).split('\n')[0]
        print(f"   ✅ {version_line}")
        results["vina"] = True
    else:
        print("   ⚠️  Vina no encontrado ni en local ni en WSL2.")
        results["vina"] = False
except Exception as e:
    print(f"   ⚠️  Vina error al ejecutar: {e}")
    results["vina"] = False

# ─────────────────────────────────────────────
# Test 8: Pipeline completo (sin Vina)
# ─────────────────────────────────────────────
print("\n[8/8] Test pipeline mock (sin docking real)...")
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from rdkit import Chem
    from rdkit.Chem import Descriptors, QED, Crippen, rdMolDescriptors
    from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
    
    # Simular una iteración completa
    test_smiles = [
        "c1ccc(Nc2nccc(-c3cccnc3)n2)cc1",
        "c1cnc(Nc2ccc(F)cc2)nc1",
        "O=C(Nc1ccc(Cl)cc1)c1cnccn1",
    ]
    
    params = FilterCatalogParams()
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
    pains_cat = FilterCatalog(params)
    
    valid = 0
    for smi in test_smiles:
        mol = Chem.MolFromSmiles(smi)
        if mol:
            mw = Descriptors.ExactMolWt(mol)
            qed = QED.qed(mol)
            pains = pains_cat.GetFirstMatch(mol) is not None
            valid += 1
    
    print(f"   ✅ Pipeline mock: {valid}/{len(test_smiles)} moléculas procesadas correctamente")
    results["pipeline"] = True
except Exception as e:
    print(f"   ❌ Pipeline: {e}")
    results["pipeline"] = False

# ─────────────────────────────────────────────
# Resumen
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("   RESUMEN DE TESTS")
print("=" * 60)

total = len(results)
passed = sum(1 for v in results.values() if v)
critical = all(results.get(k, False) for k in ["python", "rdkit", "langgraph", "pipeline"])

for name, ok in results.items():
    status = "✅" if ok else "❌"
    print(f"   {status} {name}")

print(f"\n   Resultado: {passed}/{total} tests pasados")

if critical:
    print("\n   🟢 LISTO para correr el pipeline en modo MOCK")
    print("      (sin docking real, para validar el loop)")
    
    if results.get("groq"):
        print("   🟢 LISTO para usar Groq API como cerebro")
    else:
        print("   🟡 Configura GROQ_API_KEY para activar el reflector inteligente")
    
    if results.get("vina"):
        print("   🟢 LISTO para docking real con AutoDock Vina Windows Nativo")
    else:
        print("   🟡 Instala Vina nativo en tools/vina/vina.exe o en WSL2 para docking real")
    
    print("\n   Para correr el agente:")
    print("   python run_agent.py --target EGFR --iterations 5")
else:
    print("\n   🔴 Tests críticos fallaron. Instala las dependencias:")
    print("   pip install -r requirements.txt")

print("=" * 60)
