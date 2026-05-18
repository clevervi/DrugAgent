# Skill: Muestreo de scaffolds para el generator

Firma requerida por DrugAgent: `(batch_size, scaffolds) -> list[str]` (SMILES).

```python
import random
from rdkit import Chem


def diversity_enhancer_v4(batch_size, scaffolds):
    if not scaffolds:
        return []
    random.seed(42)
    out = []
    seen = set()
    attempts = 0
    max_attempts = max(batch_size * 20, 50)
    while len(out) < batch_size and attempts < max_attempts:
        attempts += 1
        s = random.choice(scaffolds)
        mol = Chem.MolFromSmiles(s)
        if not mol:
            continue
        smi = Chem.MolToSmiles(mol)
        if smi in seen:
            continue
        seen.add(smi)
        out.append(smi)
    # Llenar el resto permitiendo duplicados si no hay suficientes únicos
    idx = 0
    while len(out) < batch_size and scaffolds and idx < batch_size * 2:
        s = scaffolds[idx % len(scaffolds)]
        idx += 1
        mol = Chem.MolFromSmiles(s)
        if mol:
            smi = Chem.MolToSmiles(mol)
            out.append(smi)
    return out[:batch_size]
```
