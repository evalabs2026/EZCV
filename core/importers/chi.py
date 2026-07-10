"""
core/importers/chi.py

Importer for CH Instruments (CHI) potentiostat CV text exports.
Handles both observed layouts: 2-column (Potential, Current) and
4-column (Potential, Current, Charge, Time) variants, and validates
inline 'Segment N:' tags against turning-point detection rather than
trusting them blindly.
"""

import re
import numpy as np
import pandas as pd

from .base import BaseImporter, CVData, CVMetadata

_KEY_VALUE_RE = re.compile(r"^([A-Za-z /()%]+?)\s*=\s*(.+)$")
_SEGMENT_TAG_RE = re.compile(r"^Segment\s*(\d+)\s*:\s*$", re.IGNORECASE)
_RESULT_LINE_RE = re.compile(r"^([A-Za-z]+)\s*=\s*([-+0-9.eE]+)\s*([A-Za-z%]*)\s*$")


class CHIImporter(BaseImporter):
    name = "chi"

    def sniff(self, lines: list) -> float:
        text = "\n".join(lines[:25]).lower()
        score = 0.0
        if "instrument model" in text and "chi" in text:
            score += 0.7
        if "cyclic voltammetry" in text:
            score += 0.2
        if "scan rate" in text and "sample interval" in text:
            score += 0.2
        return min(score, 1.0)

    def parse(self, filepath: str) -> CVData:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            raw_lines = f.readlines()
        lines = [ln.rstrip("\r\n") for ln in raw_lines]

        metadata, results_idx = self._parse_leading_metadata(lines)
        metadata.source_format = self.name
        header_idx, col_names = self._find_column_header(lines, results_idx)
        self._capture_instrument_results(lines, results_idx, header_idx, metadata)
        col_map = self._classify_columns(col_names)
        n_cols = len(col_names)

        potentials, currents, charges, native_times = [], [], [], []
        inline_segment_labels = []
        current_inline_label = None
        saw_any_inline_tag = False

        for line in lines[header_idx + 1:]:
            stripped = line.strip()
            if not stripped:
                continue
            tag_match = _SEGMENT_TAG_RE.match(stripped)
            if tag_match:
                current_inline_label = int(tag_match.group(1))
                saw_any_inline_tag = True
                continue
            parts = stripped.split(",")
            if len(parts) < 2:
                continue
            try:
                values = [float(p) for p in parts[:n_cols]]
            except ValueError:
                continue
            if len(values) < 2:
                continue

            potentials.append(values[col_map["potential"]])
            currents.append(values[col_map["current"]])
            charges.append(values[col_map["charge"]] if "charge" in col_map and len(values) > col_map["charge"] else np.nan)
            native_times.append(values[col_map["time"]] if "time" in col_map and len(values) > col_map["time"] else np.nan)
            inline_segment_labels.append(current_inline_label)

        potentials = np.array(potentials)
        currents = np.array(currents)
        charges = np.array(charges)
        native_times = np.array(native_times)
        n = len(potentials)

        if n == 0:
            raise ValueError("No numeric data rows found in CHI file.")

        has_native_time = "time" in col_map and not np.all(np.isnan(native_times))
        has_native_charge = "charge" in col_map and not np.all(np.isnan(charges))
        time_is_estimated = False

        if has_native_time:
            time = native_times
        elif metadata.sample_interval and metadata.scan_rate:
            dt = metadata.sample_interval / metadata.scan_rate
            time = np.arange(n) * dt
        else:
            time = np.arange(n, dtype=float)
            time_is_estimated = True

        tp_segments = self._detect_turning_point_segments(potentials)
        tp_segment_count = int(tp_segments.max())

        inline_labels_complete = saw_any_inline_tag and all(l is not None for l in inline_segment_labels)
        if inline_labels_complete:
            inline_arr = np.array(inline_segment_labels, dtype=int)
            inline_segment_count = len(np.unique(inline_arr))
            if inline_segment_count == tp_segment_count:
                segment = inline_arr
                segment_source = "inline_tags"
                detected_segments = inline_segment_count
            else:
                segment = tp_segments
                segment_source = "turning_point_detection"
                detected_segments = tp_segment_count
        else:
            segment = tp_segments
            segment_source = "turning_point_detection"
            detected_segments = tp_segment_count

        segments_match_declared = (
            metadata.declared_segments is not None
            and detected_segments == metadata.declared_segments
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
            segments_match_declared=segments_match_declared,
            segment_source=segment_source,
            has_native_time=has_native_time,
            has_native_charge=has_native_charge,
            time_is_estimated=time_is_estimated,
        )

    # --- internal helpers -------------------------------------------------

    def _parse_leading_metadata(self, lines):
        meta = CVMetadata()
        i = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.lower().startswith("results:"):
                return meta, i
            if not stripped:
                continue
            if stripped.lower().startswith("instrument model"):
                meta.instrument_model = stripped.split(":", 1)[-1].strip()
                continue
            m = _KEY_VALUE_RE.match(stripped)
            if not m:
                continue
            key, val = m.group(1).strip(), m.group(2).strip()
            meta.raw_header[key] = val
            key_lower = key.lower()
            try:
                if key_lower.startswith("init e"):
                    meta.init_e = float(val)
                elif key_lower.startswith("high e"):
                    meta.high_e = float(val)
                elif key_lower.startswith("low e"):
                    meta.low_e = float(val)
                elif key_lower.startswith("scan rate"):
                    meta.scan_rate = float(val)
                elif key_lower.startswith("sample interval"):
                    meta.sample_interval = float(val)
                elif key_lower == "segment":
                    meta.declared_segments = int(float(val))
                elif key_lower.startswith("quiet time"):
                    meta.quiet_time = float(val)
                elif key_lower.startswith("sensitivity"):
                    meta.sensitivity = float(val)
            except ValueError:
                pass
        return meta, i

    def _find_column_header(self, lines, start):
        for i in range(start, len(lines)):
            line = lines[i].strip()
            if "potential" in line.lower() and "current" in line.lower():
                cols = [c.strip().lower() for c in line.split(",")]
                return i, cols
        raise ValueError("Could not find CHI column header line.")

    def _capture_instrument_results(self, lines, start, end, meta):
        for line in lines[start:end]:
            stripped = line.strip()
            m = _RESULT_LINE_RE.match(stripped)
            if m:
                key, val, unit = m.groups()
                try:
                    meta.instrument_results[key] = float(val)
                except ValueError:
                    pass

    def _classify_columns(self, col_names):
        mapping = {}
        for idx, name in enumerate(col_names):
            if "potential" in name:
                mapping["potential"] = idx
            elif "current" in name:
                mapping["current"] = idx
            elif "charge" in name:
                mapping["charge"] = idx
            elif "time" in name:
                mapping["time"] = idx
        if "potential" not in mapping or "current" not in mapping:
            raise ValueError(f"Could not identify potential/current columns in header: {col_names}")
        return mapping

    def _detect_turning_point_segments(self, potential):
        n = len(potential)
        if n < 3:
            return np.ones(n, dtype=int)
        diffs = np.diff(potential)
        signs = np.sign(diffs)
        for i in range(1, len(signs)):
            if signs[i] == 0:
                signs[i] = signs[i - 1]
        segment = np.ones(n, dtype=int)
        current_seg = 1
        for i in range(1, n):
            step_sign = signs[i - 1] if i - 1 < len(signs) else signs[-1]
            prev_sign = signs[i - 2] if i - 2 >= 0 else step_sign
            if i >= 2 and step_sign != 0 and prev_sign != 0 and step_sign != prev_sign:
                current_seg += 1
            segment[i] = current_seg
        return segment
