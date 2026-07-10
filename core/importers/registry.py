"""
core/importers/registry.py

Entry point for importing any CV raw data file. Tries each known-format
importer (highest confidence first); if none is confident, returns a
ParsePreview for the generic fallback wizard instead of guessing blindly.
"""

from .chi import CHIImporter
from . import generic_csv

CONFIDENCE_THRESHOLD = 0.6

_KNOWN_IMPORTERS = [
    CHIImporter(),
    # Add GamryImporter(), AutolabImporter(), BiologicImporter(), ... here later.
]


def identify_and_parse(filepath: str):
    """
    Returns a tuple: (CVData or None, ParsePreview or None).
    Exactly one of the two will be non-None:
      - CVData is returned when a known format was confidently recognized.
      - ParsePreview is returned when the file needs user confirmation via
        the generic import wizard (core/importers/generic_csv.finalize_parse).
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        raw_lines = f.readlines()
    lines = [ln.rstrip("\r\n") for ln in raw_lines]

    best_importer, best_score = None, 0.0
    for importer in _KNOWN_IMPORTERS:
        score = importer.sniff(lines)
        if score > best_score:
            best_importer, best_score = importer, score

    if best_importer is not None and best_score >= CONFIDENCE_THRESHOLD:
        return best_importer.parse(filepath), None

    preview = generic_csv.build_preview(filepath)
    return None, preview
