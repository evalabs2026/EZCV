"""
core/reporting/plots.py

Pure matplotlib figure builders (no Qt dependency) for Dunn's b-value and
Trasatti analysis. Used by both the GUI (wrapped in a Qt canvas) and the
PDF report generator (saved directly to an image), so the two never drift
out of sync with each other.
"""

from matplotlib.figure import Figure

from core.calculations import kinetics


def build_dunn_figure(series):
    """Returns (figure, grid, b_values). Raises on failure - caller handles it."""
    grid, b_values = kinetics.dunn_b_value_curve(series, direction="forward")

    figure = Figure(figsize=(6, 4))
    ax = figure.add_subplot(111)
    ax.scatter(grid, b_values, s=10, color="tab:blue")
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8, label="b = 1 (capacitive)")
    ax.axhline(0.5, color="gray", linestyle=":", linewidth=0.8, label="b = 0.5 (diffusion-controlled)")
    ax.set_xlabel("Potential (V)")
    ax.set_ylabel("b-value")
    ax.set_ylim(-0.1, 1.5)
    ax.legend(fontsize=8)
    ax.set_title("Dunn's b-value vs Potential (forward sweep)")
    figure.tight_layout()

    return figure, grid, b_values


def _r_squared(x, y, slope, intercept):
    import numpy as np
    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    return 1 - ss_res / ss_tot if ss_tot != 0 else float("nan")


def build_trasatti_figure(series):
    """Returns (figure, result_dict). result_dict includes r2_outer/r2_total."""
    result = kinetics.trasatti_analysis(series)

    figure = Figure(figsize=(6, 5))

    ax1 = figure.add_subplot(211)
    outer = result["outer_fit"]
    ax1.scatter(outer["x"], outer["y"], color="tab:orange")
    xfit = [0, max(outer["x"])]
    yfit = [outer["intercept"], outer["slope"] * max(outer["x"]) + outer["intercept"]]
    ax1.plot(xfit, yfit, "--", color="gray")
    ax1.scatter([0], [result["q_outer"]], color="red", zorder=5, label=f"q_outer = {result['q_outer']:.3e} C")
    ax1.set_xlabel("v$^{-1/2}$ (V/s)$^{-1/2}$")
    ax1.set_ylabel("q* (C)")
    ax1.set_title("Outer charge extrapolation (v \u2192 \u221e)")
    ax1.legend(fontsize=8)

    ax2 = figure.add_subplot(212)
    total = result["total_fit"]
    ax2.scatter(total["x"], total["y"], color="tab:green")
    xfit2 = [0, max(total["x"])]
    yfit2 = [total["intercept"], total["slope"] * max(total["x"]) + total["intercept"]]
    ax2.plot(xfit2, yfit2, "--", color="gray")
    inv_q_total = 1.0 / result["q_total"] if result["q_total"] else float("nan")
    ax2.scatter([0], [inv_q_total], color="red", zorder=5, label=f"q_total = {result['q_total']:.3e} C")
    ax2.set_xlabel("v$^{1/2}$ (V/s)$^{1/2}$")
    ax2.set_ylabel("1/q* (C$^{-1}$)")
    ax2.set_title("Total charge extrapolation (v \u2192 0)")
    ax2.legend(fontsize=8)

    figure.tight_layout()

    result["r2_outer"] = _r_squared(outer["x"], outer["y"], outer["slope"], outer["intercept"])
    result["r2_total"] = _r_squared(total["x"], total["y"], total["slope"], total["intercept"])

    return figure, result
