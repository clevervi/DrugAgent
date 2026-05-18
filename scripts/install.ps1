#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Script de instalación completa para DrugAgent en Windows 11 + WSL2
.DESCRIPTION
    Instala WSL2, Ubuntu 22.04, Miniconda, y todas las dependencias del proyecto.
    Requiere ejecutar como Administrador.
#>

param(
    [switch]$SkipWSL,
    [switch]$SkipConda,
    [switch]$SkipDeps
)

$ErrorActionPreference = "Stop"

Write-Host "
╔══════════════════════════════════════════════════════════╗
║          DrugAgent - Instalador de Infraestructura       ║
║          Local + Groq Hybrid Drug Discovery Agent        ║
╚══════════════════════════════════════════════════════════╝
" -ForegroundColor Cyan

# ─────────────────────────────────────────────
# PASO 1: WSL2
# ─────────────────────────────────────────────
if (-not $SkipWSL) {
    Write-Host "[1/5] Instalando WSL2 + Ubuntu 22.04..." -ForegroundColor Yellow
    
    # Habilitar características de Windows
    Write-Host "      Habilitando Virtual Machine Platform..." -ForegroundColor Gray
    dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart | Out-Null
    dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart | Out-Null
    
    # Instalar WSL2 con Ubuntu
    wsl --install -d Ubuntu-22.04 --no-launch
    wsl --set-default-version 2
    
    Write-Host "      ✓ WSL2 instalado. IMPORTANTE: Necesitarás reiniciar el PC." -ForegroundColor Green
    Write-Host "      Después del reinicio, ejecuta este script de nuevo con -SkipWSL" -ForegroundColor Yellow
    
    $restart = Read-Host "      ¿Reiniciar ahora? (s/N)"
    if ($restart -eq 's' -or $restart -eq 'S') {
        Restart-Computer -Force
    }
    exit 0
}

Write-Host "[1/5] WSL2: Omitido (ya instalado)" -ForegroundColor Green

# ─────────────────────────────────────────────
# PASO 2: Verificar GPU en WSL2
# ─────────────────────────────────────────────
Write-Host "[2/5] Verificando acceso GPU desde WSL2..." -ForegroundColor Yellow
try {
    $gpuTest = wsl -d Ubuntu-22.04 -- bash -c "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'GPU_NOT_FOUND'"
    if ($gpuTest -match "GPU_NOT_FOUND" -or $gpuTest -eq "") {
        Write-Host "      ⚠️  GPU no visible en WSL2. Asegúrate de tener drivers NVIDIA ≥522.x" -ForegroundColor Red
        Write-Host "      Descarga desde: https://developer.nvidia.com/cuda/wsl" -ForegroundColor Yellow
    } else {
        Write-Host "      ✓ GPU detectada: $gpuTest" -ForegroundColor Green
    }
} catch {
    Write-Host "      ⚠️  No se pudo verificar GPU: $_" -ForegroundColor Yellow
}

# ─────────────────────────────────────────────
# PASO 3: Script de setup dentro de WSL2
# ─────────────────────────────────────────────
Write-Host "[3/5] Preparando script de instalación Conda dentro de WSL2..." -ForegroundColor Yellow

$wslSetupScript = @'
#!/bin/bash
set -e

echo ""
echo "==> Actualizando sistema..."
sudo apt-get update -qq
sudo apt-get install -y wget curl git build-essential cmake libxml2-dev libxslt-dev 2>/dev/null

echo ""
echo "==> Instalando AutoDock Vina..."
VINA_VERSION="1.2.5"
wget -q "https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v${VINA_VERSION}/vina_${VINA_VERSION}_linux_x86_64" -O /tmp/vina
chmod +x /tmp/vina
sudo mv /tmp/vina /usr/local/bin/vina
echo "    AutoDock Vina $(vina --version 2>&1 | head -1)"

echo ""
echo "==> Instalando Miniconda..."
if [ ! -f "$HOME/miniconda3/bin/conda" ]; then
    wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh
    bash /tmp/miniconda.sh -b -p $HOME/miniconda3
    rm /tmp/miniconda.sh
fi
export PATH="$HOME/miniconda3/bin:$PATH"
conda init bash
source ~/.bashrc 2>/dev/null || true

echo ""
echo "==> Creando environment drugagent (python 3.11)..."
conda create -n drugagent python=3.11 -y 2>/dev/null || echo "Environment ya existe"

echo ""
echo "==> Instalando RDKit y herramientas científicas..."
conda run -n drugagent conda install -c conda-forge rdkit datamol -y

echo ""
echo "==> Instalando PyTorch con CUDA 12.1..."
conda run -n drugagent pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo ""
echo "==> Instalando LangGraph, LangChain, Groq..."
conda run -n drugagent pip install \
    langgraph>=0.3.0 \
    langchain>=0.3.0 \
    langchain-community \
    langchain-groq \
    groq

echo ""
echo "==> Instalando memoria y tracking..."
conda run -n drugagent pip install chromadb mlflow sqlalchemy

echo ""
echo "==> Instalando herramientas adicionales..."
conda run -n drugagent pip install \
    deepchem \
    streamlit \
    matplotlib \
    seaborn \
    pandas \
    numpy \
    scipy \
    pyyaml \
    python-dotenv \
    requests \
    Pillow \
    reportlab \
    meeko \
    biopython

echo ""
echo "==> Clonando SciAgent-Skills..."
if [ ! -d "$HOME/SciAgent-Skills" ]; then
    git clone https://github.com/jaechang-hits/SciAgent-Skills.git $HOME/SciAgent-Skills
fi

echo ""
echo "==> Instalando OpenMM con CUDA..."
conda run -n drugagent conda install -c conda-forge openmm -y

echo ""
echo "==> Clonando REINVENT4..."
if [ ! -d "$HOME/REINVENT4" ]; then
    git clone https://github.com/MolecularAI/REINVENT4.git $HOME/REINVENT4
    conda run -n drugagent pip install -e $HOME/REINVENT4
fi

echo ""
echo "✓ ============================================"
echo "✓ Instalación completa. Ejecutando tests..."
echo "✓ ============================================"

echo ""
echo "--- Test 1: RDKit ---"
conda run -n drugagent python -c "
from rdkit import Chem
from rdkit.Chem import Descriptors
mol = Chem.MolFromSmiles('CCO')
mw = Descriptors.MolWt(mol)
print(f'RDKit OK. MW de etanol: {mw:.2f}')
"

echo ""
echo "--- Test 2: GPU PyTorch ---"
conda run -n drugagent python -c "
import torch
print(f'CUDA disponible: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    print(f'VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB')
"

echo ""
echo "--- Test 3: AutoDock Vina ---"
vina --version

echo ""
echo "✅ Setup completo! Próximo paso: configurar GROQ_API_KEY en .env"
'@

# Guardar script en el proyecto (accesible desde WSL2)
$setupWslPath = Join-Path $PSScriptRoot "setup_wsl.sh"
$wslSetupScript | Out-File -FilePath $setupWslPath -Encoding UTF8

# Convertir a formato Unix
(Get-Content $setupWslPath -Raw) -replace "`r`n", "`n" | Set-Content $setupWslPath -NoNewline -Encoding UTF8

Write-Host "      ✓ Script de setup WSL2 guardado" -ForegroundColor Green

# ─────────────────────────────────────────────
# PASO 4: Ejecutar setup en WSL2
# ─────────────────────────────────────────────
if (-not $SkipDeps) {
    Write-Host "[4/5] Ejecutando instalación en WSL2 (esto tardará 15-30 min)..." -ForegroundColor Yellow
    
    # Convertir ruta Windows a WSL2 dinámicamente
    $absScriptPath = [System.IO.Path]::GetFullPath($setupWslPath)
    $wslPath = $absScriptPath.Replace('\', '/')
    if ($wslPath -match "^([A-Za-z]):/") {
        $drive = $Matches[1].ToLower()
        $wslPath = $wslPath -replace "^[A-Za-z]:/", "/mnt/$drive/"
    }
    
    wsl -d Ubuntu-22.04 -- bash -c "chmod +x '$wslPath' && bash '$wslPath'"
    
    Write-Host "      ✓ Dependencias instaladas en WSL2" -ForegroundColor Green
} else {
    Write-Host "[4/5] Dependencias: Omitido" -ForegroundColor Green
}

# ─────────────────────────────────────────────
# PASO 5: Crear .env
# ─────────────────────────────────────────────
Write-Host "[5/5] Configurando variables de entorno..." -ForegroundColor Yellow

$envPath = Join-Path $PSScriptRoot "..\.env"
if (-not (Test-Path $envPath)) {
    @"
# DrugAgent Environment Variables
# Consigue tu API key GRATIS en: https://console.groq.com

GROQ_API_KEY=gsk_REEMPLAZA_CON_TU_KEY_REAL

# Opcional: Claude para reportes finales
# ANTHROPIC_API_KEY=

# Paths (WSL2)
VINA_PATH=/usr/local/bin/vina
REINVENT4_PATH=/root/REINVENT4
SCIAGENT_SKILLS_PATH=/root/SciAgent-Skills

# Configuración
LOG_LEVEL=INFO
MLFLOW_TRACKING_URI=sqlite:///./data/mlflow.db
"@ | Out-File -FilePath $envPath -Encoding UTF8
    Write-Host "      ✓ .env creado. IMPORTANTE: Agrega tu GROQ_API_KEY" -ForegroundColor Green
} else {
    Write-Host "      ✓ .env ya existe" -ForegroundColor Green
}

Write-Host "
╔══════════════════════════════════════════════════════════╗
║                 ✅ SETUP COMPLETADO                       ║
╠══════════════════════════════════════════════════════════╣
║  Próximos pasos:                                         ║
║  1. Edita DrugAgent\.env con tu GROQ_API_KEY             ║
║     → Obtén una en: https://console.groq.com (GRATIS)   ║
║  2. Abre WSL2: wsl -d Ubuntu-22.04                      ║
║  3. Activa env: conda activate drugagent                 ║
║  4. Ve al proyecto y corre: python scripts/test_all.py  ║
╚══════════════════════════════════════════════════════════╝
" -ForegroundColor Cyan
