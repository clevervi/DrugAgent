"""
Utilidades de Base de Datos Vectorial (ChromaDB) para el bucle RAG de DrugAgent.
"""
import os
import uuid
import hashlib
from pathlib import Path
import chromadb

CHROMA_DB_PATH = Path("./data/chroma")
CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)

_client = None

def get_chroma_client():
    """Retorna una instancia singleton persistente de ChromaDB."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    return _client

def save_insight_to_memory(target: str, iteration: int, insight: str):
    """
    Persiste un insight científico del reflector en ChromaDB.
    """
    if not insight or not isinstance(insight, str) or len(insight.strip()) < 10:
        return
        
    try:
        client = get_chroma_client()
        # Colección específica para insights del reflector
        collection = client.get_or_create_collection("drug_insights")
        
        insight_id = f"insight_{target}_{iteration}_{str(uuid.uuid4())[:6]}"
        
        collection.upsert(
            documents=[insight],
            metadatas=[{
                "target": target,
                "iteration": iteration,
                "type": "scientific_reflection"
            }],
            ids=[insight_id]
        )
        print(f"   🧠 ChromaDB: Guardado insight en memoria vectorial para {target}: '{insight[:60]}...'")
    except Exception as e:
        print(f"   ⚠️ Error guardando insight en ChromaDB: {e}")

def query_memory_context(target: str, query_text: str, n_results: int = 3) -> str:
    """
    Busca insights científicos históricos para guiar la generación de moléculas.
    """
    try:
        client = get_chroma_client()
        collection = client.get_or_create_collection("drug_insights")
        
        if collection.count() == 0:
            return ""
            
        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where={"target": target}
        )
        
        if not results or 'documents' not in results or not results['documents'] or not results['documents'][0]:
            # Fallback a consulta general sin filtro de target si es una búsqueda amplia
            results = collection.query(
                query_texts=[query_text],
                n_results=n_results
            )
            
        if not results or 'documents' not in results or not results['documents'] or not results['documents'][0]:
            return ""
            
        context_parts = []
        for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
            iter_meta = meta.get("iteration", 0)
            target_meta = meta.get("target", target)
            context_parts.append(f"- [Target: {target_meta} | Iteración {iter_meta}]: {doc}")
            
        return "\n".join(context_parts)
    except Exception as e:
        print(f"   ⚠️ Error consultando ChromaDB: {e}")
        return ""
