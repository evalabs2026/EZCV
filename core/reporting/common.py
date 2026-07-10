"""
core/reporting/common.py

Shared PDF styling: the "EZCV 2026" watermark, the disclaimer footer, and
common paragraph styles used by both report types.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import Color

DISCLAIMER_TEXT = (
    "NB: EZCV is an educational and research-assistance tool intended to simplify cyclic "
    "voltammetry analysis. While every effort has been made to validate its calculations, "
    "no automated analysis software is infallible. Please independently verify all values "
    "before using them in any publication, thesis, or official report."
)

WATERMARK_TEXT = "EZCV 2026"

_LIGHT_GRAY = Color(0.85, 0.85, 0.85)
_MED_GRAY = Color(0.5, 0.5, 0.5)


def page_decorator(canvas_obj, doc):
    """Draws the watermark near the top and the disclaimer footer at the bottom of every page."""
    width, height = letter

    # Watermark near the top of the page
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica-Bold", 34)
    canvas_obj.setFillColor(_LIGHT_GRAY)
    canvas_obj.drawCentredString(width / 2, height - 55, WATERMARK_TEXT)
    canvas_obj.restoreState()

    # Disclaimer footer, small text, centered
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica-Oblique", 6.5)
    canvas_obj.setFillColor(_MED_GRAY)
    _draw_wrapped_footer(canvas_obj, DISCLAIMER_TEXT, width, margin=0.6 * 72, y_start=28, line_height=8)
    canvas_obj.restoreState()


def _draw_wrapped_footer(canvas_obj, text, width, margin, y_start, line_height):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    max_width = width - 2 * margin
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if stringWidth(candidate, "Helvetica-Oblique", 6.5) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    y = y_start + (len(lines) - 1) * line_height
    for line in lines:
        canvas_obj.drawCentredString(width / 2, y, line)
        y -= line_height


def get_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="EZCVTitle", parent=styles["Title"], spaceAfter=6
    ))
    styles.add(ParagraphStyle(
        name="EZCVSubtitle", parent=styles["Normal"], fontSize=10,
        textColor=_MED_GRAY, spaceAfter=14
    ))
    styles.add(ParagraphStyle(
        name="EZCVSectionHeading", parent=styles["Heading2"], spaceBefore=14, spaceAfter=6
    ))
    return styles
