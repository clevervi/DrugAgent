#!/usr/bin/env python3
"""Debug: ver el output exacto de Vina para ajustar el parser."""
import sys, io, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

from pathlib import Path

VINA_EXE     = Path("tools/vina/vina.exe")
receptor     = Path("data/receptors/4HJO.pdbqt")
lig_dir      = Path("data/dock_tmp/test_ligs")

# Tomar el primer ligando disponible
ligs = list(lig_dir.glob("*.pdbqt"))
if not ligs:
    print("No hay ligandos preparados")
    sys.exit(1)

lig = ligs[0]
out = lig.with_name(lig.stem + "_debug_out.pdbqt")

cmd = [
    str(VINA_EXE),
    "--receptor", str(receptor),
    "--ligand", str(lig),
    "--center_x", "-43.18",
    "--center_y", "-2.45",
    "--center_z", "38.23",
    "--size_x", "22.0",
    "--size_y", "22.0",
    "--size_z", "22.0",
    "--exhaustiveness", "4",
    "--num_modes", "3",
    "--out", str(out),
]

print("CMD:", " ".join(cmd))
print("\n--- STDOUT ---")
result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
print(repr(result.stdout))
print("\n--- STDERR ---")
print(repr(result.stderr))
print("\n--- RETURN CODE:", result.returncode)

if out.exists():
    print("\n--- OUT PDBQT (primeras líneas) ---")
    for line in out.read_text().split('\n')[:20]:
        print(repr(line))
