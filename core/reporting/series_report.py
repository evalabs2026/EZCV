"""
core/reporting/series_report.py

Builds a PDF report for scan-rate series analysis: Dunn's b-value and/or
Trasatti results, whichever were actually run.
"""

from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, KeepTogether
from reportlab.lib import colors
from reportlab.lib.units import inch

from core.reporting.common import page_decorator, get_styles
from core.reporting.single_report import _make_table


def build_series_report(output_path, series, dunn_image_path=None, trasatti_image_path=None,
                         trasatti_result=None):
    styles = get_styles()
    story = []

    story.append(Paragraph("EZCV - Scan-Rate Series Analysis Report", styles["EZCVTitle"]))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        styles["EZCVSubtitle"]
    ))

    # --- Files / segments table ---
    story.append(Paragraph("Files Included", styles["EZCVSectionHeading"]))
    file_rows = [["File", "Scan rate (V/s)", "Segments used"]]
    for entry in series.entries:
        name = entry.filepath.split("/")[-1].split("\\")[-1]
        segs = ", ".join(str(s) for s in entry.selected_segments)
        file_rows.append([name, str(entry.scan_rate), segs])
    files_table = Table(file_rows, colWidths=[2.8 * inch, 1.3 * inch, 1.4 * inch])
    files_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(files_table)
    story.append(Spacer(1, 12))

    if dunn_image_path is None and trasatti_image_path is None:
        story.append(Paragraph(
            "No analysis has been run yet for this series.", styles["Normal"]
        ))

    if dunn_image_path:
        story.append(Paragraph("Dunn's b-value Analysis", styles["EZCVSectionHeading"]))
        story.append(Image(dunn_image_path, width=5.5 * inch, height=3.7 * inch))
        story.append(Paragraph(
            "b \u2248 1: surface-capacitive process at that potential. "
            "b \u2248 0.5: diffusion-controlled process. Values near the potential-window "
            "edges are less reliable (low current, unstable fit).",
            styles["Normal"]
        ))
        story.append(Spacer(1, 12))

    if trasatti_image_path and trasatti_result:
        r = trasatti_result
        result_rows = [
            ["Parameter", "Value"],
            ["q_total (total charge)", f"{r['q_total']:.4e} C"],
            ["q_outer (fast, easily accessible)", f"{r['q_outer']:.4e} C"],
            ["q_inner (diffusion-limited)", f"{r['q_inner']:.4e} C"],
            ["\u2248 EDLC / fast surface contribution", f"{r['percent_outer']:.1f} %"],
            ["\u2248 Pseudocapacitive / diffusion-limited", f"{r['percent_inner']:.1f} %"],
            ["R\u00b2 (outer charge fit)", f"{r.get('r2_outer', float('nan')):.4f}"],
            ["R\u00b2 (total charge fit)", f"{r.get('r2_total', float('nan')):.4f}"],
        ]
        story.append(KeepTogether([
            Paragraph("Trasatti Analysis", styles["EZCVSectionHeading"]),
            Image(trasatti_image_path, width=5.5 * inch, height=4.6 * inch),
            Spacer(1, 6),
            _make_table(result_rows),
            Spacer(1, 6),
            Paragraph(
                "Note: the outer/inner split is the standard Trasatti proxy for EDLC vs. "
                "pseudocapacitive contribution - a widely used approximation, not a strict "
                "physical separation. R\u00b2 values below ~0.95 suggest the linear extrapolation "
                "may not be very reliable over the scan-rate range used.",
                styles["Normal"]
            )
        ]))

    doc = SimpleDocTemplate(output_path, pagesize=letter,
                             topMargin=0.9 * inch, bottomMargin=0.7 * inch)
    doc.build(story, onFirstPage=page_decorator, onLaterPages=page_decorator)
