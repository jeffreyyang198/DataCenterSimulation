# Dashboard screenshots and manual verification

Launch from the repository root in the existing environment:

```bash
source /Users/yeritmaryrodriguezdelgado/.venvs/data-center-impact/bin/activate
python3 -m src.dashboard.app
```

Open <http://127.0.0.1:8050>. Use a desktop window at least 1440 pixels wide. Screenshots are **pending manual capture**: browser access was not approved during implementation. No browser automation package was installed.

Use macOS Shift–Command–4 to capture the dashboard area and save/move the resulting PNG into this directory with the following names. The Plotly camera button exports the map alone if preferred; use an OS screenshot to include controls and summary panels.

- `national_overview.png`: reset to U.S., central scenario, 2030, all states visible in the initial viewport. Confirm colored states and four national summary cards load.
- `state_example.png`: click Virginia or select it in the state selector. Confirm the dark state outline, associated whole HUC8 polygons and only Virginia-assigned site markers. Repeat Arizona, California, Texas and New York; no unrelated HUC8 should appear. Choose an example from `validation.json` → `cross_state_examples` to inspect the portion extending beyond the selected state.
- `huc8_example.png`: click a watershed polygon, then click a site. Confirm the orange whole-watershed outline, watershed/site details, site state label and updated watershed trajectory. Cross-state sites in the selected watershed should remain visible.
- `hotspot_example.png`: return to the state, choose Hotspot trajectory map mode, 2030, central scenario. Confirm saved trajectory categories, readable legend and complete watershed outlines.

Manual acceptance checklist:

1. Click states, a HUC8 and a site directly on the map; verify selector values and breadcrumb follow the same hierarchy.
2. Change the year to 2025 and scenario to Higher pressure; confirm annual values, markers, temperature context, map colors and chart indicator update.
3. With CRPI selected in 2025, confirm the notice explicitly says WSF is shown because CRPI is available only in 2030. Return to 2030 for CRPI scores.
4. Switch temporal metrics, including cumulative CO₂, direct water, WSF, Aqueduct stress and NASA temperature. Confirm one unit per chart and gaps at censored/missing values.
5. Confirm population remains unchanged across years/scenarios. Unique state-level population must remain unavailable rather than a sum of site populations.
6. Confirm the NASA background-climate and Aqueduct interpolation notes remain visible in the footer.
7. Use Back to state, select another state and Reset to U.S.; confirm stale HUC8/site selections clear.
8. Check the lower-pressure filter and Presentation Mode toggle. Summary totals retain the full geography while the filter changes displayed HUC8s/sites.
9. Confirm no traceback in the serving terminal during these interactions. Record manual results here after capture; do not relabel programmatic checks as manual checks.

Automated results: `validation.json`, `programmatic_checks.txt`, `tests.txt` and `completion.txt`.
