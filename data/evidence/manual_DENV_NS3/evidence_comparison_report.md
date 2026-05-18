# Informe de evidencia pública — DrugAgent

- **Fecha:** 2026-05-18T02:02:49
- **Run ID:** manual_DENV_NS3
- **Target:** DENV_NS3 | **PDB:** 2M9P
- **Área / indicación:**  — 
- **ChEMBL target ID:** CHEMBL4296313
- **Actividades de referencia descargadas:** 45 (tipos: IC50, Ki, EC50, Kd, Potency)

## Fuentes
- [ChEMBL](https://www.ebi.ac.uk/chembl/) — actividades bioquímicas curadas
- [RCSB PDB](https://www.rcsb.org/) — estructura del receptor
- [WHO R&D Blueprint](https://www.who.int/activities/prioritizing-diseases-for-research-and-development-in-emergency-contexts) — priorización sanitaria (contexto, no consulta automática)

## Aviso metodológico
Los scores de docking de DrugAgent (kcal/mol) **no son directamente comparables** con IC50/Ki de ChEMBL (nM/µM).
Este informe usa **similitud estructural (Tanimoto)** frente a ligandos con actividad publicada como contexto químico.

## Candidatos DrugAgent vs referencias ChEMBL

| Rank | SMILES (truncado) | Docking (kcal/mol) | QED | Tox proxy | Max Tanimoto vs ref. ChEMBL |
|------|-------------------|--------------------|-----|-----------|---------------------------|

## Interpretación (guía)
- **Tanimoto > 0.35** hacia un inhibidor conocido: química en espacio similar (revisar patentes / novedad).
- **Tanimoto < 0.25** con muchas referencias: posible scaffold más novedoso (mayor riesgo, mayor oportunidad).
- Siguiente paso experimental sugerido: ensayo enzimático o celular contra el mismo blanco, no solo más docking.

## Referencias ChEMBL (muestra, mejores pChEMBL)

- CHEMBL231813: Ki = 3.9 nM (pChEMBL 8.41); SMILES `CCC[C@H](NC(=O)[C@@H]1[C@H]2CCC[C@H]2CN1C(=O)[C@@H`
- CHEMBL4588900: EC50 = 4.6 nM (pChEMBL 8.34); SMILES `COc1ccc2c(O[C@@H]3C[C@H]4C(=O)N[C@]5(C(=O)O)CC5/C=`
- CHEMBL4588900: IC50 = 6.7 nM (pChEMBL 8.17); SMILES `COc1ccc2c(O[C@@H]3C[C@H]4C(=O)N[C@]5(C(=O)O)CC5/C=`
- CHEMBL421233: Ki = 30.0 nM (pChEMBL 7.52); SMILES `CC(=O)N[C@@H](CC(=O)O)C(=O)N[C@@H](CCC(=O)O)C(=O)N`
- CHEMBL417559: Ki = 40.0 nM (pChEMBL 7.40); SMILES `CC(=O)N[C@@H](CC(=O)O)C(=O)N[C@@H](CCC(=O)O)C(=O)N`
- CHEMBL258734: Ki = 44.8 nM (pChEMBL 7.35); SMILES `CC(C)(C)OC(=O)N[C@H]1CCCCC/C=C\[C@@H]2C[C@@]2(C(=O`
- CHEMBL3125043: Ki = 53.0 nM (pChEMBL 7.28); SMILES `C=Cc1cc([C@H](NC(=O)[C@@H](NC(=O)OC(C)(C)C)C(C)(C)`
- CHEMBL3927196: IC50 = 53.0 nM (pChEMBL 7.28); SMILES `CC(C)=CC(=O)CC[C@H](NC(=O)OC(C)(C)C)C(=O)N1CC2[C@@`
- CHEMBL3125043: Ki = 110.0 nM (pChEMBL 6.96); SMILES `C=Cc1cc([C@H](NC(=O)[C@@H](NC(=O)OC(C)(C)C)C(C)(C)`
- CHEMBL3125169: Ki = 110.0 nM (pChEMBL 6.96); SMILES `C=Cc1cc(C(NC(=O)OC(C)(C)C)C(=O)Nc2cccc(C(=O)NS(=O)`
- CHEMBL231813: IC50 = 130.0 nM (pChEMBL 6.89); SMILES `CCC[C@H](NC(=O)[C@@H]1[C@H]2CCC[C@H]2CN1C(=O)[C@@H`
- CHEMBL1170408: Ki = 140.0 nM (pChEMBL 6.85); SMILES `C=CCCCS(=O)(=O)NC(=O)[C@H](CCC)NC(=O)[C@@H](NC(=O)`
- CHEMBL3125169: Ki = 180.0 nM (pChEMBL 6.75); SMILES `C=Cc1cc(C(NC(=O)OC(C)(C)C)C(=O)Nc2cccc(C(=O)NS(=O)`
- CHEMBL297884: Ki = 200.0 nM (pChEMBL 6.70); SMILES `COc1ccc2c(O[C@@H]3C[C@H]4C(=O)N[C@]5(C(=O)O)C[C@H]`
- CHEMBL3125043: Ki = 210.0 nM (pChEMBL 6.68); SMILES `C=Cc1cc([C@H](NC(=O)[C@@H](NC(=O)OC(C)(C)C)C(C)(C)`