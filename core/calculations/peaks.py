"""
core/calculations/peaks.py

Redox peak analysis for cyclic voltammetry:
- Oxidation peak potential/current (Epa, Ipa) - found on forward (increasing
  potential) sweeps, where the anodic peak current is a maximum.
- Reduction peak potential/current (Epc, Ipc) - found on reverse (decreasing
  potential) sweeps, where the cathodic peak current is a minimum (most
  negative).
- Peak separation (ΔEp), formal potential (E°'), and peak current ratio
  (Ipa/Ipc) are derived from the above.

Segment sweep direction is determined from the sign of the potential's
rate of change within each segment - this reuses the same "trust the data,
not file labels" principle as segmentation.
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.signal import find_peaks


@dataclass
class PeakAnalysisResult:
    epa: float | None  # oxidation (anodic) peak potential, V
    ipa: float | None  # oxidation (anodic) peak current, A
    epc: float | None  # reduction (cathodic) peak potential, V
    ipc: float | None  # reduction (cathodic) peak current, A
    delta_ep: float | None       # |Epa - Epc|, V
    formal_potential: float | None  # (Epa + Epc) / 2, V
    ipa_ipc_ratio: float | None     # |Ipa / Ipc|
    peaks_detected: bool = True  # False if the curve has no genuine interior peak
                                  # (e.g. rectangular/capacitive CV shape)


def _classify_segment_direction(potential: np.ndarray) -> str:
    """Return 'forward' (increasing) or 'reverse' (decreasing) for a segment."""
    diffs = np.diff(potential)
    if len(diffs) == 0:
        return "forward"
    return "forward" if np.mean(diffs) >= 0 else "reverse"


def _find_interior_peak(potential: np.ndarray, current: np.ndarray, mode: str, prominence_frac: float = 0.02):
    """
    Find a genuine LOCAL peak (not just the array endpoint) in `current`.
    mode='max' looks for anodic peaks, mode='min' looks for cathodic peaks.
    Returns (potential_at_peak, current_at_peak) or (None, None) if no
    interior peak with meaningful prominence exists (e.g. a monotonic,
    rectangular/capacitive-shaped curve with no real redox peak).
    """
    n = len(current)
    if n < 5:
        return None, None

    signal = current if mode == "max" else -current
    data_range = float(np.max(signal) - np.min(signal))
    if data_range == 0:
        return None, None

    min_prominence = prominence_frac * data_range
    peak_indices, _ = find_peaks(signal, prominence=min_prominence)

    edge_margin = max(2, int(0.01 * n))
    interior_peaks = [i for i in peak_indices if edge_margin <= i <= n - 1 - edge_margin]

    if not interior_peaks:
        return None, None

    best_idx = max(interior_peaks, key=lambda i: signal[i])
    return float(potential[best_idx]), float(current[best_idx])


def analyze_peaks(df: pd.DataFrame) -> PeakAnalysisResult:
    """
    df must contain 'potential_V', 'current_A', and 'segment' columns
    (already filtered to whichever segments the user selected).
    """
    epa = ipa = epc = ipc = None

    for seg_id, group in df.groupby("segment"):
        potential = group["potential_V"].to_numpy()
        current = group["current_A"].to_numpy()
        if len(potential) < 5:
            continue

        direction = _classify_segment_direction(potential)

        if direction == "forward":
            e_candidate, i_candidate = _find_interior_peak(potential, current, mode="max")
            if e_candidate is not None and (ipa is None or i_candidate > ipa):
                epa, ipa = e_candidate, i_candidate
        else:
            e_candidate, i_candidate = _find_interior_peak(potential, current, mode="min")
            if e_candidate is not None and (ipc is None or i_candidate < ipc):
                epc, ipc = e_candidate, i_candidate

    peaks_detected = (epa is not None) or (epc is not None)
    delta_ep = abs(epa - epc) if (epa is not None and epc is not None) else None
    formal_potential = ((epa + epc) / 2) if (epa is not None and epc is not None) else None
    ipa_ipc_ratio = (abs(ipa / ipc) if (ipa is not None and ipc not in (None, 0)) else None)

    return PeakAnalysisResult(
        epa=epa, ipa=ipa, epc=epc, ipc=ipc,
        delta_ep=delta_ep, formal_potential=formal_potential,
        ipa_ipc_ratio=ipa_ipc_ratio, peaks_detected=peaks_detected,
    )
