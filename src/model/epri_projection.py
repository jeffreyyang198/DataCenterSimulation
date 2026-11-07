"""Load EPRI state-level data-center demand projections and interpolate annual loads."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_EPRI_FILE = (
    ROOT / "data/raw/epri/EPRI_2024_Projections.xlsx"
)

START_YEAR = 2023
END_YEAR = 2030


STATE_ABBREVIATIONS = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}


SCENARIOS = {
    "low": {
        "load_col": 3,
        "share_col": 4,
        "label_rate": 0.0371,
    },
    "moderate": {
        "load_col": 5,
        "share_col": 6,
        "label_rate": 0.05,
    },
    "high": {
        "load_col": 7,
        "share_col": 8,
        "label_rate": 0.10,
    },
    "higher": {
        "load_col": 9,
        "share_col": 10,
        "label_rate": 0.15,
    },
}


def load_epri_projections(
    path: str | Path = DEFAULT_EPRI_FILE,
) -> pd.DataFrame:
    """Load the EPRI workbook into tidy state/scenario rows.

    The workbook uses two header rows followed by one row per represented
    state. Each output row represents one state under one growth scenario.

    Returns columns including:
        state
        state_abbr
        scenario
        scenario_label_growth_rate
        epri_2023_load_mwh
        epri_2023_state_share
        epri_2030_load_mwh
        epri_2030_state_share
        implied_annual_growth_rate
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"EPRI projection workbook not found: {path}"
        )

    raw = pd.read_excel(
        path,
        sheet_name="Sheet1",
        header=None,
    )

    if raw.shape[1] < 11:
        raise ValueError(
            "EPRI workbook does not contain the expected 11 columns"
        )

    # Rows 0-1 are the workbook's two header rows.
    data = raw.iloc[2:].copy()

    data = data.dropna(
        subset=[0]
    )

    data[0] = (
        data[0]
        .astype(str)
        .str.strip()
    )

    if data[0].duplicated().any():
        raise ValueError(
            "EPRI workbook contains duplicate state rows"
        )

    records = []

    for _, row in data.iterrows():
        state = row[0]

        if state not in STATE_ABBREVIATIONS:
            raise ValueError(
                f"Unknown state name in EPRI workbook: {state}"
            )

        load_2023 = pd.to_numeric(
            row[1],
            errors="coerce",
        )

        share_2023 = pd.to_numeric(
            row[2],
            errors="coerce",
        )

        if pd.isna(load_2023) or load_2023 <= 0:
            raise ValueError(
                f"{state}: invalid 2023 EPRI load"
            )

        for scenario_name, config in SCENARIOS.items():
            load_2030 = pd.to_numeric(
                row[config["load_col"]],
                errors="coerce",
            )

            share_2030 = pd.to_numeric(
                row[config["share_col"]],
                errors="coerce",
            )

            if pd.isna(load_2030) or load_2030 <= 0:
                raise ValueError(
                    f"{state}: invalid 2030 EPRI load "
                    f"for {scenario_name}"
                )

            implied_growth = (
                (load_2030 / load_2023)
                ** (1 / (END_YEAR - START_YEAR))
                - 1
            )

            records.append(
                {
                    "state": state,
                    "state_abbr": STATE_ABBREVIATIONS[state],
                    "scenario": scenario_name,
                    "scenario_label_growth_rate": (
                        config["label_rate"]
                    ),
                    "epri_2023_load_mwh": float(load_2023),
                    "epri_2023_state_share": float(share_2023),
                    "epri_2030_load_mwh": float(load_2030),
                    "epri_2030_state_share": float(share_2030),
                    "implied_annual_growth_rate": float(
                        implied_growth
                    ),
                }
            )

    result = pd.DataFrame(records)

    if result.duplicated(
        subset=["state_abbr", "scenario"]
    ).any():
        raise ValueError(
            "Duplicate state/scenario combinations found"
        )

    return result


def project_epri_annual(
    projections: pd.DataFrame,
    start_year: int = START_YEAR,
    end_year: int = END_YEAR,
) -> pd.DataFrame:
    """Interpolate annual state demand between EPRI endpoints.

    A constant compound annual growth rate is inferred separately for each
    state/scenario from its published 2023 and 2030 loads.

    This guarantees that the first and final simulated years match the EPRI
    workbook endpoints.
    """
    required = {
        "state",
        "state_abbr",
        "scenario",
        "epri_2023_load_mwh",
        "epri_2030_load_mwh",
        "implied_annual_growth_rate",
    }

    if missing := required - set(projections.columns):
        raise ValueError(
            f"Missing EPRI columns: {sorted(missing)}"
        )

    if end_year <= start_year:
        raise ValueError(
            "end_year must be greater than start_year"
        )

    rows = []

    for row in projections.itertuples(
        index=False
    ):
        baseline = float(
            row.epri_2023_load_mwh
        )

        target = float(
            row.epri_2030_load_mwh
        )

        rate = float(
            row.implied_annual_growth_rate
        )

        for year in range(
            start_year,
            end_year + 1,
        ):
            if year == start_year:
                projected = baseline

            elif year == end_year:
                # Preserve the exact published endpoint.
                projected = target

            else:
                years_elapsed = (
                    year - start_year
                )

                projected = (
                    baseline
                    * (1 + rate) ** years_elapsed
                )

            rows.append(
                {
                    "state": row.state,
                    "state_abbr": row.state_abbr,
                    "scenario": row.scenario,
                    "year": year,
                    "projected_epri_load_mwh": projected,
                    "implied_annual_growth_rate": rate,
                }
            )

    result = pd.DataFrame(rows)

    result[
        "cumulative_epri_load_mwh"
    ] = (
        result.groupby(
            [
                "state_abbr",
                "scenario",
            ]
        )["projected_epri_load_mwh"]
        .cumsum()
    )

    return result


def compare_modeled_to_epri(
    modeled_state_baseline: pd.DataFrame,
    epri_projections: pd.DataFrame,
) -> pd.DataFrame:
    """Compare modeled state demand with EPRI's 2023 state benchmark.

    EPRI values remain state-level benchmarks. They are not assigned to
    individual facilities.
    """
    required = {
        "state",
        "baseline_modeled_mwh",
    }

    if missing := required - set(
        modeled_state_baseline.columns
    ):
        raise ValueError(
            f"Missing modeled baseline columns: {sorted(missing)}"
        )

    benchmark = (
        epri_projections[
            [
                "state_abbr",
                "epri_2023_load_mwh",
            ]
        ]
        .drop_duplicates(
            subset="state_abbr"
        )
        .rename(
            columns={
                "state_abbr": "state",
            }
        )
    )

    result = modeled_state_baseline.merge(
        benchmark,
        on="state",
        how="left",
        validate="one_to_one",
    )

    result[
        "modeled_to_epri_ratio"
    ] = (
        result["baseline_modeled_mwh"]
        / result["epri_2023_load_mwh"]
    )

    result[
        "modeled_minus_epri_mwh"
    ] = (
        result["baseline_modeled_mwh"]
        - result["epri_2023_load_mwh"]
    )

    return result