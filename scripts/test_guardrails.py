#!/usr/bin/env python3
"""
DrugAgent-Local - Test de Guardrails de Bioseguridad Estructural
Verifica que el validador molecular permita compuestos legítimos y bloquee
sustancias químicas peligrosas o reguladas.
"""
import sys
import os

# Asegurar que el directorio raíz está en el path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.guardrails import validate_molecular_safety

def run_tests():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    print("🧪 Iniciando Suite de Pruebas: Guardrails de Bioseguridad Estructural\n")
    
    # 1. Compuestos Farmacéuticos Permitidos (Legítimos)
    safe_compounds = {
        "Aspirina": "CC(=O)Oc1ccccc1C(=O)O",
        "Gefitinib (Oncológico EGFR)": "COc1cc2ncnc(Nc3ccc(F)cc3Cl)c2cc1OC3CCN(C)CC3",
        "Paracetamol": "CC(=O)Nc1ccc(O)cc1",
        "Sitagliptina (Diabetes)": "C1CN(C(=O)C(C1)N)C2CC(C(C2)F)(F)F"
    }
    
    # 2. Compuestos Peligrosos/Regulados Prohibidos (Deberían ser bloqueados)
    dangerous_compounds = {
        "Fentanilo (Opioide Sintético)": "CCC(=O)N(c1ccccc1)C2CCN(CCc3ccccc3)CC2",
        "Gas Mostaza (Agente Químico)": "ClCCSCCCl",
        "Gas Sarín (Neurotoxina de Fósforo)": "CC(C)OP(=O)(C)F",
        "Heroína (Sustancia Controlada)": "CC(=O)Oc1ccc2c3c1Oc4c5c(ccc43)C(CC6C5CC2N6C)OC(=O)C"
    }
    
    all_passed = True
    
    print("--- 🟢 EVALUANDO COMPUESTOS PERMITIDOS ---")
    for name, smiles in safe_compounds.items():
        is_safe, reason = validate_molecular_safety(smiles)
        if is_safe:
            print(f"✅ [APROBADO] {name} es permitido correctamente.")
        else:
            print(f"❌ [FALLO] {name} fue rechazado injustificadamente. Razón: {reason}")
            all_passed = False
            
    print("\n--- 🔴 EVALUANDO COMPUESTOS PROHIBIDOS ---")
    for name, smiles in dangerous_compounds.items():
        is_safe, reason = validate_molecular_safety(smiles)
        if not is_safe:
            print(f"✅ [BLOQUEADO] {name} bloqueado con éxito. Razón: {reason}")
        else:
            print(f"❌ [FALLO] {name} superó los guardrails de bioseguridad.")
            all_passed = False
            
    print("\n-------------------------------------------")
    if all_passed:
        print("🎉 ¡TODOS LOS TESTS DE BIOPROTECCIÓN PASARON EXITOSAMENTE! 🎉")
        sys.exit(0)
    else:
        print("🚨 SE DETECTARON FALLOS EN LA SEGURIDAD DE LOS GUARDRAILS. REVISE EL CÓDIGO.")
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
