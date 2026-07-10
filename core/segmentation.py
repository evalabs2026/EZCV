"""
core/segmentation.py

Format-agnostic CV segment detection: identifies segment boundaries from
genuine direction reversals (turning points) in a potential sweep, rather
than trusting any file's own segment labels. Works identically regardless
of which instrument or importer produced the data.
"""

import numpy as np


def detect_turning_point_segments(potential: np.ndarray) -> np.ndarray:
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


def classify_segment_direction(potential: np.ndarray) -> str:
    """Return 'forward' (increasing potential) or 'reverse' (decreasing)."""
    diffs = np.diff(potential)
    if len(diffs) == 0:
        return "forward"
    return "forward" if np.mean(diffs) >= 0 else "reverse"
