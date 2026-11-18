"""Flag potentially overlapping or duplicate modeled IM3 site records.

This module is diagnostic only. It does not remove, merge, or alter sites.
"""

from __future__ import annotations

from itertools import combinations
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
import re

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

INPUT = (
    ROOT
    / "data/processed/energy_scenarios/floor_area_1.0/low_ai_inference.csv"
)

PAIR_OUTPUT = ROOT / "outputs/site_record_overlap_candidates.csv"
CLUSTER_OUTPUT = ROOT / "outputs/site_record_overlap_clusters.csv"

ENERGY_COLUMN = "estimated_annual_facility_energy_mwh"


def normalize_text(value) -> str:
    """Normalize site/operator text for conservative candidate matching."""
    if pd.isna(value):
        return ""

    text = str(value).lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance between two WGS84 points."""
    earth_radius_km = 6371.0088

    lat1 = radians(float(lat1))
    lon1 = radians(float(lon1))
    lat2 = radians(float(lat2))
    lon2 = radians(float(lon2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )

    return 2 * earth_radius_km * asin(sqrt(a))


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)

        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])

        return self.parent[x]

    def union(self, a, b):
        ra = self.find(a)
        rb = self.find(b)

        if ra != rb:
            self.parent[rb] = ra


def candidate_reason(a, b, distance_km: float) -> str | None:
    """Return a conservative diagnostic reason, or None."""

    same_name = (
        bool(a["normalized_site_name"])
        and a["normalized_site_name"] == b["normalized_site_name"]
    )

    same_operator = (
        bool(a["normalized_operator"])
        and a["normalized_operator"] == b["normalized_operator"]
    )

    # Nearly identical coordinates are worth reviewing regardless of name.
    if distance_km <= 0.01:
        return "near_identical_coordinates"

    # Same-named records within 1 km may represent duplicated records,
    # separate campus buildings, or multiple structures with the same label.
    if same_name and distance_km <= 1.0:
        return "same_name_within_1km"

    # Same operator extremely close together is another conservative flag.
    if same_operator and distance_km <= 0.10:
        return "same_operator_within_100m"

    return None


def main() -> None:
    df = pd.read_csv(INPUT)

    required = {
        "site_id",
        "state_abbr",
        "latitude",
        "longitude",
        ENERGY_COLUMN,
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    modeled = df.loc[df[ENERGY_COLUMN].notna()].copy()

    modeled["normalized_site_name"] = (
        modeled.get("site_name", pd.Series(index=modeled.index, dtype=object))
        .map(normalize_text)
    )

    modeled["normalized_operator"] = (
        modeled.get("operator", pd.Series(index=modeled.index, dtype=object))
        .map(normalize_text)
    )

    modeled["latitude"] = pd.to_numeric(
        modeled["latitude"], errors="coerce"
    )
    modeled["longitude"] = pd.to_numeric(
        modeled["longitude"], errors="coerce"
    )

    modeled = modeled.loc[
        modeled["latitude"].notna()
        & modeled["longitude"].notna()
    ].copy()

    pairs = []
    union = UnionFind()

    for state, group in modeled.groupby("state_abbr", dropna=False):
        records = group.to_dict("records")

        for a, b in combinations(records, 2):
            distance = haversine_km(
                a["latitude"],
                a["longitude"],
                b["latitude"],
                b["longitude"],
            )

            reason = candidate_reason(a, b, distance)

            if reason is None:
                continue

            union.union(a["site_id"], b["site_id"])

            pairs.append(
                {
                    "site_id_a": a["site_id"],
                    "site_id_b": b["site_id"],
                    "state_abbr": state,
                    "distance_m": distance * 1000,
                    "reason": reason,
                    "site_name_a": a.get("site_name"),
                    "site_name_b": b.get("site_name"),
                    "operator_a": a.get("operator"),
                    "operator_b": b.get("operator"),
                    "site_type_a": a.get("site_type"),
                    "site_type_b": b.get("site_type"),
                    "square_feet_a": a.get("square_feet"),
                    "square_feet_b": b.get("square_feet"),
                    "energy_mwh_a": a.get(ENERGY_COLUMN),
                    "energy_mwh_b": b.get(ENERGY_COLUMN),
                }
            )

    pair_df = pd.DataFrame(pairs)

    # Build connected candidate clusters.
    candidate_ids = set()

    if not pair_df.empty:
        candidate_ids.update(pair_df["site_id_a"])
        candidate_ids.update(pair_df["site_id_b"])

    clustered = modeled.loc[
        modeled["site_id"].isin(candidate_ids)
    ].copy()

    if not clustered.empty:
        clustered["cluster_root"] = clustered["site_id"].map(union.find)

        roots = {
            root: i + 1
            for i, root in enumerate(
                sorted(clustered["cluster_root"].unique())
            )
        }

        clustered["candidate_cluster_id"] = (
            clustered["cluster_root"]
            .map(roots)
            .map(lambda x: f"cluster_{x:04d}")
        )

        cluster_summary = (
            clustered.groupby(
                "candidate_cluster_id",
                as_index=False,
            )
            .agg(
                records=("site_id", "size"),
                state_abbr=("state_abbr", "first"),
                site_names=(
                    "site_name",
                    lambda x: " | ".join(
                        sorted(
                            {
                                str(v)
                                for v in x.dropna()
                            }
                        )
                    ),
                ),
                operators=(
                    "operator",
                    lambda x: " | ".join(
                        sorted(
                            {
                                str(v)
                                for v in x.dropna()
                            }
                        )
                    ),
                ),
                total_square_feet=("square_feet", "sum"),
                total_energy_mwh=(ENERGY_COLUMN, "sum"),
                max_single_record_energy_mwh=(
                    ENERGY_COLUMN,
                    "max",
                ),
            )
            .sort_values(
                ["total_energy_mwh", "records"],
                ascending=[False, False],
            )
        )
    else:
        cluster_summary = pd.DataFrame()

    PAIR_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    pair_df.to_csv(PAIR_OUTPUT, index=False)
    cluster_summary.to_csv(CLUSTER_OUTPUT, index=False)

    print("=== MODELED RECORD AUDIT ===")
    print("Modeled records:", len(modeled))
    print("Candidate pairs:", len(pair_df))
    print("Candidate clusters:", len(cluster_summary))

    if not pair_df.empty:
        print("\nCandidate reasons:")
        print(pair_df["reason"].value_counts().to_string())

    duplicate_source_ids = 0
    if "source_site_id" in modeled.columns:
        duplicate_source_ids = int(
            modeled["source_site_id"]
            .dropna()
            .duplicated(keep=False)
            .sum()
        )

    print("\nRows sharing source_site_id:", duplicate_source_ids)

    if not cluster_summary.empty:
        print("\n=== TOP 20 CANDIDATE CLUSTERS BY MODELED ENERGY ===")
        print(
            cluster_summary.head(20).to_string(index=False)
        )

        candidate_energy = clustered[ENERGY_COLUMN].sum()
        total_energy = modeled[ENERGY_COLUMN].sum()

        print(
            "\nEnergy represented inside candidate clusters:",
            f"{candidate_energy:,.0f} MWh",
        )

        print(
            "Share of modeled baseline energy:",
            f"{100 * candidate_energy / total_energy:.2f}%",
        )

    print("\nDiagnostic only — no records were removed or merged.")
    print("Wrote:", PAIR_OUTPUT)
    print("Wrote:", CLUSTER_OUTPUT)


if __name__ == "__main__":
    main()
