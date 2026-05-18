# Informe de evidencia pública — DrugAgent

- **Fecha:** 2026-05-18T01:54:54
- **Run ID:** manual_EGFR
- **Target:** EGFR | **PDB:** 4HJO
- **Área / indicación:**  — 
- **ChEMBL target ID:** CHEMBL3608
- **Actividades de referencia descargadas:** 50 (tipos: IC50, Ki, EC50, Kd, Potency)

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

- CHEMBL52765: IC50 = 40.0 nM (pChEMBL 7.40); SMILES `Nc1ccc2ncnc(Nc3cccc(Br)c3)c2c1`
- CHEMBL66031: IC50 = 46.0 nM (pChEMBL 7.34); SMILES `Brc1cccc(Nc2ncnc3cc4[nH]cnc4cc23)c1`
- CHEMBL137617: IC50 = 70.0 nM (pChEMBL 7.16); SMILES `C/N=N/Nc1ccc2ncnc(Nc3cccc(Br)c3)c2c1`
- CHEMBL152448: IC50 = 110.0 nM (pChEMBL 6.96); SMILES `CN(CO)/N=N/c1ccc2ncnc(Nc3cccc(Br)c3)c2c1`
- CHEMBL152922: IC50 = 130.0 nM (pChEMBL 6.89); SMILES `CC(=O)OCN(C)/N=N/c1ccc2ncnc(Nc3cccc(Br)c3)c2c1`
- CHEMBL137189: IC50 = 200.0 nM (pChEMBL 6.70); SMILES `C/N=N/Nc1ccc2ncnc(Nc3cccc(C)c3)c2c1`
- CHEMBL153577: IC50 = 578.0 nM (pChEMBL 6.24); SMILES `CC(=O)N(C)/N=N/c1ccc2ncnc(Nc3cccc(C)c3)c2c1`
- CHEMBL341946: IC50 = 1000.0 nM (pChEMBL 6.00); SMILES `O=C(NCCCc1ccccc1)c1cc(NCc2cc(O)ccc2O)ccc1O`
- CHEMBL7819: IC50 = 2830.0 nM (pChEMBL 5.55); SMILES `COc1cc(O)c2c(=O)c(-c3cccc(Cl)c3)cn(C)c2c1`
- CHEMBL142135: IC50 = 4000.0 nM (pChEMBL 5.40); SMILES `O=C(NC1CCc2ccccc2C1)c1cc(NCc2cc(O)ccc2O)ccc1O`
- CHEMBL44918: IC50 = 4000.0 nM (pChEMBL 5.40); SMILES `O=C(NCCc1ccc(F)cc1)c1cc(NCc2cc(O)ccc2O)ccc1O`
- CHEMBL7810: IC50 = 4930.0 nM (pChEMBL 5.31); SMILES `COc1cc(O)c2c(=O)c(-c3cccc(Cl)c3)cn(CCc3ccccc3)c2c1`
- CHEMBL140774: IC50 = 8000.0 nM (pChEMBL 5.10); SMILES `O=C(NCc1ccccc1)c1cc(NCc2cc(O)ccc2O)ccc1O`
- CHEMBL7866: IC50 = 9550.0 nM (pChEMBL 5.02); SMILES `COC(=O)Cn1cc(-c2cccc(Cl)c2)c(=O)c2c(O)cc(OC)cc21`
- CHEMBL137924: IC50 = 10000.0 nM (pChEMBL 5.00); SMILES `O=C(NCCc1ccccc1)c1cc(NCc2cc(O)ccc2O)ccc1O`