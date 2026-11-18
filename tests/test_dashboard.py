"""Dashboard scientific/navigation logic; no tests of Dash/Plotly internals."""
from types import SimpleNamespace
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from src.dashboard.callbacks import INITIAL, navigate
from src.dashboard.data import (DashboardData, MEDIAN_FIELDS, SUM_FIELDS, aggregate,
                                crosswalk, full_watersheds, huc_ids, site_filter)
from src.dashboard.formatting import effective_metric, number


@pytest.fixture
def sample():
    sites = pd.DataFrame({'site_id': ['a', 'b', 'c'], 'state_abbr': ['AZ', 'NV', 'AZ'],
                          'huc8': ['15010001', '15010001', '15010002']})
    states = gpd.GeoDataFrame({'state_abbr': ['AZ', 'NV'], 'state_fips': ['04', '32']},
                              geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs=4326)
    geometry = gpd.GeoDataFrame({'huc8': ['15010001', '15010002']},
                                geometry=[box(.5, .2, 1.5, .8), box(.1, .1, .3, .3)], crs=4326)
    cross = crosswalk(sites, states)
    return SimpleNamespace(sites=sites, states=states, geometry=geometry, cross=cross,
                           state_hucs={s: set(g.huc8) for s, g in cross.groupby('state_abbr')})


def test_state_crosswalk_uses_assigned_sites(sample):
    assert len(sample.cross) == 3
    assert sample.cross.loc[sample.cross.state_abbr.eq('NV'), 'huc8'].tolist() == ['15010001']
    assert sample.cross.modeled_site_count_in_state.sum() == 3
    assert set(sample.cross.state_fips) == {'04', '32'}


def test_state_selection_keeps_full_cross_state_watershed(sample):
    original = sample.geometry.set_index('huc8').loc['15010001', 'geometry']
    selected = full_watersheds(sample.geometry, sample.cross, 'AZ')
    retained = selected.set_index('huc8').loc['15010001', 'geometry']
    assert retained.equals_exact(original, 0)
    assert retained.area == original.area
    assert retained.difference(sample.states.iloc[0].geometry).area > 0
    assert len(selected) == 2


def test_unrelated_watersheds_hidden_and_filter_is_row_selection(sample):
    selected = full_watersheds(sample.geometry, sample.cross, 'NV')
    assert selected.huc8.tolist() == ['15010001']
    lower = full_watersheds(sample.geometry, sample.cross, 'AZ', {'15010002'})
    assert lower.huc8.tolist() == ['15010002']
    assert len(sample.geometry) == 2


def test_state_sites_and_full_watershed_sites(sample):
    assert set(site_filter(sample.sites, state='AZ').site_id) == {'a', 'c'}
    assert set(site_filter(sample.sites, state='AZ', huc8='15010001').site_id) == {'a', 'b'}


def test_new_state_clears_lower_levels_preserves_controls(sample):
    prior = {**INITIAL, 'selected_state': 'AZ', 'selected_huc8': '15010001', 'selected_site': 'a', 'selected_year': 2027}
    result = navigate(prior, 'state', 'NV', sample)
    assert result['selected_state'] == 'NV'
    assert result['selected_huc8'] is None and result['selected_site'] is None
    assert result['selected_year'] == 2027 and prior['selected_site'] == 'a'


def test_huc_change_clears_site_and_rejects_unrelated_huc(sample):
    state = {**INITIAL, 'selected_state': 'NV', 'selected_site': 'b'}
    changed = navigate(state, 'huc8', '15010001', sample)
    assert changed['selected_huc8'] == '15010001' and changed['selected_site'] is None
    assert navigate(changed, 'huc8', '15010002', sample) == changed


def test_cross_state_site_allowed_only_within_selected_huc(sample):
    prior = {**INITIAL, 'selected_state': 'AZ', 'selected_huc8': '15010001'}
    result = navigate(prior, 'site', 'b', sample)
    assert result['selected_site'] == 'b' and result['selected_state'] == 'AZ'
    assert navigate({**INITIAL, 'selected_state': 'AZ'}, 'site', 'b', sample)['selected_site'] is None


def test_back_and_reset(sample):
    prior = {**INITIAL, 'selected_state': 'AZ', 'selected_huc8': '15010001', 'selected_site': 'a'}
    back = navigate(prior, 'back', None, sample)
    assert back['selected_state'] == 'AZ' and back['selected_huc8'] is None and back['selected_site'] is None
    reset = navigate(prior, 'reset', None, sample)
    assert all(reset[k] is None for k in ['selected_state', 'selected_huc8', 'selected_site'])


def test_year_and_scenario_lookup_are_exact():
    data = object.__new__(DashboardData)
    data.state_sites = {'AZ': {'a'}}
    data.huc_sites = {'15010001': {'a', 'b'}}
    data.annual_lookup = {}
    for year in [2023, 2030]:
        for scenario, multiplier in [('central', 1), ('higher_pressure', 2)]:
            data.annual_lookup[(year, scenario)] = pd.DataFrame({'site_id': ['a', 'b'], 'energy': [year * multiplier, 9], 'population': [123, 456]}).set_index('site_id', drop=False)
    assert data.site_values(2023, 'central', state='AZ').energy.tolist() == [2023]
    assert data.site_values(2030, 'higher_pressure', state='AZ').energy.tolist() == [4060]
    assert len(data.site_values(2030, 'central', state='AZ', huc8='15010001')) == 2
    assert data.site_values(2023, 'central').population.equals(data.site_values(2030, 'higher_pressure').population)


def test_no_fabricated_annual_crpi_and_metric_validation():
    assert effective_metric('crpi_equal', 2030) == 'crpi_equal'
    assert effective_metric('crpi_equal', 2025) == 'annual_water_scarcity_footprint_m3_eq'
    assert effective_metric('projected_energy_mwh', 2025) == 'projected_energy_mwh'
    with pytest.raises(ValueError):
        effective_metric('human_health_risk', 2030)


def test_missing_and_open_ended_formatting():
    for missing in [None, np.nan, pd.NA, np.inf]:
        assert number(missing) == 'Not available'
    assert number(0, 'm³') == '0 m³'
    assert number(268e6, 'MWh') == '268.00 TWh'
    assert number(9999, 'ratio') == '≥100 (open-ended)'
    assert number(1428.6, 'ratio') == 'Censored / open-ended context'


def test_aggregation_preserves_unknowns_and_never_sums_population():
    frame = pd.DataFrame({c: [np.nan, np.nan] for c in SUM_FIELDS + list(MEDIAN_FIELDS)})
    frame['pop_5km'] = [100, 100]
    values = aggregate(frame)
    assert np.isnan(values['projected_energy_mwh'])
    assert not any('pop' in k for k in values)
    assert values['site_count'] == 2


def test_unique_population_requires_validated_group():
    data = object.__new__(DashboardData)
    data.population_lookup = pd.DataFrame({'group_type': ['national', 'huc8'], 'group_id': ['all', '15010001'],
        'unique_population_within_5km': [100, 75], 'missing_tract_population': [False, True]}).set_index(['group_type', 'group_id'])
    value, note = data.proximity()
    assert np.isnan(value) and 'not summed' in note
    assert data.proximity(national=True)[0] == 100
    assert np.isnan(data.proximity('15010001')[0])


def test_huc_codes_keep_leading_zeroes_and_unknowns():
    values = huc_ids(pd.Series([1060001.0, '02030105', np.nan]))
    assert values.iloc[0] == '01060001' and values.iloc[1] == '02030105' and pd.isna(values.iloc[2])


def test_fresh_clone_uses_verified_compact_dataset_without_large_source(tmp_path):
    import hashlib
    import json
    from src.dashboard.data import read_annual_states
    cache = tmp_path / 'dashboard.csv'
    cache.write_text('site_id,huc8,year,screening_scenario\na,01060001,2030,central\n')
    metadata = tmp_path / 'dashboard.json'
    metadata.write_text(json.dumps({'schema_version': 2, 'cache_sha256': hashlib.sha256(cache.read_bytes()).hexdigest()}))
    frame = read_annual_states(tmp_path / 'absent.csv', cache, metadata)
    assert frame.huc8.tolist() == ['01060001']
    cache.write_text(cache.read_text().replace('2030', '2023'))
    with pytest.raises(FileNotFoundError, match='checksum'):
        read_annual_states(tmp_path / 'absent.csv', cache, metadata)
