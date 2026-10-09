"""Shared matplotlib style for report charts."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from common import ROOT  # noqa: E402

CHART_DIR = ROOT / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": ["PingFang SC", "Hiragino Sans GB", "Heiti SC", "Arial Unicode MS"],
    "axes.unicode_minus": False,
    "figure.dpi": 110,
    "savefig.dpi": 150,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 8.5,
    "legend.frameon": False,
    "figure.facecolor": "#fbfaf7",
    "axes.facecolor": "#fbfaf7",
    "savefig.facecolor": "#fbfaf7",
})

C = {
    "stock": "#1b6b80", "spot": "#c9874a", "spot2": "#8c5a2b", "fut1": "#2f63b3", "fut2": "#9b59a6",
    "fut3": "#3f9a6b", "fut4": "#d1495b", "grey": "#8a8a8a", "dark": "#2b2b2b", "light": "#d9d4c7",
    "muyuan": "#1b6b80", "wens": "#d1495b", "small": "#e0a458", "gd": "#c0392b", "nat": "#34495e",
}
PALETTE = ["#1b6b80", "#d1495b", "#e0a458", "#3f9a6b", "#6c5b7b", "#2f63b3", "#8c5a2b", "#7f8c8d",
           "#c06c84", "#355c7d", "#99b898", "#f67280", "#4b4b4b", "#a0522d", "#5d8aa8", "#b5651d",
           "#2e8b57", "#8b008b", "#cd853f", "#708090"]


def title(fig, main, sub=None):
    h = fig.get_figheight()
    fig.suptitle(main, x=0.01, ha="left", fontsize=15, fontweight="bold", y=1 + 0.62 / h)
    if sub:
        fig.text(0.01, 1 + 0.2 / h, sub, ha="left", fontsize=10, color="#555555")


def source(fig, text, y=0.005):
    fig.text(0.01, y, "来源/口径：" + text, ha="left", fontsize=8, color="#666666", wrap=True)


def year_axis(ax, fmt="%Y"):
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))


def save(fig, name):
    p = CHART_DIR / name
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    return p
