"""
core/calculations/kinetics.py

Multi-scan-rate kinetics analysis:
- Dunn's method: b-value (i = a*v^b) and capacitive/diffusive current
  contribution split (i = k1*v + k2*v^0.5), both computed as a function
  of potential across a scan-rate series.
- Trasatti analysis: total voltammetric charge extrapolation to separate
  "outer" (fast, easily accessible) charge from "inner" (diffusion-limited)
  charge.

Both require a ScanRateSeries (same sample, multiple scan rates) rather
than a single CV file.
"""

import numpy as np

from core.segmentation import classify_segment_direction
from core.calculations.capacitance import absolute_trapezoidal_area


def _get_branch_arrays(entry, direction: str):
    """
    Return (potential, current) for the branch (forward/reverse) of this
    entry's selected segments, using the most recent matching segment if
    more than one is present (e.g. a file with 2 full cycles recorded).
    Sorted ascending by potential for safe interpolation.
    """
    df = entry.filtered_df()
    match_potential, match_current = None, None
    for seg, group in df.groupby("segment"):
        potential = group["potential_V"].to_numpy()
        current = group["current_A"].to_numpy()
        if len(potential) < 2:
            continue
        if classify_segment_direction(potential) == direction:
            match_potential, match_current = potential, current  # keep latest match
    if match_potential is None:
        return None, None
    order = np.argsort(match_potential)
    return match_potential[order], match_current[order]


def common_potential_grid(series, direction: str, n_points: int = 200):
    mins, maxs = [], []
    for entry in series.entries:
        p, _ = _get_branch_arrays(entry, direction)
        if p is None:
            continue
        mins.append(p.min())
        maxs.append(p.max())
    if not mins:
        raise ValueError(f"No '{direction}' segments found in any file in this series.")
    lo, hi = max(mins), min(maxs)
    if lo >= hi:
        raise ValueError("Scan-rate files do not share an overlapping potential range.")
    return np.linspace(lo, hi, n_points)


def _interpolate_series_currents(series, direction: str, potential_grid):
    result = {}
    for entry in series.entries:
        p, c = _get_branch_arrays(entry, direction)
        if p is None:
            continue
        result[entry.scan_rate] = np.interp(potential_grid, p, c)
    return result


def dunn_b_value_curve(series, direction: str = "forward", n_points: int = 200):
    """
    Returns (potential_grid, b_values). b(V) close to 1.0 indicates a
    surface-capacitive process at that potential; close to 0.5 indicates
    a diffusion-controlled (battery-like) process.
    """
    grid = common_potential_grid(series, direction, n_points)
    currents = _interpolate_series_currents(series, direction, grid)
    rates = np.array(sorted(currents.keys()))
    log_v = np.log10(rates)

    b_values = np.full(len(grid), np.nan)
    for i in range(len(grid)):
        mag = np.abs(np.array([currents[r][i] for r in rates]))
        if np.any(mag <= 0):
            continue
        slope, _intercept = np.polyfit(log_v, np.log10(mag), 1)
        b_values[i] = slope
    return grid, b_values


def capacitive_diffusive_split(series, direction: str = "forward", n_points: int = 200):
    """
    Solves i(V) = k1*v + k2*v^0.5 at each potential via least squares
    across the scan-rate series (Dunn's method, full form).
    Returns (potential_grid, k1_curve, k2_curve).
    """
    grid = common_potential_grid(series, direction, n_points)
    currents = _interpolate_series_currents(series, direction, grid)
    rates = np.array(sorted(currents.keys()))
    design_matrix = np.column_stack([rates, np.sqrt(rates)])

    k1 = np.full(len(grid), np.nan)
    k2 = np.full(len(grid), np.nan)
    for i in range(len(grid)):
        y = np.array([currents[r][i] for r in rates])
        coeffs, *_ = np.linalg.lstsq(design_matrix, y, rcond=None)
        k1[i], k2[i] = coeffs
    return grid, k1, k2


def percent_capacitive_at_scan_rate(k1_curve, k2_curve, scan_rate: float):
    """% of current that is capacitive (surface-controlled) at a given scan rate, per potential."""
    i_cap = k1_curve * scan_rate
    i_total = k1_curve * scan_rate + k2_curve * np.sqrt(scan_rate)
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(i_total != 0, 100.0 * i_cap / i_total, np.nan)
    return pct


def trasatti_analysis(series):
    """
    Total voltammetric charge (q*) at each scan rate, extrapolated to
    separate outer (fast) charge from total charge:
      - q_outer: intercept of q* vs v^(-1/2), extrapolated to v -> infinity
      - q_total: reciprocal of the intercept of (1/q*) vs v^(1/2), extrapolated to v -> 0
      - q_inner = q_total - q_outer (diffusion-limited charge)
    """
    rates, q_star = [], []
    for entry in series.entries:
        df = entry.filtered_df()
        potential = df["potential_V"].to_numpy()
        current = df["current_A"].to_numpy()
        area = absolute_trapezoidal_area(potential, current)
        q = area / entry.scan_rate  # (V*A) / (V/s) = A*s = Coulombs
        rates.append(entry.scan_rate)
        q_star.append(q)

    rates = np.array(rates)
    q_star = np.array(q_star)

    # Catch the failure mode where one file's charge is anomalously near-zero
    # (usually a segment-selection issue for that specific file) BEFORE it
    # silently propagates into 1/q* = inf and wrecks the whole linear fit.
    median_q = np.median(q_star)
    for rate, q in zip(rates, q_star):
        if q <= 0 or (median_q > 0 and q < 0.05 * median_q):
            raise ValueError(
                f"The file at scan rate {rate} V/s produced an anomalously low charge "
                f"(q* = {q:.3e} C, vs. a median of {median_q:.3e} C across the series). "
                f"This is usually caused by an incorrect segment selection for that specific "
                f"file. Please check its Start/End segment values in the Scan-Rate Series "
                f"import wizard."
            )

    x_outer = rates ** -0.5
    slope_o, intercept_o = np.polyfit(x_outer, q_star, 1)
    q_outer = intercept_o

    x_total = rates ** 0.5
    y_total = 1.0 / q_star
    slope_t, intercept_t = np.polyfit(x_total, y_total, 1)
    q_total = (1.0 / intercept_t) if intercept_t != 0 else float("nan")

    q_inner = (q_total - q_outer) if np.isfinite(q_total) else float("nan")

    percent_outer = (100.0 * q_outer / q_total) if (np.isfinite(q_total) and q_total != 0) else float("nan")
    percent_inner = (100.0 - percent_outer) if np.isfinite(percent_outer) else float("nan")

    return {
        "rates": rates,
        "q_star": q_star,
        "q_outer": q_outer,
        "q_total": q_total,
        "q_inner": q_inner,
        "percent_outer": percent_outer,
        "percent_inner": percent_inner,
        "outer_fit": {"x": x_outer, "y": q_star, "slope": slope_o, "intercept": intercept_o},
        "total_fit": {"x": x_total, "y": y_total, "slope": slope_t, "intercept": intercept_t},
    }
