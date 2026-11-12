"""Exercise real-data views and the Dash HTTP callback contract without a browser."""
import json
from pathlib import Path
import re
import warnings

import numpy as np
import pandas as pd

from .app import create_app
from .callbacks import INITIAL, navigate, summary_panel
from .data import OUT, PRE, ROOT, full_watersheds, load_data
from .formatting import METRICS
from .maps import map_figure, temporal_figure


def run():
    warnings.filterwarnings('ignore', message='Mean of empty slice')
    data = load_data()
    assert data.geometry.subbasin_name.notna().all()
    app = create_app(data)
    client = app.server.test_client()
    assert client.get('/').status_code == 200
    assert client.get('/_dash-layout').status_code == 200
    assert client.get('/_dash-dependencies').status_code == 200
    keys = list(app.callback_map)
    navkey = next(k for k in keys if 'selection.data' in k)
    renderkey = next(k for k in keys if 'map.figure' in k)

    def post(key, values, changed, previous=None):
        spec = app.callback_map[key]
        outputs = spec['output']
        payload = {'output': key, 'outputs': [{'id': o.component_id, 'property': o.component_property} for o in outputs],
                   'inputs': [{'id': i['id'], 'property': i['property'], 'value': values[i['id']]} for i in spec['inputs']],
                   'state': [{'id': i['id'], 'property': i['property'], 'value': previous} for i in spec['state']],
                   'changedPropIds': [changed]}
        response = client.post('/_dash-update-component', json=payload)
        assert response.status_code == 200, response.get_data(as_text=True)[:2000]
        return response.get_json()['response']

    def navigate_http(previous, custom=None, control=None, value=None):
        values = {'map': {'points': [{'customdata': custom}]} if custom else None,
                  'state-select': previous['selected_state'], 'huc-select': previous['selected_huc8'],
                  'site-select': previous['selected_site'], 'year': previous['selected_year'],
                  'scenario': previous['selected_scenario'], 'metric': previous['selected_metric'],
                  'lower-filter': ['lower'] if previous.get('lower_only') else [], 'reset': 0, 'back': 0}
        changed = 'map.clickData'
        if control:
            values[control] = value
            changed = control + ('.n_clicks' if control in ['reset', 'back'] else '.value')
        return post(navkey, values, changed, previous)['selection']['data']

    def render_http(selection):
        return post(renderkey, {'selection': selection, 'temporal-metric': 'projected_energy_mwh', 'presentation': []}, 'selection.data')

    national = render_http(INITIAL)
    assert len(national['map']['figure']['data'][0]['locations']) == 56
    states_checked = []
    crossing = []
    for state in ['AZ', 'VA', 'CA', 'TX', 'NY', 'AK']:
        selection = navigate_http(INITIAL, ['state', state])
        response = render_http(selection)
        selected = full_watersheds(data.geometry, data.cross, state)
        assert set(selected.huc8) == data.state_hucs.get(state, set())
        original = data.geometry.set_index('huc8')
        for row in selected.itertuples():
            assert row.geometry.equals_exact(original.loc[row.huc8, 'geometry'], 0)
        if not selected.empty:
            state_poly = data.states.loc[data.states.state_abbr.eq(state)].geometry.union_all()
            crossing.extend((state, row.huc8) for row in selected.itertuples() if row.geometry.difference(state_poly).area > 1e-5)
            expected_sites = data.state_sites[state]
            markers = next(t for t in response['map']['figure']['data'] if t.get('name', '').startswith('Modeled sites'))
            assert {c[1] for c in markers['customdata']} == expected_sites
        states_checked.append(state)
    assert crossing, 'Real-data cross-state behavior must be demonstrated'
    supported = data.huc_lookup[(2030, 'central')].projected_energy_mwh
    cross_state, huc = next((s, h) for s, h in crossing if pd.notna(supported.loc[h]) and supported.loc[h] > 0)
    selection = navigate_http(INITIAL, ['state', cross_state])
    selection = navigate_http(selection, ['huc8', huc])
    response = render_http(selection)
    markers = next(t for t in response['map']['figure']['data'] if t.get('name', '').startswith('Modeled sites'))
    assert {c[1] for c in markers['customdata']} == data.huc_sites[huc]
    site = next(iter(data.huc_sites[huc]))
    selection = navigate_http(selection, ['site', site])
    response = render_http(selection)
    assert site in json.dumps(response['summary'])
    base_pop = data.site_values(2030, 'central', huc8=huc).pop_5km
    selection = navigate_http(selection, control='year', value=2025)
    selection = navigate_http(selection, control='scenario', value='higher_pressure')
    response = render_http(selection)
    assert 'CRPI is validated for 2030 only' in response['map-note']['children']
    assert base_pop.equals(data.site_values(2025, 'higher_pressure', huc8=huc).pop_5km)
    low = data.site_values(2030, 'lower_pressure', huc8=huc).projected_energy_mwh.sum(min_count=1)
    high = data.site_values(2030, 'higher_pressure', huc8=huc).projected_energy_mwh.sum(min_count=1)
    assert high > low
    for metric in METRICS:
        state = {**selection, 'selected_metric': metric, 'selected_year': 2030}
        map_figure(data, state).to_json()
    for metric in ['cumulative_co2_metric_tonnes', 'annual_direct_water_m3', 'median_aqueduct_water_stress', 'median_temperature_mean_c']:
        temporal_figure(data, selection, metric).to_json()
    filtered = navigate_http(selection, control='lower-filter', value=['lower'])
    render_http(filtered)
    back = navigate_http(selection, control='back', value=1)
    assert back['selected_huc8'] is None and back['selected_site'] is None and back['selected_state'] == cross_state
    reset = navigate_http(selection, control='reset', value=1)
    assert all(reset[k] is None for k in ['selected_state', 'selected_huc8', 'selected_site'])
    validation = {'status': 'programmatic checks passed', 'national_states': len(data.states),
        'states_with_sites': int(data.sites.state_abbr.nunique()), 'huc8_count': len(data.geometry),
        'site_records': len(data.sites), 'years': [2023, 2030], 'scenarios': list(data.annual.screening_scenario.unique()),
        'states_checked': states_checked, 'all_map_metrics_checked': list(METRICS),
        'cross_state_examples': crossing[:15], 'full_polygon_equality_verified': True,
        'huc8_click_verified': True, 'site_click_verified': True, 'year_scenario_updates_verified': True,
        'population_static_verified': True, 'back_reset_verified': True,
        'http_callback_tracebacks': 0,
        'manual_browser_validation': 'Not performed: Computer Use access to Chrome was not approved.',
        'screenshots': 'Manual capture instructions in outputs/dashboard/README.md; no synthetic screenshots.'}
    (OUT / 'dashboard/validation.json').write_text(json.dumps(validation, indent=2) + '\n')
    print(json.dumps(validation, indent=2))


def report():
    validation = json.loads((OUT / 'dashboard/validation.json').read_text())
    log = (OUT / 'dashboard/tests.txt').read_text()
    match = re.search(r'(\d+) passed(?:, (\d+) subtests passed)?', log)
    assert match and not re.search(r'\d+ failed|FAILED|ERRORS', log)
    validation['tests'] = {'passed': int(match[1]), 'subtests_passed': int(match[2] or 0), 'failed': 0}
    (OUT / 'dashboard/validation.json').write_text(json.dumps(validation, indent=2) + '\n')
    lines = ['INTERACTIVE DASHBOARD COMPLETE', '', 'Launch:', 'python3 -m src.dashboard.app',
        'Local URL: http://127.0.0.1:8050', '', 'National states:', str(validation['national_states']),
        '', 'States with modeled sites:', str(validation['states_with_sites']), '', 'HUC8 watersheds:', str(validation['huc8_count']),
        '', 'Site records:', str(validation['site_records']), '', 'Years:', '2023–2030', '', 'Scenarios:', *validation['scenarios'],
        '', 'Available map metrics:', *[v[0] for v in METRICS.values()], '', 'Cross-state HUC8 behavior:', 'full polygon retained',
        '', 'Dashboard files:', *[str(p.relative_to(ROOT)) for p in sorted((ROOT / 'src/dashboard').rglob('*')) if p.is_file() and '__pycache__' not in str(p)],
        'data/processed/us_states_2023.gpkg', 'data/processed/us_states_dashboard.geojson',
        'data/processed/huc8_dashboard_geometry.geojson', 'data/processed/state_huc8_dashboard_crosswalk.csv',
        'data/processed/huc8_dashboard_names.csv', 'data/processed/dashboard_site_states.csv', 'data/processed/dashboard_site_states.json',
        'data/processed/dashboard_geometry_metadata.json', 'outputs/dashboard/validation.json',
        'outputs/dashboard/README.md', 'docs/dashboard.md', '', 'Tests:', f'{match[1]} passed',
        f'{match[2] or 0} subtests passed', '0 failed', '',
        'Browser screenshots/manual checks remain unverified: Computer Use access to Chrome was not approved.',
        'No GitHub push. DataCenterSimulation/ unchanged.']
    text = '\n'.join(lines) + '\n'
    (OUT / 'dashboard/completion.txt').write_text(text)
    print(text)


if __name__ == '__main__':
    import sys
    report() if '--report' in sys.argv else run()
