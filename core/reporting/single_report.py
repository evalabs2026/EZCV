"""
core/reporting/single_report.py

Builds a PDF report for a single-file CV analysis: plot, sample info,
and calculated results.
"""

from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, KeepTogether
)
from reportlab.lib import colors
from reportlab.lib.units import inch

from core.reporting.common import page_decorator, get_styles


def build_single_report(output_path, filename, metadata, sample_info, results, plot_image_path,
                         selected_segments):
    styles = get_styles()
    story = []

    story.append(Paragraph("EZCV - Single CV Analysis Report", styles["EZCVTitle"]))
    story.append(Paragraph(
        f"File: {filename} &nbsp;&nbsp;|&nbsp;&nbsp; Generated: "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        styles["EZCVSubtitle"]
    ))

    # --- Instrument / scan info ---
    info_rows = [["Field", "Value"]]
    if metadata.get("instrument_model"):
        info_rows.append(["Instrument", metadata["instrument_model"]])
    if metadata.get("scan_rate") is not None:
        info_rows.append(["Scan rate (V/s)", str(metadata["scan_rate"])])
    if metadata.get("init_e") is not None and metadata.get("high_e") is not None:
        info_rows.append(["Potential window (file)", f"{metadata.get('low_e')} V to {metadata.get('high_e')} V"])
    info_rows.append(["Segments used", ", ".join(str(s) for s in selected_segments)])
    story.append(KeepTogether([
        Paragraph("Scan Information", styles["EZCVSectionHeading"]),
        _make_table(info_rows),
    ]))
    story.append(Spacer(1, 10))

    # --- Sample info ---
    if sample_info and any(v is not None for v in sample_info.values()):
        sample_rows = [["Field", "Value"]]
        if sample_info.get("mass_g") is not None:
            sample_rows.append(["Mass (g)", str(sample_info["mass_g"])])
        if sample_info.get("area_cm2") is not None:
            sample_rows.append(["Electrode area (cm\u00b2)", str(sample_info["area_cm2"])])
        if sample_info.get("v0") is not None and sample_info.get("v1") is not None:
            sample_rows.append(["Potential window (used)", f"{sample_info['v0']} V to {sample_info['v1']} V"])
        story.append(KeepTogether([
            Paragraph("Sample Information", styles["EZCVSectionHeading"]),
            _make_table(sample_rows),
        ]))
        story.append(Spacer(1, 10))

    # --- Plot ---
    if plot_image_path:
        story.append(KeepTogether([
            Paragraph("CV Plot", styles["EZCVSectionHeading"]),
            Image(plot_image_path, width=5.5 * inch, height=4 * inch),
        ]))
        story.append(Spacer(1, 10))

    # --- Results ---
    if results:
        result_rows = [["Parameter", "Value"]]
        for key, value in results.items():
            result_rows.append([key, str(value)])
        story.append(KeepTogether([
            Paragraph("Calculated Results", styles["EZCVSectionHeading"]),
            _make_table(result_rows),
        ]))
    else:
        story.append(KeepTogether([
            Paragraph("Calculated Results", styles["EZCVSectionHeading"]),
            Paragraph("No parameters were calculated for this file.", styles["Normal"]),
        ]))

    doc = SimpleDocTemplate(output_path, pagesize=letter,
                             topMargin=0.9 * inch, bottomMargin=0.7 * inch)
    doc.build(story, onFirstPage=page_decorator, onLaterPages=page_decorator)


def _make_table(rows):
    table = Table(rows, colWidths=[2.2 * inch, 3.3 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table
