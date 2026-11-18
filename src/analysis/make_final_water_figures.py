"""Generate final figures for modeled data-center water-resource impacts.

Population normalization is intentionally excluded from this version and
will be added later as a separate community-context analysis.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter


ROOT = Path(__file__).resolve().parents[2]

FIG_DIR = ROOT / "outputs/figures"

TEMPORAL_SUMMARY = (
    ROOT / "outputs/temporal_water_summary_2023_2030.csv"
)

HUC8_2030 = (
    ROOT / "outputs/water_burden_huc8_2030.csv"
)

TEMPORAL_SITES = (
    ROOT / "outputs/temporal_water_2023_2030.csv"
)

DUPLICATE_SENSITIVITY = (
    ROOT / "outputs/apple_duplicate_sensitivity_water.csv"
)

SUSPECTED_DUPLICATE = "im3_00567575425"
SENSITIVITY_HUC8 = "15050100"

SCENARIOS = [
    "low",
    "moderate",
    "high",
    "higher",
]


def billions(value, position=None):
    return f"{value / 1e9:.1f}B"


def save(fig, name):
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    png = FIG_DIR / f"{name}.png"
    pdf = FIG_DIR / f"{name}.pdf"

    fig.savefig(
        png,
        dpi=300,
        bbox_inches="tight",
    )

    fig.savefig(
        pdf,
        bbox_inches="tight",
    )

    print("Wrote:", png)
    print("Wrote:", pdf)


# ============================================================
# FIGURE 1
# Temporal water impacts
# ============================================================

def figure1_temporal_water():

    df = pd.read_csv(TEMPORAL_SUMMARY)

    # -----------------------
    # Figure 1A — WF
    # -----------------------

    fig, ax = plt.subplots(figsize=(8.5, 5.5))

    for scenario in SCENARIOS:

        x = (
            df[df["scenario"] == scenario]
            .sort_values("year")
        )

        ax.plot(
            x["year"],
            x["annual_water_footprint_m3"],
            marker="o",
            linewidth=2,
            label=scenario.capitalize(),
        )

    ax.set_title(
        "Projected data-center water footprint, 2023–2030"
    )

    ax.set_xlabel("Year")
    ax.set_ylabel("Annual water footprint (m³)")

    ax.yaxis.set_major_formatter(
        FuncFormatter(billions)
    )

    ax.grid(alpha=0.25)

    ax.legend(
        title="EPRI demand scenario",
        frameon=False,
    )

    fig.text(
        0.5,
        -0.01,
        "Watershed water-intensity coefficients are held constant; "
        "scenario differences reflect electricity-demand growth.",
        ha="center",
        fontsize=9,
    )

    fig.tight_layout()

    save(
        fig,
        "figure1a_temporal_water_footprint",
    )

    plt.close(fig)

    # -----------------------
    # Figure 1B — WSF
    # -----------------------

    fig, ax = plt.subplots(figsize=(8.5, 5.5))

    for scenario in SCENARIOS:

        x = (
            df[df["scenario"] == scenario]
            .sort_values("year")
        )

        ax.plot(
            x["year"],
            x[
                "annual_water_scarcity_footprint_m3_eq"
            ],
            marker="o",
            linewidth=2,
            label=scenario.capitalize(),
        )

    ax.set_title(
        "Projected scarcity-weighted water impact, 2023–2030"
    )

    ax.set_xlabel("Year")

    ax.set_ylabel(
        "Annual water scarcity footprint (m³-eq)"
    )

    ax.yaxis.set_major_formatter(
        FuncFormatter(billions)
    )

    ax.grid(alpha=0.25)

    ax.legend(
        title="EPRI demand scenario",
        frameon=False,
    )

    fig.text(
        0.5,
        -0.01,
        "m³-eq represents scarcity-weighted impact and should not be "
        "interpreted as literal water consumption.",
        ha="center",
        fontsize=9,
    )

    fig.tight_layout()

    save(
        fig,
        "figure1b_temporal_water_scarcity",
    )

    plt.close(fig)


# ============================================================
# FIGURE 2
# Watershed rank changes
# ============================================================

def figure2_rank_shift():

    df = pd.read_csv(
        HUC8_2030,
        dtype={"huc8": "string"},
    )

    x = df[
        df["scenario"] == "moderate"
    ].copy()

    selected = x[
        (x["wf_rank_within_scenario"] <= 10)
        |
        (x["wsf_rank_within_scenario"] <= 10)
    ].copy()

    selected = selected.sort_values(
        "wsf_rank_within_scenario"
    )

    y = list(range(len(selected)))

    fig, ax = plt.subplots(
        figsize=(9, 7)
    )

    for i, (_, row) in enumerate(
        selected.iterrows()
    ):

        ax.plot(
            [
                row["wf_rank_within_scenario"],
                row["wsf_rank_within_scenario"],
            ],
            [i, i],
            linewidth=1.5,
            alpha=0.6,
        )

    ax.scatter(
        selected[
            "wf_rank_within_scenario"
        ],
        y,
        marker="o",
        s=70,
        label="Water footprint rank",
        zorder=3,
    )

    ax.scatter(
        selected[
            "wsf_rank_within_scenario"
        ],
        y,
        marker="s",
        s=70,
        label="Scarcity-weighted rank",
        zorder=3,
    )

    ax.set_yticks(y)

    ax.set_yticklabels(
        selected["huc8"]
    )

    ax.invert_yaxis()
    ax.invert_xaxis()

    ax.set_xlabel(
        "2030 moderate-scenario rank "
        "(1 = highest modeled impact)"
    )

    ax.set_ylabel(
        "HUC8 watershed"
    )

    ax.set_title(
        "Scarcity weighting changes which watersheds rank highest"
    )

    ax.grid(
        axis="x",
        alpha=0.25,
    )

    ax.legend(
        frameon=False,
    )

    fig.tight_layout()

    save(
        fig,
        "figure2_huc8_rank_shift",
    )

    plt.close(fig)


# ============================================================
# FIGURE 3
# Scarcity amplification
# ============================================================

def figure3_scarcity_amplification():

    df = pd.read_csv(
        HUC8_2030,
        dtype={"huc8": "string"},
    )

    x = df[
        df["scenario"] == "moderate"
    ].copy()

    x = x[
        (x["water_footprint_m3"] > 0)
        &
        (
            x[
                "water_scarcity_footprint_m3_eq"
            ] > 0
        )
    ].copy()

    x["scarcity_amplification"] = (
        x[
            "water_scarcity_footprint_m3_eq"
        ]
        /
        x["water_footprint_m3"]
    )

    x["rank_shift"] = (
        x["wf_rank_within_scenario"]
        -
        x["wsf_rank_within_scenario"]
    )

    sizes = (
        25
        +
        5 * x["sites"].clip(upper=40)
    )

    fig, ax = plt.subplots(
        figsize=(9, 6.5)
    )

    ax.scatter(
        x["scarcity_amplification"],
        x["rank_shift"],
        s=sizes,
        alpha=0.55,
    )

    ax.axhline(
        0,
        linewidth=1,
        linestyle="--",
    )

    ax.set_xscale("log")

    ax.set_xlabel(
        "Scarcity amplification (WSF ÷ WF)"
    )

    ax.set_ylabel(
        "Upward rank shift after scarcity weighting\n"
        "(WF rank − WSF rank)"
    )

    ax.set_title(
        "Scarcity weighting elevates moderate-footprint watersheds"
    )

    ax.grid(alpha=0.25)

    important = [
        "10190009",
        "17020015",
        "16020201",
        "16020204",
        "15050100",
        "15010015",
    ]

    for huc in important:

        row = x[
            x["huc8"] == huc
        ]

        if row.empty:
            continue

        row = row.iloc[0]

        ax.annotate(
            huc,
            (
                row[
                    "scarcity_amplification"
                ],
                row["rank_shift"],
            ),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=8,
        )

    fig.tight_layout()

    save(
        fig,
        "figure3_scarcity_amplification",
    )

    plt.close(fig)


# ============================================================
# FIGURE 4
# Suspected duplicate sensitivity
# ============================================================

def figure4_duplicate_sensitivity():

    national = pd.read_csv(
        DUPLICATE_SENSITIVITY
    )

    row = national[
        (national["scenario"] == "moderate")
        &
        (national["year"] == 2030)
    ].iloc[0]

    energy_change = row[
        "projected_energy_mwh_percent_change"
    ]

    wf_change = row[
        "annual_water_footprint_m3_percent_change"
    ]

    wsf_change = row[
        "annual_water_scarcity_footprint_m3_eq_percent_change"
    ]

    sites = pd.read_csv(
        TEMPORAL_SITES,
        dtype={"huc8": "string"},
    )

    local = sites[
        (sites["scenario"] == "moderate")
        &
        (sites["year"] == 2030)
        &
        (
            sites["water_status"]
            == "estimated"
        )
        &
        (
            sites["huc8"]
            == SENSITIVITY_HUC8
        )
    ].copy()

    primary_wf = (
        local[
            "annual_water_footprint_m3"
        ].sum()
    )

    primary_wsf = (
        local[
            "annual_water_scarcity_footprint_m3_eq"
        ].sum()
    )

    filtered = local[
        local["site_id"]
        != SUSPECTED_DUPLICATE
    ]

    sensitivity_wf = (
        filtered[
            "annual_water_footprint_m3"
        ].sum()
    )

    sensitivity_wsf = (
        filtered[
            "annual_water_scarcity_footprint_m3_eq"
        ].sum()
    )

    local_wf_change = (
        100
        *
        (
            primary_wf
            - sensitivity_wf
        )
        /
        primary_wf
    )

    local_wsf_change = (
        100
        *
        (
            primary_wsf
            - sensitivity_wsf
        )
        /
        primary_wsf
    )

    labels = [
        "National\nenergy",
        "National\nWF",
        "National\nWSF",
        "HUC8 15050100\nWF",
        "HUC8 15050100\nWSF",
    ]

    values = [
        energy_change,
        wf_change,
        wsf_change,
        local_wf_change,
        local_wsf_change,
    ]

    fig, ax = plt.subplots(
        figsize=(9, 5.8)
    )

    bars = ax.bar(
        labels,
        values,
    )

    ax.set_ylabel(
        "Reduction after excluding suspected record (%)"
    )

    ax.set_title(
        "Primary watershed rankings are robust to a suspected overlapping IM3 record"
    )

    ax.grid(
        axis="y",
        alpha=0.25,
    )

    for bar, value in zip(
        bars,
        values,
    ):

        ax.text(
            bar.get_x()
            + bar.get_width() / 2,
            bar.get_height(),
            f"{value:.2f}%",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.text(
        0.5,
        -0.18,
        "HUC8 15050100 remained #1 by WF and #3 by WSF after exclusion.",
        transform=ax.transAxes,
        ha="center",
        fontsize=9,
    )

    fig.tight_layout()

    save(
        fig,
        "figure4_duplicate_sensitivity",
    )

    plt.close(fig)


def main():

    print(
        "\nGenerating final water-resource figures...\n"
    )

    figure1_temporal_water()
    figure2_rank_shift()
    figure3_scarcity_amplification()
    figure4_duplicate_sensitivity()

    print(
        "\nFinished."
    )


if __name__ == "__main__":
    main()
