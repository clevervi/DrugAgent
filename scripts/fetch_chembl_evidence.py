#!/usr/bin/env python3
"""
Descarga evidencia ChEMBL para un target y (opcional) compara con candidatos de una corrida Prisma.

Uso:
  python scripts/fetch_chembl_evidence.py --target EGFR --pdb 4HJO
  python scripts/fetch_chembl_evidence.py --target MPRO --run-id <uuid-de-prisma>
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(".env")


def main():
    parser = argparse.ArgumentParser(description="ChEMBL evidence pack for DrugAgent")
    parser.add_argument("--target", required=True, help="target_name (ej. EGFR, MPRO)")
    parser.add_argument("--pdb", default="4HJO", help="PDB ID")
    parser.add_argument("--run-id", default=None, help="Prisma run UUID para cargar top candidatos")
    parser.add_argument("--area", default="", help="therapeutic_area")
    parser.add_argument("--indication", default="", help="indication_label")
    args = parser.parse_args()

    top_candidates = []
    run_id = args.run_id or f"manual_{args.target}"

    if args.run_id:
        from orchestrator.db import db, init_db, close_db
        init_db()
        run = db.run.find_unique(where={"id": args.run_id}, include={"candidates": True})
        if not run:
            print(f"No existe run {args.run_id}")
            sys.exit(1)
        top_candidates = [
            {
                "smiles": c.smiles,
                "docking_score": c.docking_score,
                "qed": c.qed,
                "admet_toxicity": c.admet_toxicity,
            }
            for c in (run.candidates or [])
        ]
        run_id = run.id
        close_db()

    from utils.evidence_report import generate_evidence_pack

    result = generate_evidence_pack(
        target_name=args.target,
        target_pdb_id=args.pdb,
        top_candidates=top_candidates,
        run_id=run_id,
        therapeutic_area=args.area,
        indication_label=args.indication,
    )
    print(result)
    if result.get("skipped") and not result.get("success"):
        sys.exit(2)


if __name__ == "__main__":
    main()
