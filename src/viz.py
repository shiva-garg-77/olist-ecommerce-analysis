"""Shared plotting style so every chart in the notebook, report and dashboard
looks like it belongs to the same project."""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns

from src.config import FIGURES_DIR, PALETTE


def apply_style() -> None:
    sns.set_theme(style="whitegrid", context="notebook")
    mpl.rcParams.update(
        {
            "figure.dpi": 110,
            "savefig.dpi": 160,
            "savefig.bbox": "tight",
            "figure.facecolor": PALETTE["bg"],
            "axes.facecolor": PALETTE["bg"],
            "axes.edgecolor": PALETTE["grid"],
            "axes.labelcolor": PALETTE["ink"],
            "axes.titlecolor": PALETTE["ink"],
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "grid.color": PALETTE["grid"],
            "grid.linewidth": 0.8,
            "xtick.color": PALETTE["muted"],
            "ytick.color": PALETTE["muted"],
            "xtick.major.size": 0,
            "ytick.major.size": 0,
            "xtick.major.pad": 6,
            "ytick.major.pad": 6,
            "text.color": PALETTE["ink"],
            "font.size": 10,
            "legend.frameon": False,
            "figure.autolayout": False,
        }
    )


def save(fig: plt.Figure, name: str, tight: bool = True) -> Path:
    path = FIGURES_DIR / f"{name}.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    return path


def brl(value: float, decimals: int = 0) -> str:
    """Format a number as Brazilian reais, e.g. R$ 15.4M / R$ 128k."""
    if value >= 1_000_000:
        return f"R$ {value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"R$ {value / 1_000:,.0f}k"
    return f"R$ {value:,.{decimals}f}"


def fmt_thousands(x, _pos=None) -> str:
    return f"{x:,.0f}"
