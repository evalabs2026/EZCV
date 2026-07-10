"""
core/importers/base.py

Shared data structures and the common interface every format-specific
importer (CHI, Gamry, Autolab, generic fallback, ...) implements.

Design principle: a "confident" importer (one that recognizes its own
format's fingerprint) parses automatically. An importer that ISN'T sure
never guesses silently - it returns a ParsePreview for a human to confirm
in the import wizard instead. Wrong-but-plausible numbers are worse than
asking a one-time question.
"""

from dataclasses import dataclass, field
import pandas as pd


@dataclass
class CVMetadata:
    init_e: float | None = None
    high_e: float | None = None
    low_e: float | None = None
    scan_rate: float | None = None        # V/s
    sample_interval: float | None = None  # V
    declared_segments: int | None = None
    quiet_time: float | None = None
    sensitivity: float | None = None
    instrument_model: str | None = None
    source_format: str = "unknown"
    raw_header: dict = field(default_factory=dict)
    instrument_results: dict = field(default_factory=dict)


@dataclass
class CVData:
    df: pd.DataFrame          # index, time_s, potential_V, current_A, charge_C, segment
    metadata: CVMetadata
    detected_segments: int
    segments_match_declared: bool
    segment_source: str       # "inline_tags" | "turning_point_detection"
    has_native_time: bool
    has_native_charge: bool
    time_is_estimated: bool = False   # True if time had to be guessed (no dt, no native time)


@dataclass
class ColumnSuggestion:
    """One column's suggested semantic role, shown to the user in the import wizard."""
    index: int
    header_label: str
    sample_values: list
    suggested_role: str | None   # "potential" | "current" | "time" | "charge" | None
    confidence: float            # 0.0 - 1.0


@dataclass
class ParsePreview:
    """
    Returned when no known-format importer recognizes the file. Represents
    the generic importer's best guess, to be confirmed/corrected by the user
    before any calculation happens.
    """
    filepath: str
    delimiter: str
    data_start_line: int
    raw_preview_lines: list
    columns: list  # list[ColumnSuggestion]
    detected_scan_rate: float | None = None
    detected_sample_interval: float | None = None


class BaseImporter:
    """Interface every named-format importer implements."""
    name = "base"

    def sniff(self, lines: list) -> float:
        """
        Return a confidence score (0.0-1.0) that this importer recognizes
        the file's format, WITHOUT fully parsing it. Should be cheap and
        based on fingerprints (e.g. an 'Instrument Model: CHIxxxx' line).
        """
        raise NotImplementedError

    def parse(self, filepath: str) -> CVData:
        """Fully parse the file. Only called when sniff() was confident."""
        raise NotImplementedError
