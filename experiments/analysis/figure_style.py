"""Shared print style for the three learning figures; never alter data or bands."""

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HIERFL = "#008000"
SPYKER = "#0000FF"
FEEDBACK_DISABLED = "#FF0000"
BAND_ALPHA = 0.10


def panels():
    """Use the same physical canvas, type sizes and plotting area in every cohort."""
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "mathtext.fontset": "dejavusans",
            "font.size": 8.5,
            "axes.titlesize": 8.5,
            "axes.labelsize": 8.5,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 7.5,
            "axes.linewidth": 0.55,
            "lines.linewidth": 0.85,
            "lines.markersize": 1.7,
            "lines.markeredgewidth": 0.45,
            "lines.markerfacecolor": "white",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.facecolor": "white",
        }
    )
    figure, axes = plt.subplots(2, 1, figsize=(3.45, 3.65), sharex=True, sharey=True)
    figure.subplots_adjust(left=0.17, right=0.97, bottom=0.22, top=0.94, hspace=0.38)
    return figure, axes


def finish(figure, axes, titles, horizon, figures, stem, *, accuracy_limit=100):
    """Use zero-based, explicitly labelled scales and compact shared legends."""
    tick_step = 10 if accuracy_limit <= 40 else 20
    y_ticks = list(range(0, accuracy_limit + 1, tick_step))
    for axis, title in zip(axes, titles, strict=True):
        axis.axhline(
            10,
            color="#666666",
            linestyle=":",
            linewidth=0.6,
            label="Chance (10%)",
            zorder=1,
        )
        axis.set(
            title=title,
            xlim=(-0.02 * horizon, 1.02 * horizon),
            ylim=(0, accuracy_limit),
            xticks=[horizon * index / 6 for index in range(7)],
            yticks=y_ticks,
        )
        axis.set_axisbelow(True)
        axis.grid(color="#B0B0B0", linewidth=0.4, alpha=0.45)
        for spine in axis.spines.values():
            spine.set_visible(True)
            spine.set_color("black")
        axis.tick_params(colors="black", width=0.55, length=2.5)
    figure.supylabel("Test accuracy (%)", x=0.012, fontsize=8.5)
    axes[-1].set_xlabel("Virtual time (s)")
    handles, labels = axes[0].get_legend_handles_labels()
    columns = 3
    if stem == "primary-learning-curves":
        # Separate method from placement instead of repeating both in four long
        # labels. Compact legend rows leave the common time label unobstructed.
        handles = [
            Line2D([], [], color=HIERFL, marker="o", label="HierFL"),
            Line2D([], [], color=SPYKER, marker="s", label="Spyker-inspired"),
            Line2D([], [], color="#555555", linestyle="-", label="2/2/2"),
            Line2D([], [], color="#555555", linestyle="--", label="4/1/1"),
            Line2D([], [], color="#727272", linestyle=":", label="Chance (10%)"),
        ]
        labels = [handle.get_label() for handle in handles]
        columns = 3
    legend = figure.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.005),
        ncol=columns,
        frameon=True,
        facecolor="white",
        edgecolor="#CCCCCC",
        framealpha=1,
        columnspacing=0.8,
        handlelength=1.7,
    )
    legend.get_frame().set_linewidth(0.5)
    figure.savefig(
        figures / f"{stem}.pdf",
        metadata={"CreationDate": None, "ModDate": None},
    )
    figure.savefig(figures / f"{stem}.png", dpi=300)
    plt.close(figure)
