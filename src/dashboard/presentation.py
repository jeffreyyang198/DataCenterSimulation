"""Launch the classroom dashboard using only the prepared local snapshot."""
import argparse
from pathlib import Path
from time import perf_counter

import pandas as pd
from werkzeug.serving import make_server

from .app import create_app
from .data import MEDIAN_FIELDS, OUT, PAIRS, PRE, ROOT, SUM_FIELDS, load_data

YEARS = set(range(2023, 2031))
CSV_COLUMNS = {
    PRE / 'master_sites_with_huc8.csv': 'site_id site_name site_type operator state_abbr state_fips huc8 longitude latitude'.split(),
    PRE / 'dashboard_site_states.csv': [
        *SUM_FIELDS, *MEDIAN_FIELDS, 'site_id', 'huc8', 'year', 'screening_scenario', 'state_abbr', 'longitude', 'latitude',
        *(f'{prefix}pop_{radius}km' for radius in (1, 3, 5) for prefix in ('', 'incomplete_')),
    ],
    PRE / 'state_huc8_dashboard_crosswalk.csv': 'state_abbr state_fips huc8 modeled_site_count_in_state'.split(),
    PRE / 'stateful_unique_population_5km.csv': 'group_type group_id unique_population_within_5km missing_tract_population'.split(),
    OUT / 'huc8_dynamic_profiles_2023_2030.csv': [
        *SUM_FIELDS, *MEDIAN_FIELDS.values(), 'huc8', 'year', 'screening_scenario', 'site_count',
        'max_aqueduct_water_stress', 'unique_population_within_5km',
    ],
    OUT / 'huc8_dashboard_data.csv': 'huc8 cluster_id cluster_label hotspot_category scenario_robust'.split(),
    OUT / 'huc8_lower_pressure_candidates.csv': ['huc8'],
    OUT / 'huc8_crpi_scenario_sensitivity_2030.csv': 'huc8 screening_scenario crpi_equal'.split(),
}
OTHER_FILES = [
    PRE / 'dashboard_site_states.json', PRE / 'us_states_dashboard.geojson', PRE / 'huc8_dashboard_geometry.geojson',
]
BACKUPS = [
    OUT / 'animations/data_center_resource_pressure_2023_2030.mp4',
    OUT / 'animations/powerpoint_poster_frame.png',
]


def validate_files():
    issues = []
    for path in [*CSV_COLUMNS, *OTHER_FILES]:
        label = path.relative_to(ROOT)
        try:
            with path.open('rb') as stream:
                if not stream.read(1):
                    raise ValueError('file is empty')
            if path in CSV_COLUMNS:
                missing = set(CSV_COLUMNS[path]) - set(pd.read_csv(path, nrows=0).columns)
                if missing:
                    issues.append(f'{label} is missing columns {", ".join(sorted(missing))}')
        except (OSError, ValueError) as error:
            issues.append(f'{label} — {error.strerror if isinstance(error, OSError) else error}')
    if issues:
        raise ValueError('\n'.join(issues))


def preflight(*, backups=False):
    validate_files()
    data = load_data(presentation=True)
    state_ids, huc_ids, sites = set(data.states.state_abbr), set(data.geometry.huc8), set(data.sites.site_id)
    for geometry, identifier, name in [
        (data.states, 'state_abbr', 'state_name'), (data.geometry, 'huc8', 'subbasin_name'),
    ]:
        if (geometry.empty or not geometry[identifier].is_unique or geometry[[identifier, name]].isna().any().any()
                or geometry.geometry.isna().any() or geometry.geometry.is_empty.any()
                or not geometry.geometry.geom_type.isin(['Polygon', 'MultiPolygon']).all()
                or geometry.crs is None or geometry.crs.to_epsg() != 4326):
            raise ValueError(f'Invalid identifiers or EPSG:4326 polygons in dashboard {identifier} geometry')
    if (not data.states.state_abbr.str.fullmatch(r'[A-Z]{2}').all()
            or not data.geometry.huc8.str.fullmatch(r'\d{8}').all()):
        raise ValueError('Invalid state or HUC8 codes in dashboard geometry')
    if (data.sites.site_id.isna().any() or not data.sites.site_id.is_unique
            or not set(data.sites.state_abbr) <= state_ids or not set(data.sites.huc8.dropna()) <= huc_ids
            or not set(data.cross.state_abbr) <= state_ids or not set(data.cross.huc8) <= huc_ids
            or set(data.context.huc8) != huc_ids or not data.context.huc8.is_unique
            or not data.lower_ids <= huc_ids or not data.population_lookup.index.is_unique):
        raise ValueError('Dashboard geographic identifiers are missing, duplicated, or inconsistent')
    expected_pairs = {(year, scenario) for year in YEARS for scenario in PAIRS}
    for name, lookup, expected_ids in [
        ('Site snapshot', data.annual_lookup, sites), ('Watershed profiles', data.huc_lookup, huc_ids),
    ]:
        if set(lookup) != expected_pairs or any(not frame.index.is_unique or set(frame.index) != expected_ids
                                                for frame in lookup.values()):
            raise ValueError(f'{name} needs complete 2023–2030 coverage for lower, central and higher scenarios')
    for frame in (data.sites, data.annual):
        if not (frame.longitude.between(-180, 180) & frame.latitude.between(-90, 90)).all():
            raise ValueError('Site longitude/latitude is missing or out of range')
    keys = data.crpi.set_index(['screening_scenario', 'huc8']).index
    if not keys.is_unique or set(keys) != {(scenario, huc) for scenario in PAIRS for huc in huc_ids}:
        raise ValueError('CRPI table needs one 2030 row per watershed and scenario')
    if len(data.demo_examples) < 3:
        raise ValueError('At least three supported watershed examples are required')
    if backups:
        for path, magic, offset in [(BACKUPS[0], b'ftyp', 4), (BACKUPS[1], b'\x89PNG\r\n\x1a\n', 0)]:
            with path.open('rb') as stream:
                stream.seek(offset)
                if stream.read(len(magic)) != magic:
                    raise ValueError(f'Invalid backup file {path.relative_to(ROOT)}')
    return data


def summary(data):
    return (f'Sites loaded: {len(data.sites):,}\nHUC8 watersheds: {len(data.geometry)}\n'
            f'States and equivalents: {len(data.states)}\nYears: 2023–2030\n'
            'Scenarios: lower, central, higher\nNetwork required: NO (local browser connection only)\n'
            'Demo examples:\n' + '\n'.join(f'  {state} / {huc} · {label}'
                                               for huc, (state, label) in data.demo_examples.items()))


def failure(error):
    message = str(error) or 'A saved data integrity check failed.'
    print(f'PRESENTATION PREFLIGHT FAILED\n\n{message}\n\n'
          'See the Live Presentation Dashboard section in README.md for recovery.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8050)
    args = parser.parse_args()
    start = perf_counter()
    try:
        data = preflight()
        app = create_app(data, presentation=True)
    except (OSError, ValueError, AssertionError, KeyError) as error:
        failure(error)
        return 1
    try:
        # The local WSGI server runs directly without Dash's debug runner or reloader.
        server = make_server('127.0.0.1', args.port, app.server, threaded=True)
    except SystemExit:
        print(f'Could not bind 127.0.0.1:{args.port}. Stop the other local server or pass --port 8051.', flush=True)
        return 1
    with server:
        print('=' * 52 + '\nDATA CENTER RESOURCE PRESSURE DASHBOARD\nPRESENTATION MODE READY\n' + '=' * 52,
              f'\n\nURL: http://127.0.0.1:{server.server_port}\n\n{summary(data)}\n\n'
              f'Startup: {perf_counter() - start:.2f} s\n'
              'Press Ctrl+C after the presentation to stop the server.', sep='', flush=True)
        server.serve_forever()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
