"""
ML ADMET Predictor
Provee una interfaz estandarizada para evaluar propiedades de absorción,
distribución, metabolismo, excreción y toxicidad usando modelos ML/Deep Learning.
Contiene un modelo Random Forest local entrenado dinámicamente con descriptores 
físico-químicos y huellas moleculares de Morgan (ECFP4).
"""
import numpy as np
import os
import pickle
from pathlib import Path
from rdkit import Chem
from rdkit.Chem import Descriptors, AllChem, rdFingerprintGenerator
from utils.scoring import deterministic_noise

# Intentar cargar scikit-learn
try:
    from sklearn.ensemble import RandomForestRegressor
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

# Intentar cargar joblib
try:
    import joblib
    HAS_JOBLIB = True
except ImportError:
    HAS_JOBLIB = False

# Configuración de rutas
MODELS_DIR = Path("data/models")
TOX_MODEL_PATH = MODELS_DIR / "admet_toxicity_rf.pkl"
ABS_MODEL_PATH = MODELS_DIR / "admet_absorption_rf.pkl"

# Conjunto de datos de referencia (SMILES, toxicidad [0-1], absorción intestinal [0-1])
REFERENCE_DATA = [
    # Medicamentos comunes (Baja toxicidad, buena absorción)
    ("CC(=O)Oc1ccccc1C(=O)O", 0.05, 0.98), # Aspirin
    ("CC(=O)Nc1ccc(O)cc1", 0.08, 0.90),    # Paracetamol
    ("CN1C=NC2=C1C(=O)N(C)C(=O)N2C", 0.12, 0.99), # Caffeine
    ("CC(C)cc1ccc(cc1)C(C)C(=O)O", 0.06, 0.95),  # Ibuprofen
    ("CN1CCC23C4c5ccc(O)cc5OC2C(O)C=CC3C1CC4", 0.35, 0.40), # Morphine
    ("COc1cc2ncnc(Nc3ccc(F)cc3Cl)c2cc1OC3CCN(C)CC3", 0.20, 0.85), # Gefitinib
    ("C1CN(C(=O)C(C1)N)C2CC(C(C2)F)(F)F", 0.08, 0.92), # Sitagliptin
    
    # Moléculas tóxicas o precursores peligrosos (Alta toxicidad)
    ("CCC(=O)N(c1ccccc1)C2CCN(CCc3ccccc3)CC2", 0.95, 0.95), # Fentanyl
    ("CN1C2CCC1C(C(C2)OC(=O)c3ccccc3)C(=O)OC", 0.85, 0.90), # Cocaine
    ("ClCCSCCCl", 0.99, 0.15), # Mustard gas
    ("CC(C)OP(=O)(C)F", 1.00, 0.05), # Sarin
    ("O=P(F)(C1CCCC1)C2CCCC2", 0.90, 0.20), # G-series agent derivative
    ("C1(=CC=CC=C1)O", 0.45, 0.85), # Phenol
    ("C1(=CC=CC=C1)N", 0.55, 0.88), # Aniline
    
    # Fragmentos simples / Solventes
    ("c1ccccc1", 0.30, 0.92), # Benzene
    ("CCO", 0.05, 0.99), # Ethanol
    ("CO", 0.40, 0.99), # Methanol
    ("CS", 0.25, 0.85), # Methanethiol
    ("CCCC", 0.03, 0.95), # Butane
    ("C1CCCCC1", 0.05, 0.98), # Cyclohexane
    ("CCN(CC)CC", 0.12, 0.92), # Triethylamine
    ("c1ccc(cc1)C(=O)O", 0.07, 0.95), # Benzoic acid
    ("NCC(=O)O", 0.01, 0.99), # Glycine
    ("C1CCNCC1", 0.08, 0.95), # Piperidine
    ("C1CCOCC1", 0.04, 0.98), # Tetrahydrofuran
]

class MLADMETPredictor:
    def __init__(self, use_ml_models: bool = True):
        """
        Inicializa los modelos ML.
        :param use_ml_models: Si es True, entrena/carga el modelo Random Forest.
                              Si es False o sklearn no está disponible, cae de forma segura a la heurística básica.
        """
        self.use_ml_models = use_ml_models and HAS_SKLEARN
        self.tox_model = None
        self.abs_model = None
        
        if self.use_ml_models:
            if self._load_models():
                # Modelos ya cargados con éxito
                pass
            else:
                print("[ADMET] Entrenando localmente modelos Random Forest de toxicidad y absorcion...")
                self._train_models()
                self._save_models()
        else:
            if not HAS_SKLEARN:
                print("[ADMET] ADVERTENCIA: scikit-learn no esta disponible. Usando Proxy Heuristico.")
            else:
                print("[ADMET] Modo de proxy heuristico seleccionado.")

    def _extract_features(self, smiles: str):
        """
        Extrae descriptores fisicoquímicos y huellas moleculares de Morgan (ECFP4)
        para generar la representación de entrada para el modelo ML.
        """
        try:
            mol = Chem.MolFromSmiles(smiles)
            if not mol:
                return None
            
            # Descriptores Físico-Químicos
            mw = Descriptors.MolWt(mol)
            logp = Descriptors.MolLogP(mol)
            tpsa = Descriptors.TPSA(mol)
            hbd = Descriptors.NumHDonors(mol)
            hba = Descriptors.NumHAcceptors(mol)
            rotb = Descriptors.NumRotatableBonds(mol)
            
            # Fingerprint Morgan de 128 bits, radio 2 (ECFP4)
            fp_gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=128)
            fp = fp_gen.GetFingerprint(mol)
            fp_bits = list(fp)
            
            # Combinación de features
            features = [mw, logp, tpsa, hbd, hba, rotb] + fp_bits
            return features
        except Exception as e:
            print(f"Error extrayendo descriptores para {smiles}: {e}")
            return None

    def _train_models(self):
        """
        Entrena dinámicamente los regresores Random Forest en base al dataset de referencia.
        """
        try:
            X = []
            y_tox = []
            y_abs = []
            
            for smiles, tox, absorp in REFERENCE_DATA:
                feat = self._extract_features(smiles)
                if feat is not None:
                    X.append(feat)
                    y_tox.append(tox)
                    y_abs.append(absorp)
            
            X = np.array(X)
            y_tox = np.array(y_tox)
            y_abs = np.array(y_abs)
            
            # Modelo de toxicidad
            self.tox_model = RandomForestRegressor(n_estimators=50, random_state=42)
            self.tox_model.fit(X, y_tox)
            
            # Modelo de absorción
            self.abs_model = RandomForestRegressor(n_estimators=50, random_state=42)
            self.abs_model.fit(X, y_abs)
            
            print(f"[ADMET] Modelos de Machine Learning entrenados con exito ({len(X)} compuestos de referencia).")
        except Exception as e:
            print(f"[ADMET] Error al entrenar modelos ML: {e}. Desactivando modelos ML.")
            self.use_ml_models = False

    def _save_models(self):
        """Guarda los modelos entrenados en disco."""
        try:
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            if HAS_JOBLIB:
                joblib.dump(self.tox_model, TOX_MODEL_PATH)
                joblib.dump(self.abs_model, ABS_MODEL_PATH)
            else:
                with open(TOX_MODEL_PATH, "wb") as f:
                    pickle.dump(self.tox_model, f)
                with open(ABS_MODEL_PATH, "wb") as f:
                    pickle.dump(self.abs_model, f)
            print("   [ADMET] Modelos guardados exitosamente en disco (data/models/).")
        except Exception as e:
            print(f"   [ADMET] Error guardando modelos en disco: {e}")

    def _load_models(self) -> bool:
        """Intenta cargar los modelos desde disco."""
        try:
            if TOX_MODEL_PATH.exists() and ABS_MODEL_PATH.exists():
                if HAS_JOBLIB:
                    self.tox_model = joblib.load(TOX_MODEL_PATH)
                    self.abs_model = joblib.load(ABS_MODEL_PATH)
                else:
                    with open(TOX_MODEL_PATH, "rb") as f:
                        self.tox_model = pickle.load(f)
                    with open(ABS_MODEL_PATH, "rb") as f:
                        self.abs_model = pickle.load(f)
                print("   [ADMET] Modelos Random Forest cargados con exito desde disco.")
                return self.tox_model is not None and self.abs_model is not None
            return False
        except Exception as e:
            print(f"   [ADMET] Error al cargar los modelos de disco: {e}. Se procedera a re-entrenar.")
            return False

    def predict_toxicity(self, smiles: str) -> float:
        """
        Predice la probabilidad de toxicidad clínica [0.0 - 1.0].
        """
        if self.use_ml_models and self.tox_model:
            feat = self._extract_features(smiles)
            if feat is not None:
                pred = self.tox_model.predict([feat])[0]
                return float(np.clip(pred, 0.0, 1.0))
            
        # PROXY MODE / FALLBACK: basado en la complejidad molecular y heurísticas
        mol = Chem.MolFromSmiles(smiles)
        if not mol: return 1.0
        
        weight = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        
        # Penaliza alto peso y alta lipofilia
        base_tox = (weight / 1000.0) + (logp / 10.0)
        return min(max(base_tox + deterministic_noise(smiles, scale=0.1), 0.0), 1.0)
        
    def predict_absorption(self, smiles: str) -> float:
        """
        Predice la absorción intestinal (HIA) [0.0 - 1.0].
        """
        if self.use_ml_models and self.abs_model:
            feat = self._extract_features(smiles)
            if feat is not None:
                pred = self.abs_model.predict([feat])[0]
                return float(np.clip(pred, 0.0, 1.0))
            
        mol = Chem.MolFromSmiles(smiles)
        if not mol: return 0.0
        
        tpsa = Descriptors.TPSA(mol)
        # Menor TPSA suele tener mejor absorción, pico en ~60-90
        abs_score = 1.0 - (abs(tpsa - 75.0) / 100.0)
        return min(max(abs_score + deterministic_noise(smiles, scale=0.1), 0.0), 1.0)
