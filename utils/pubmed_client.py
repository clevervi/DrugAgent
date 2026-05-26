"""
PubMed E-utilities client — literatura científica gratuita para RAG.
No requiere API key (rate limit: 3 req/s sin key, 10 req/s con NCBI_API_KEY en .env).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")


def _get(url: str, timeout: float = 10.0) -> str:
    if _NCBI_API_KEY:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}api_key={_NCBI_API_KEY}"
    req = Request(url, headers={"User-Agent": "DrugAgent-Local/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _cache_path(cache_dir: Path, key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)[:100]
    return cache_dir / f"pubmed_{safe}.txt"


def search_pubmed(query: str, max_results: int = 8, cache_dir: Optional[Path] = None) -> List[str]:
    """Retorna lista de PMIDs para la query."""
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cp = _cache_path(cache_dir, f"ids_{query}_{max_results}")
        if cp.exists() and (time.time() - cp.stat().st_mtime) < 86400 * 3:
            return cp.read_text().splitlines()
    try:
        url = f"{EUTILS_BASE}/esearch.fcgi?db=pubmed&term={quote(query)}&retmax={max_results}&retmode=json"
        data = json.loads(_get(url))
        ids = data.get("esearchresult", {}).get("idlist", [])
        if cache_dir and ids:
            _cache_path(cache_dir, f"ids_{query}_{max_results}").write_text("\n".join(ids))
        return ids
    except Exception as e:
        print(f"   [PubMed] esearch failed: {e}")
        return []


def fetch_abstracts(pmids: List[str], cache_dir: Optional[Path] = None) -> str:
    """Retorna texto plano con títulos + abstracts de los PMIDs dados."""
    if not pmids:
        return ""
    key = "abs_" + "_".join(pmids[:8])
    if cache_dir:
        cp = _cache_path(cache_dir, key)
        if cp.exists() and (time.time() - cp.stat().st_mtime) < 86400 * 7:
            return cp.read_text(encoding="utf-8")
    try:
        ids_str = ",".join(pmids[:8])
        url = f"{EUTILS_BASE}/efetch.fcgi?db=pubmed&id={ids_str}&rettype=abstract&retmode=text"
        text = _get(url)
        if cache_dir:
            _cache_path(cache_dir, key).write_text(text, encoding="utf-8")
        return text
    except Exception as e:
        print(f"   [PubMed] efetch failed: {e}")
        return ""


def get_target_literature(
    target_name: str,
    max_results: int = 5,
    cache_dir: Optional[Path] = None,
) -> str:
    """
    Obtiene literatura reciente sobre el target para enriquecer el contexto del reflector.
    Búsqueda: '<target> inhibitor drug discovery small molecule'.
    Retorna hasta 5 abstracts concatenados, truncados a 3000 chars.
    """
    if cache_dir is None:
        cache_dir = Path("data/evidence/pubmed_cache")

    query = f"{target_name} inhibitor drug discovery small molecule"
    pmids = search_pubmed(query, max_results=max_results, cache_dir=cache_dir)
    if not pmids:
        return ""

    abstracts = fetch_abstracts(pmids, cache_dir=cache_dir)
    if not abstracts:
        return ""

    # Truncar para no saturar el contexto del LLM
    truncated = abstracts[:3000]
    if len(abstracts) > 3000:
        truncated += "\n[...truncado]"

    return f"=== LITERATURA PUBMED ({target_name}) ===\n{truncated}\n"
