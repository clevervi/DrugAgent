import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fpdf import FPDF, XPos, YPos
from rdkit import Chem
from rdkit.Chem import Draw


def _chunk_line_for_pdf(text: str, max_len: int = 92) -> List[str]:
    """Evita líneas sin espacios (tablas/SMILES) que rompen fpdf multi_cell."""
    text = _sanitize_pdf_text(text or "")
    if not text:
        return []
    if len(text) <= max_len:
        return [text]
    chunks: List[str] = []
    while text:
        chunks.append(text[:max_len])
        text = text[max_len:]
    return chunks


def _sanitize_pdf_text(text: str) -> str:
    """fpdf core fonts: reemplazar caracteres fuera de latin-1."""
    if not text:
        return ""
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2026": "...",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00b0": " deg",
        "\u03bc": "u",
        "\u00b1": "+/-",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _load_latest_run_from_db(run_id: Optional[str] = None) -> Tuple[Optional[Any], List[dict]]:
    try:
        from prisma import Prisma

        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.abspath(os.path.join(script_dir, "..", "data", "drugagent.db"))
        if not os.path.exists(db_path):
            return None, []
        os.environ["DATABASE_URL"] = f"file:{db_path}"
        db = Prisma()
        db.connect()
        if run_id:
            latest_run = db.run.find_unique(where={"id": run_id}, include={"candidates": True})
        else:
            latest_run = db.run.find_first(
                order={"start_time": "desc"},
                include={"candidates": True},
            )
        data: List[dict] = []
        if latest_run and latest_run.candidates:
            data = [c.model_dump() for c in latest_run.candidates]
        db.disconnect()
        return latest_run, data
    except Exception as e:
        print(f"Advertencia: No se pudo conectar/leer de Prisma DB ({e}).")
        return None, []


def _evidence_paths_for_run(run_id: str) -> Tuple[Optional[Path], Optional[Path]]:
    base = Path("data/evidence") / str(run_id)
    md_path = base / "evidence_comparison_report.md"
    meta_path = base / "evidence_meta.json"
    return (md_path if md_path.is_file() else None, meta_path if meta_path.is_file() else None)


def _markdown_excerpt_for_pdf(md_text: str, max_lines: int = 28) -> List[str]:
    lines_out: List[str] = []
    for raw in md_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## Referencias ChEMBL"):
            break
        if re.match(r"^\|[-:\s|]+\|$", line):
            continue
        line = line.replace("**", "").replace("`", "")
        if line.startswith("#"):
            line = line.lstrip("# ").strip()
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            line = "  |  ".join(c for c in cells if c)
        lines_out.append(_sanitize_pdf_text(line))
        if len(lines_out) >= max_lines:
            lines_out.append("...")
            break
    return lines_out


def _load_evidence_excerpt(run_id: Optional[str]) -> Tuple[List[str], Dict[str, Any]]:
    if not run_id:
        return [], {}
    md_path, meta_path = _evidence_paths_for_run(run_id)
    meta: Dict[str, Any] = {}
    if meta_path:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    if not md_path:
        return [], meta
    try:
        return _markdown_excerpt_for_pdf(md_path.read_text(encoding="utf-8")), meta
    except Exception:
        return [], meta

class PDFReport(FPDF):
    def header(self):
        # Dibujar una franja superior azul corporativa elegante
        self.set_fill_color(30, 58, 138)  # Azul Profundo
        self.rect(0, 0, 210, 15, 'F')
        
        # Texto del Header
        self.set_xy(10, 3)
        self.set_font('helvetica', 'B', 10)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, 'DRUGAGENT - REPORTES DE DESCUBRIMIENTO MOLECULAR AUTÓNOMO', 0, align='L')
        
        # Fecha en el Header (Derecha)
        self.set_xy(150, 3)
        self.set_font('helvetica', '', 9)
        self.cell(50, 10, datetime.now().strftime('%Y-%m-%d %H:%M'), 0, align='R')
        
        self.ln(20)

    def footer(self):
        self.set_y(-20)
        # Línea de separación sutil
        self.set_draw_color(226, 232, 240)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        
        # Texto de pie de página
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 10, 'Documento Confidencial - Generado por DrugAgent (Everness Labs)', 0, align='L')
        self.set_xy(180, -15)
        self.cell(20, 10, f'Página {self.page_no()}', 0, align='R')

def generate_pdf_report(
    results_json="output/results.json",
    output_pdf="output/DrugAgent_Report.pdf",
    run_id: Optional[str] = None,
):
    latest_run, data = _load_latest_run_from_db(run_id)

    # Fallback al JSON estático secundario si no hay datos en DB
    if not data:
        if not os.path.exists(results_json):
            print(f"Error: No se encontró la base de datos ni el archivo JSON en {results_json}")
            return
        try:
            with open(results_json, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error leyendo el fallback JSON: {e}")

    if not data:
        print("No hay datos disponibles en DB ni en JSON para generar el reporte.")
        return

    # Quedarnos con el Top 10 para el reporte ordenando por docking score (más bajo/negativo)
    top_candidates = sorted(data, key=lambda x: x.get("docking_score", 0.0) or 0.0)[:10]

    effective_run_id = run_id or (latest_run.id if latest_run else None)
    target_name = (latest_run.target_name if latest_run else None) or "N/D"
    target_pdb = (latest_run.target_pdb_id if latest_run else None) or "N/D"
    therapeutic_area = (latest_run.therapeutic_area if latest_run else None) or ""
    indication_label = (latest_run.indication_label if latest_run else None) or ""
    docking_mode = (latest_run.docking_mode if latest_run else None) or ""

    evidence_lines, evidence_meta = _load_evidence_excerpt(effective_run_id)

    # Crear temp dir para imágenes
    os.makedirs("output/temp_img", exist_ok=True)

    pdf = PDFReport()
    pdf.add_page()

    # === PORTADA / SECCIÓN DE INTRODUCCIÓN ===
    pdf.set_font('helvetica', 'B', 22)
    pdf.set_text_color(30, 58, 138)  # Azul Profundo
    pdf.cell(0, 12, "REPORTE EJECUTIVO DE CRIBADO", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
    
    pdf.set_font('helvetica', '', 12)
    pdf.set_text_color(71, 85, 105)  # Gris Pizarra
    subtitle = _sanitize_pdf_text(
        f"Target: {target_name} ({target_pdb}) | Candidatos: {len(data)}"
    )
    if therapeutic_area or indication_label:
        subtitle += _sanitize_pdf_text(
            f" | {therapeutic_area or ''} {indication_label or ''}".strip()
        )
    if docking_mode:
        subtitle += f" | Docking: {docking_mode}"
    pdf.cell(0, 8, subtitle, 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
    if effective_run_id:
        pdf.set_font('helvetica', '', 9)
        pdf.cell(0, 6, _sanitize_pdf_text(f"Run ID: {effective_run_id}"), 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
    pdf.ln(5)
    
    # Línea decorativa azul
    pdf.set_draw_color(30, 58, 138)
    pdf.set_line_width(1.5)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(8)
    
    # Resumen Ejecutivo
    pdf.set_font('helvetica', 'B', 14)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, "Resumen Ejecutivo", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font('helvetica', '', 10.5)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 6, _sanitize_pdf_text(
        "Este reporte resume los mejores candidatos identificados por el pipeline DrugAgent "
        "(docking AutoDock Vina, QED, SA Score, filtros PAINS/Brenk y proxy ADMET). "
        "No sustituye ensayos experimentales ni decisiones clínicas."
    ))
    pdf.ln(6)

    if evidence_lines or evidence_meta:
        if pdf.get_y() > 240:
            pdf.add_page()
        pdf.set_x(pdf.l_margin)
        ew = pdf.epw
        pdf.set_font('helvetica', 'B', 14)
        pdf.set_text_color(30, 58, 138)
        pdf.cell(0, 8, "Evidencia publica (ChEMBL API)", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', '', 9.5)
        pdf.set_text_color(51, 65, 85)
        chembl_tid = evidence_meta.get("chembl_target_id", "")
        n_act = evidence_meta.get("n_activities", "")
        if chembl_tid:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(
                ew, 5,
                _sanitize_pdf_text(
                    f"ChEMBL target: {chembl_tid} | Actividades de referencia: {n_act}. "
                    "Docking (kcal/mol) no es comparable con IC50/Ki; se usa Tanimoto vs ligandos curados."
                ),
            )
        for line in evidence_lines:
            for chunk in _chunk_line_for_pdf(line):
                if not chunk.strip():
                    continue
                if pdf.get_y() > 265:
                    pdf.add_page()
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(ew, 4.5, chunk)
        pdf.ln(6)
    elif effective_run_id:
        pdf.set_font('helvetica', 'I', 9)
        pdf.set_text_color(100, 116, 139)
        pdf.multi_cell(
            0, 5,
            _sanitize_pdf_text(
                "Sin paquete de evidencia ChEMBL para esta corrida "
                f"(data/evidence/{effective_run_id}/). Ejecuta el pipeline con evidence.enabled=true."
            ),
        )
        pdf.ln(4)

    for i, mol_data in enumerate(top_candidates, 1):
        smiles = mol_data.get("smiles", "")
        mol_id = mol_data.get("mol_id", f"mol_{i}")
        score = mol_data.get("docking_score", 0.0)
        qed = mol_data.get("qed", 0.0)
        sa_score = mol_data.get("sa_score", 0.0)
        le = mol_data.get("ligand_efficiency", 0.0)
        tox = mol_data.get("admet_toxicity", 0.0)
        sol = mol_data.get("admet_solubility", "moderate")
        pains = mol_data.get("pains_alert", False)
        brenk = mol_data.get("brenk_alert", False)
        status = mol_data.get("status", "N/A")
        score_final = mol_data.get("score_final", 0.0)
        md_rmsd = mol_data.get("md_rmsd")
        md_refined_score = mol_data.get("md_refined_score")

        # Generar imagen de estructura molecular 2D
        img_path = f"output/temp_img/{mol_id}.png"
        mol = Chem.MolFromSmiles(smiles)
        if mol:
            Draw.MolToFile(mol, img_path, size=(300, 300))

        # Encabezado del Candidato (Banner de Tarjeta)
        pdf.set_fill_color(241, 245, 249)  # Gris muy claro (#F1F5F9)
        pdf.set_text_color(30, 58, 138)   # Azul
        pdf.set_font('helvetica', 'B', 11)
        pdf.cell(0, 8, f"  Candidato #{i}: {mol_id}   |   Score Combinado: {score_final:.4f}", 1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        pdf.ln(3)

        # Guardar posición Y de inicio de tarjeta
        start_y = pdf.get_y()

        # Columna Izquierda: Métricas y Parámetros
        pdf.set_font('helvetica', '', 9.5)
        pdf.set_text_color(51, 65, 85)

        # Fila: SMILES
        pdf.set_font('helvetica', 'B', 9)
        pdf.cell(40, 5, "SMILES:", 0)
        pdf.set_font('helvetica', '', 8)
        pdf.cell(80, 5, smiles[:55] + ("..." if len(smiles) > 55 else ""), 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Fila: Docking Score
        pdf.set_font('helvetica', 'B', 9)
        pdf.cell(40, 5, "Afinidad Docking:", 0)
        pdf.set_font('helvetica', '', 9.5)
        score_str = f"{score:.2f} kcal/mol" if isinstance(score, float) else str(score)
        pdf.cell(80, 5, score_str, 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Fila: Dinámica Molecular (MD)
        if md_rmsd is not None or md_refined_score is not None:
            pdf.set_font('helvetica', 'B', 9)
            pdf.cell(40, 5, "Estabilidad MD:", 0)
            pdf.set_font('helvetica', '', 9.5)
            rmsd_str = f"{md_rmsd:.2f} A (RMSD)" if isinstance(md_rmsd, float) else "N/A"
            ref_score_str = f"{md_refined_score:.2f} kcal/mol (Refinado)" if isinstance(md_refined_score, float) else "N/A"
            pdf.cell(80, 5, f"{rmsd_str} | {ref_score_str}", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Fila: Ligand Efficiency
        pdf.set_font('helvetica', 'B', 9)
        pdf.cell(40, 5, "Ligand Efficiency:", 0)
        pdf.set_font('helvetica', '', 9.5)
        le_str = f"{le:.4f}" if isinstance(le, float) else str(le)
        pdf.cell(80, 5, le_str, 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Fila: QED (Drug-likeness)
        pdf.set_font('helvetica', 'B', 9)
        pdf.cell(40, 5, "Drug-likeness (QED):", 0)
        pdf.set_font('helvetica', '', 9.5)
        qed_str = f"{qed:.3f}" if isinstance(qed, float) else str(qed)
        pdf.cell(80, 5, qed_str, 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Fila: SA Score
        pdf.set_font('helvetica', 'B', 9)
        pdf.cell(40, 5, "Synthesizability (SA):", 0)
        pdf.set_font('helvetica', '', 9.5)
        sa_str = f"{sa_score:.3f} (bajo = más sintetizable)" if isinstance(sa_score, float) else str(sa_score)
        pdf.cell(80, 5, sa_str, 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Fila: ADMET Sol / Tox
        pdf.set_font('helvetica', 'B', 9)
        pdf.cell(40, 5, "Perfil ADMET:", 0)
        pdf.set_font('helvetica', '', 9.5)
        pdf.cell(80, 5, f"Toxicidad: {tox:.3f} | Solubilidad: {sol}", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Fila: Alertas y Filtros
        pdf.set_font('helvetica', 'B', 9)
        pdf.cell(40, 5, "Toxicóforos Alertas:", 0)
        if pains or brenk:
            pdf.set_text_color(220, 38, 38)  # Rojo vivo para peligro
            alerts = []
            if pains: alerts.append("PAINS")
            if brenk: alerts.append("BRENK")
            pdf.set_font('helvetica', 'B', 9)
            pdf.cell(80, 5, f"ALERTA ACTIVADA: {' + '.join(alerts)}", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.set_text_color(16, 185, 129)  # Verde esmeralda para seguro
            pdf.set_font('helvetica', 'B', 9)
            pdf.cell(80, 5, "NINGUNA (Compuesto Limpio)", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_text_color(51, 65, 85)  # Restaurar gris

        # Fila: Status
        pdf.set_font('helvetica', 'B', 9)
        pdf.cell(40, 5, "Estado Pipeline:", 0)
        pdf.set_font('helvetica', 'I', 9.5)
        pdf.cell(80, 5, str(status).upper(), 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Columna Derecha: Imagen Molecular
        end_y = pdf.get_y()
        if os.path.exists(img_path):
            # Dibujar la estructura química 2D a la derecha
            pdf.image(img_path, x=140, y=start_y, w=48)
            card_height = end_y - start_y
            if card_height < 50:
                pdf.set_y(start_y + 52)
            else:
                pdf.ln(5)
        else:
            pdf.ln(5)

        # Línea divisoria elegante
        pdf.set_draw_color(226, 232, 240)
        pdf.set_line_width(0.5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(6)

        # Salto de página inteligente (cada 3 compuestos para evitar cortes feos)
        if i % 3 == 0 and i != len(top_candidates):
            pdf.add_page()

    # Limpiar imágenes temporales
    try:
        for file in os.listdir("output/temp_img"):
            os.remove(os.path.join("output/temp_img", file))
        os.rmdir("output/temp_img")
    except Exception:
        pass

    pdf.output(output_pdf)
    print(f"PDF generado exitosamente en {output_pdf}")

def generate_breakthrough_pdf(b_data: dict, output_pdf: str = None):
    """
    Genera un PDF para candidatos in silico de alta prioridad (no es informe clínico).
    """
    if not output_pdf:
        target_clean = str(b_data.get('target_name', 'TARGET')).replace(" ", "_").upper()
        output_pdf = f"output/BREAKTHROUGH_{target_clean}_{b_data.get('id', '0000')}.pdf"
        
    os.makedirs("output/temp_img", exist_ok=True)
    
    pdf = PDFReport()
    pdf.add_page()
    
    # === PORTADA DE AVANCE ===
    pdf.set_fill_color(16, 185, 129)  # Verde esmeralda (Éxito)
    pdf.rect(0, 15, 210, 12, 'F')
    
    pdf.set_xy(10, 16)
    pdf.set_font('helvetica', 'B', 16)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, "Candidato in silico de alta prioridad", 0, align='C')
    pdf.ln(12)
    
    pdf.set_font('helvetica', 'B', 20)
    pdf.set_text_color(15, 23, 42)  # Azul muy oscuro
    pdf.cell(0, 12, f"Diana Terapéutica: {b_data.get('target_name')} ({b_data.get('target_pdb_id')})", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    
    pdf.set_font('helvetica', 'I', 12)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(0, 8, f"{b_data.get('therapeutic_area')} | {b_data.get('indication_label')}", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(8)
    
    # Justificación / Explicación
    pdf.set_font('helvetica', 'B', 12)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, "Resumen computacional (requiere validacion experimental)", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font('helvetica', '', 11)
    pdf.set_text_color(51, 65, 85)
    explanation = b_data.get("explanation") or b_data.get("evidence_summary", "Explicación no disponible.")
    pdf.multi_cell(0, 6, explanation)
    pdf.ln(8)
    
    # Imagen y Detalles
    img_path = f"output/temp_img/break_{b_data.get('id', '1')}.png"
    smiles = b_data.get("smiles", "")
    mol = Chem.MolFromSmiles(smiles)
    if mol:
        Draw.MolToFile(mol, img_path, size=(400, 400))
    
    start_y = pdf.get_y()
    
    # Caja de métricas
    pdf.set_fill_color(241, 245, 249)
    pdf.set_font('helvetica', 'B', 11)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(100, 8, "Métricas Clave del Ligando", 1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
    
    metrics_y = pdf.get_y()
    pdf.set_font('helvetica', 'B', 10)
    pdf.set_text_color(51, 65, 85)
    pdf.cell(50, 6, "Docking Score:", 0)
    pdf.set_font('helvetica', '', 10)
    pdf.cell(50, 6, f"{b_data.get('docking_score')} kcal/mol", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    if b_data.get('md_refined_score') or b_data.get('md_rmsd'):
        pdf.set_font('helvetica', 'B', 10)
        pdf.cell(50, 6, "Estabilidad proxy:", 0)
        pdf.set_font('helvetica', '', 10)
        pdf.cell(50, 6, f"{b_data.get('md_refined_score', 'N/A')} kcal/mol | {b_data.get('md_rmsd', 'N/A')} Å", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font('helvetica', 'B', 10)
    pdf.cell(50, 6, "Drug-likeness (QED):", 0)
    pdf.set_font('helvetica', '', 10)
    pdf.cell(50, 6, f"{b_data.get('qed')}", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font('helvetica', 'B', 10)
    pdf.cell(50, 6, "Toxicidad ADMET:", 0)
    pdf.set_font('helvetica', '', 10)
    pdf.cell(50, 6, f"{b_data.get('admet_toxicity')}", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font('helvetica', 'B', 10)
    pdf.cell(50, 6, "SMILES:", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('helvetica', 'I', 8)
    pdf.multi_cell(95, 5, smiles)
    
    # Imagen
    if os.path.exists(img_path):
        pdf.image(img_path, x=115, y=start_y, w=80)
        
    # Limpiar temp
    try:
        os.remove(img_path)
    except Exception:
        pass
        
    pdf.output(output_pdf)
    print(f"PDF Breakthrough generado en {output_pdf}")

if __name__ == "__main__":
    generate_pdf_report()
