"""
core/importers/generic_csv.py

Fallback importer used when no known-format importer (CHI, Gamry, ...)
recognizes the file. Never silently guesses and computes results - instead
it produces a ParsePreview with suggested column roles and a confidence
score per column, which the GUI shows to the user for one-time confirmation
(or correction) via the import wizard. Only after the user confirms does
finalize_parse() actually build the analysis-ready dataset.
"""

import re
import numpy as np
import pandas as pd

from .base import CVData, CVMetadata, ColumnSuggestion, ParsePreview
from ..segmentation import detect_turning_point_segments

_DELIMITER_CANDIDATES = [",", "\t", ";", "|"]

_POTENTIAL_KEYWORDS = ["potential", "volt", "e/v", "e (v)", "ewe", "voltage"]
_CURRENT_KEYWORDS = ["current", "amp", "i/a", "i (a)", "i/ma", "i/ua"]
_TIME_KEYWORDS = ["time", "sec", "s)", "/s"]
_CHARGE_KEYWORDS = ["charge", "coulomb", "q/c", "ah", "mah"]

_SCAN_RATE_RE = re.compile(r"scan\s*rate.*?([\-+0-9.eE]+)", re.IGNORECASE)
_SAMPLE_INTERVAL_RE = re.compile(r"sample\s*interval.*?([\-+0-9.eE]+)", re.IGNORECASE)


def _detect_delimiter(lines: list) -> str:
    sample_lines = [l for l in lines if l.strip()][:50]
    best_delim, best_score = ",", -1
    for delim in _DELIMITER_CANDIDATES:
        counts = [l.count(delim) for l in sample_lines if delim in l]
        if not counts:
            continue
        # a good delimiter appears a consistent number of times across many lines
        consistency = len(counts)
        if consistency > best_score:
            best_score = consistency
            best_delim = delim
    return best_delim


def _find_data_block(lines: list, delimiter: str, min_run: int = 8):
    """Find the longest run of consecutive lines that parse as pure numeric rows."""
    best_start, best_len, best_ncols = None, 0, None
    run_start, run_len, run_ncols = None, 0, None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            run_start, run_len, run_ncols = None, 0, None
            continue
        parts = [p.strip() for p in stripped.split(delimiter) if p.strip() != ""]
        if len(parts) < 2:
            run_start, run_len, run_ncols = None, 0, None
            continue
        try:
            [float(p) for p in parts]
            is_numeric = True
        except ValueError:
            is_numeric = False

        if is_numeric:
            if run_start is None or len(parts) != run_ncols:
                run_start, run_len, run_ncols = i, 1, len(parts)
            else:
                run_len += 1
            if run_len > best_len:
                best_start, best_len, best_ncols = run_start, run_len, run_ncols
        else:
            run_start, run_len, run_ncols = None, 0, None

    if best_start is None or best_len < min_run:
        raise ValueError("Could not locate a consistent block of numeric data rows in this file.")
    return best_start, best_ncols


def _get_header_labels(lines: list, data_start: int, delimiter: str, n_cols: int):
    if data_start == 0:
        return [f"col_{i}" for i in range(n_cols)]
    candidate = lines[data_start - 1].strip()
    parts = [p.strip() for p in candidate.split(delimiter) if p.strip() != ""]
    if len(parts) != n_cols:
        return [f"col_{i}" for i in range(n_cols)]
    numeric_count = 0
    for p in parts:
        try:
            float(p)
            numeric_count += 1
        except ValueError:
            pass
    if numeric_count >= n_cols / 2:
        return [f"col_{i}" for i in range(n_cols)]  # looks numeric, not a real header
    return [p.lower() for p in parts]


def _keyword_match(label: str, keywords: list) -> bool:
    return any(k in label for k in keywords)


def _column_stats(values: np.ndarray) -> dict:
    diffs = np.diff(values)
    sign_changes = int(np.sum(np.diff(np.sign(diffs)) != 0)) if len(diffs) > 1 else 0
    return {
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "range": float(np.max(values) - np.min(values)),
        "mean_abs": float(np.mean(np.abs(values))),
        "sign_changes": sign_changes,
        "monotonic_frac": float(np.mean(diffs >= 0)) if len(diffs) else 1.0,
        "diff_std_over_mean": float(np.std(diffs) / (np.mean(np.abs(diffs)) + 1e-30)) if len(diffs) else 0.0,
    }


def _suggest_roles(col_names: list, columns: np.ndarray) -> list:
    n_cols = columns.shape[1]
    suggestions = [None] * n_cols
    confidences = [0.0] * n_cols
    stats = [_column_stats(columns[:, i]) for i in range(n_cols)]

    # Pass 1: header keyword matching (high confidence)
    for i, name in enumerate(col_names):
        if _keyword_match(name, _POTENTIAL_KEYWORDS):
            suggestions[i], confidences[i] = "potential", 0.9
        elif _keyword_match(name, _CURRENT_KEYWORDS):
            suggestions[i], confidences[i] = "current", 0.9
        elif _keyword_match(name, _TIME_KEYWORDS):
            suggestions[i], confidences[i] = "time", 0.9
        elif _keyword_match(name, _CHARGE_KEYWORDS):
            suggestions[i], confidences[i] = "charge", 0.9

    # Pass 2: statistical heuristics for anything still unassigned
    unassigned = [i for i in range(n_cols) if suggestions[i] is None]
    used_roles = set(r for r in suggestions if r is not None)

    for i in unassigned:
        s = stats[i]
        # Time: strictly/near-monotonic increasing, very regular step size
        if s["monotonic_frac"] > 0.98 and s["diff_std_over_mean"] < 0.05 and "time" not in used_roles:
            suggestions[i], confidences[i] = "time", 0.6
            used_roles.add("time")
        # Potential: many sign changes (sweeps back and forth), bounded range typical of CV (<10V)
        elif s["sign_changes"] > 1 and s["range"] < 10 and "potential" not in used_roles:
            suggestions[i], confidences[i] = "potential", 0.55
            used_roles.add("potential")
        # Charge: monotonic-ish (mostly one direction) but not as regular as time
        elif s["monotonic_frac"] > 0.9 and "charge" not in used_roles and "potential" in used_roles:
            suggestions[i], confidences[i] = "charge", 0.4
            used_roles.add("charge")

    # Whatever's left and still unassigned: best guess is current (most CV files are P/I pairs)
    for i in range(n_cols):
        if suggestions[i] is None and "current" not in used_roles:
            suggestions[i], confidences[i] = "current", 0.35
            used_roles.add("current")
        elif suggestions[i] is None:
            confidences[i] = 0.2  # low-confidence leftover, unknown role

    return suggestions, confidences


def build_preview(filepath: str, n_preview_lines: int = 15) -> ParsePreview:
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        raw_lines = f.readlines()
    lines = [ln.rstrip("\r\n") for ln in raw_lines]

    delimiter = _detect_delimiter(lines)
    data_start, n_cols = _find_data_block(lines, delimiter)
    col_names = _get_header_labels(lines, data_start, delimiter, n_cols)

    # Parse a sample of the numeric block for column statistics
    sample_rows = []
    for line in lines[data_start:data_start + 500]:
        stripped = line.strip()
        if not stripped:
            continue
        parts = [p.strip() for p in stripped.split(delimiter) if p.strip() != ""]
        if len(parts) != n_cols:
            continue
        try:
            sample_rows.append([float(p) for p in parts])
        except ValueError:
            continue
    sample_arr = np.array(sample_rows)

    suggested_roles, confidences = _suggest_roles(col_names, sample_arr)

    columns = [
        ColumnSuggestion(
            index=i,
            header_label=col_names[i],
            sample_values=list(sample_arr[:5, i]),
            suggested_role=suggested_roles[i],
            confidence=confidences[i],
        )
        for i in range(n_cols)
    ]

    header_text = "\n".join(lines[:data_start])
    scan_rate_match = _SCAN_RATE_RE.search(header_text)
    sample_interval_match = _SAMPLE_INTERVAL_RE.search(header_text)

    return ParsePreview(
        filepath=filepath,
        delimiter=delimiter,
        data_start_line=data_start,
        raw_preview_lines=lines[:n_preview_lines],
        columns=columns,
        detected_scan_rate=float(scan_rate_match.group(1)) if scan_rate_match else None,
        detected_sample_interval=float(sample_interval_match.group(1)) if sample_interval_match else None,
    )


def finalize_parse(preview: ParsePreview, confirmed_roles: dict, scan_rate: float | None = None,
                    sample_interval: float | None = None) -> CVData:
    """
    confirmed_roles: {column_index: role} as confirmed/corrected by the user
    in the import wizard, e.g. {0: "potential", 1: "current"}.
    """
    with open(preview.filepath, "r", encoding="utf-8", errors="replace") as f:
        raw_lines = f.readlines()
    lines = [ln.rstrip("\r\n") for ln in raw_lines]

    role_to_index = {v: k for k, v in confirmed_roles.items()}
    if "potential" not in role_to_index or "current" not in role_to_index:
        raise ValueError("Both a potential and current column must be assigned before parsing.")

    rows = []
    for line in lines[preview.data_start_line:]:
        stripped = line.strip()
        if not stripped:
            continue
        parts = [p.strip() for p in stripped.split(preview.delimiter) if p.strip() != ""]
        try:
            values = [float(p) for p in parts]
        except ValueError:
            continue
        rows.append(values)

    arr = np.array(rows)
    n = len(arr)
    potentials = arr[:, role_to_index["potential"]]
    currents = arr[:, role_to_index["current"]]
    charges = arr[:, role_to_index["charge"]] if "charge" in role_to_index else np.full(n, np.nan)

    time_is_estimated = False
    if "time" in role_to_index:
        time = arr[:, role_to_index["time"]]
        has_native_time = True
    elif sample_interval and scan_rate:
        dt = sample_interval / scan_rate
        time = np.arange(n) * dt
        has_native_time = False
    else:
        time = np.arange(n, dtype=float)
        has_native_time = False
        time_is_estimated = True

    segment = detect_turning_point_segments(potentials)
    detected_segments = int(segment.max())

    metadata = CVMetadata(
        scan_rate=scan_rate,
        sample_interval=sample_interval,
        source_format="generic_csv",
    )

    df = pd.DataFrame({
        "index": np.arange(n),
        "time_s": time,
        "potential_V": potentials,
        "current_A": currents,
        "charge_C": charges,
        "segment": segment,
    })

    return CVData(
        df=df,
        metadata=metadata,
        detected_segments=detected_segments,
        segments_match_declared=False,  # no declared count to compare against in generic files
        segment_source="turning_point_detection",
        has_native_time=has_native_time,
        has_native_charge="charge" in role_to_index,
        time_is_estimated=time_is_estimated,
    )
