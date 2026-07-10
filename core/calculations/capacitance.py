"""
core/calculations/capacitance.py

Area-under-curve and specific capacitance calculations, ported from the
original EZCV 2.1 C# logic with the same formulas, plus a more rigorous
net-area option for users who want it.
"""

import numpy as np


def absolute_trapezoidal_area(potential: np.ndarray, current: np.ndarray) -> float:
    """
    Sum of absolute trapezoid areas between consecutive points.
    This matches the original EZCV 2.1 behavior exactly:
        area += 0.5 * |dx| * |y0 + y1|
    Note: this sums total absolute area swept, not a signed net integral.
    """
    area = 0.0
    for i in range(1, len(potential)):
        x0, x1 = potential[i - 1], potential[i]
        y0, y1 = current[i - 1], current[i]
        area += 0.5 * abs(x1 - x0) * abs(y0 + y1)
    return area


def net_signed_area(potential: np.ndarray, current: np.ndarray) -> float:
    """
    Proper signed integral (closed-loop / shoelace-style) of the CV curve.
    For a full closed CV cycle this gives the true net enclosed area, which
    corresponds to the physically meaningful net charge passed. Requires the
    segment(s) passed in to form (approximately) a closed loop.
    """
    return float(np.abs(np.trapz(current, potential)))


def specific_capacitance(area: float, mass_g: float, scan_rate_v_s: float,
                          potential_window_v: float) -> float:
    """
    Cs = Area / (2 * m * scan_rate * ΔV)
    Matches the original EZCV 2.1 formula. Units: F/g when area is in
    (V * A), mass in g, scan rate in V/s, potential window in V.
    """
    denominator = 2 * mass_g * scan_rate_v_s * potential_window_v
    if denominator == 0:
        raise ValueError("Mass, scan rate, and potential window must all be non-zero.")
    return area / denominator
