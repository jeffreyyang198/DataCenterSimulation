"""One-time loading, keyed lookups and reproducible display-only preparation.

State navigation is determined by site assignment. No intersection/clip is used.
"""
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import struct
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PRE = ROOT / 'data/processed'
OUT = ROOT / 'outputs'
PAIRS = {'lower_pressure': ('low', 'optimistic'), 'central': ('moderate', 'business_as_usual'),
         'higher_pressure': ('higher', 'pessimistic')}
SUM_FIELDS = ['projected_energy_mwh', 'annual_co2_metric_tonnes', 'cumulative_co2_metric_tonnes',
              'annual_direct_water_m3', 'cumulative_direct_water_m3',
              'annual_water_footprint_m3', 'annual_water_scarcity_footprint_m3_eq']
MEDIAN_FIELDS = {'aqueduct_water_stress': 'median_aqueduct_water_stress',
                 'aqueduct_water_depletion': 'median_aqueduct_water_depletion',
                 'temperature_mean_c': 'median_temperature_mean_c',
                 'warmest_day_mean_c': 'median_warmest_day_mean_c'}


def huc_ids(series):
    return pd.to_numeric(series, errors='coerce').astype('Int64').astype('string').str.zfill(8)


def crosswalk(sites, states):
    """Site-based navigation relation; no polygon majority or spatial clipping."""
    counts = (sites.dropna(subset=['huc8', 'state_abbr']).groupby(['state_abbr', 'huc8'])
              .size().rename('modeled_site_count_in_state').reset_index())
    return counts.merge(states[['state_abbr', 'state_fips']], on='state_abbr', validate='many_to_one')


def full_watersheds(geometry, cross, state_abbr, lower_ids=None):
    ids = set(cross.loc[cross.state_abbr.eq(state_abbr), 'huc8'])
    if lower_ids is not None:
        ids &= set(lower_ids)
    # Row selection only. Geometry objects are returned whole, unchanged.
    return geometry.loc[geometry.huc8.isin(ids)].copy()


def site_filter(sites, state=None, huc8=None):
    if huc8:
        return sites.loc[sites.huc8.eq(huc8)].copy()
    return sites.loc[sites.state_abbr.eq(state)].copy() if state else sites.copy()


def source_names():
    """Read text attributes from the source DBF without loading geometry."""
    path = ROOT / 'data/raw/siddik/SI_Shapefile.dbf'
    encoding = path.with_suffix('.cpg').read_text().strip() if path.with_suffix('.cpg').exists() else 'latin1'
    with path.open('rb') as stream:
        header = stream.read(32)
        count = struct.unpack('<I', header[4:8])[0]
        header_length, record_length = struct.unpack('<HH', header[8:12])
        fields, offset = {}, 1
        for _ in range((header_length - 33) // 32):
            descriptor = stream.read(32)
            name, width = descriptor[:11].split(b'\0')[0].decode('ascii'), descriptor[16]
            fields[name] = (offset, width)
            offset += width
        stream.seek(header_length)
        rows = []
        for _ in range(count):
            record = stream.read(record_length)
            if record[:1] == b'*':
                continue
            values = {}
            for source, target in [('HUC_8', 'huc8'), ('SUBBASIN', 'subbasin_name')]:
                start, width = fields[source]
                values[target] = record[start:start + width].decode(encoding).strip()
            rows.append(values)
    names = pd.DataFrame(rows)
    assert names.huc8.is_unique and names.huc8.str.fullmatch(r'\d{8}').all()
    return names


def prepare():
    """Generate small web assets without touching scientific source geometries."""
    archive = ROOT / 'data/raw/census/state_boundaries_2023/cb_2023_us_state_500k.zip'
    states = gpd.read_file(archive).rename(columns={'STATEFP': 'state_fips', 'STUSPS': 'state_abbr', 'NAME': 'state_name'})
    states = states[['state_fips', 'state_abbr', 'state_name', 'geometry']].to_crs(4326)
    state_target = PRE / 'us_states_2023.gpkg'
    # Deterministic display products can be regenerated; raw archive is preserved.
    states.to_file(state_target, driver='GPKG', layer='states')
    web = states.to_crs(5070)
    web.geometry = web.geometry.simplify(1200, preserve_topology=True).make_valid()
    web = web.to_crs(4326)
    web.to_file(PRE / 'us_states_dashboard.geojson', driver='GeoJSON')
    hucs = gpd.read_file(PRE / 'huc8_analysis_boundaries.gpkg').to_crs(4326)
    hucs.huc8 = huc_ids(hucs.huc8)
    names = source_names()
    names.to_csv(PRE / 'huc8_dashboard_names.csv', index=False)
    hucs = hucs.merge(names, on='huc8', how='left', validate='one_to_one')
    assert hucs.subbasin_name.notna().all()
    assert hucs.huc8.is_unique and hucs.geometry.is_valid.all() and not hucs.geometry.is_empty.any()
    hucs[['huc8', 'subbasin_name', 'geometry']].to_file(PRE / 'huc8_dashboard_geometry.geojson', driver='GeoJSON')
    sites = pd.read_csv(PRE / 'master_sites_with_huc8.csv', dtype={'state_fips': str})
    sites.huc8 = huc_ids(sites.huc8)
    cross = crosswalk(sites, states)
    cross.to_csv(PRE / 'state_huc8_dashboard_crosswalk.csv', index=False)
    metadata = {
        'state_source': str(archive.relative_to(ROOT)),
        'state_source_url': 'https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip',
        'state_source_crs': 'EPSG:4269', 'display_crs': 'EPSG:4326', 'state_display_simplification_m': 1200,
        'huc8_source': 'data/raw/siddik/SI_Shapefile.shp',
        'huc8_name_source': 'data/raw/siddik/SI_Shapefile.dbf:SUBBASIN',
        'huc8_display_parent': 'data/processed/huc8_analysis_boundaries.gpkg',
        'huc8_display_simplification_m': 500, 'huc8_additional_simplification': False,
        'full_watersheds_retained': True, 'navigation_relation': 'site state assignment → HUC8',
        'state_count': len(states), 'huc8_count': len(hucs), 'valid_huc8_geometries': int(hucs.geometry.is_valid.sum()),
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [archive, PRE / 'huc8_analysis_boundaries.gpkg', PRE / 'master_sites_with_huc8.csv', ROOT / 'data/raw/siddik/SI_Shapefile.dbf']},
    }
    (PRE / 'dashboard_geometry_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata, indent=2))


@dataclass
class DashboardData:
    sites: pd.DataFrame
    annual: pd.DataFrame
    profiles: pd.DataFrame
    context: pd.DataFrame
    states: gpd.GeoDataFrame
    geometry: gpd.GeoDataFrame
    cross: pd.DataFrame
    lower_ids: set
    population: pd.DataFrame

    def __post_init__(self):
        self.annual_lookup = {(int(y), s): g.set_index('site_id', drop=False) for (y, s), g in self.annual.groupby(['year', 'screening_scenario'])}
        self.huc_lookup = {(int(y), s): g.set_index('huc8', drop=False) for (y, s), g in self.profiles.groupby(['year', 'screening_scenario'])}
        self.state_hucs = {s: set(g.huc8) for s, g in self.cross.groupby('state_abbr')}
        self.huc_sites = {h: set(g.site_id) for h, g in self.sites.dropna(subset=['huc8']).groupby('huc8')}
        self.state_sites = {s: set(g.site_id) for s, g in self.sites.groupby('state_abbr')}
        self.state_geojson = json.loads(self.states.to_json(drop_id=True))
        self.huc_geojson = {f['properties']['huc8']: f for f in json.loads(self.geometry.to_json(drop_id=True))['features']}
        self.state_counts = self.sites.groupby('state_abbr').size()
        self.context_lookup = self.context.set_index('huc8')
        self.population_lookup = self.population.set_index(['group_type', 'group_id'])
        self.aggregate_lookup = {}
        for (year, scenario), frame in self.annual_lookup.items():
            for state in self.states.state_abbr:
                ids = self.state_sites.get(state, set())
                self.aggregate_lookup[(state, year, scenario)] = aggregate(frame.loc[frame.index.isin(ids)])
            self.aggregate_lookup[(None, year, scenario)] = aggregate(frame)

    def site_values(self, year, scenario, state=None, huc8=None):
        frame = self.annual_lookup[(int(year), scenario)]
        if huc8:
            return frame.loc[frame.index.isin(self.huc_sites.get(huc8, set()))]
        if state:
            return frame.loc[frame.index.isin(self.state_sites.get(state, set()))]
        return frame

    def watershed_values(self, year, scenario):
        frame = self.huc_lookup[(int(year), scenario)].copy()
        cols = ['cluster_id', 'cluster_label', 'hotspot_category', 'scenario_robust']
        frame = frame.join(self.context_lookup[cols])
        frame['crpi_equal'] = np.nan
        if int(year) == 2030:
            scores = self.crpi.loc[self.crpi.screening_scenario.eq(scenario)].set_index('huc8')
            frame['crpi_equal'] = scores.crpi_equal
        return frame

    def proximity(self, huc8=None, national=False):
        key = ('huc8', huc8) if huc8 else (('national', 'all') if national else None)
        if key is None or key not in self.population_lookup.index:
            return np.nan, 'Unique state-level proximity population is unavailable; overlapping site populations are not summed.'
        row = self.population_lookup.loc[key]
        if bool(row.missing_tract_population):
            return np.nan, 'Incomplete tract population coverage.'
        return row.unique_population_within_5km, 'Static ACS 2023 proximity within dissolved 5-km site buffers; not exposure.'


def aggregate(frame):
    values = {c: frame[c].sum(min_count=1) for c in SUM_FIELDS}
    values.update({target: frame[source].median() for source, target in MEDIAN_FIELDS.items()})
    values['site_count'] = len(frame)
    values['max_aqueduct_water_stress'] = frame.aqueduct_water_stress.max()
    values['energy_modeled_sites'] = int(frame.projected_energy_mwh.notna().sum())
    values['co2_modeled_sites'] = int(frame.annual_co2_metric_tonnes.notna().sum())
    values['water_modeled_sites'] = int(frame.annual_water_scarcity_footprint_m3_eq.notna().sum())
    return values


def read_annual_states(source, cache, cache_meta):
    """Allow a fresh clone to use the verified compact artifact without the large CSV."""
    metadata = json.loads(cache_meta.read_text()) if cache_meta.exists() else {}
    source_exists = source.exists()
    source_matches = not source_exists or (
        metadata.get('size') == source.stat().st_size and metadata.get('mtime_ns') == source.stat().st_mtime_ns)
    cache_valid = (cache.exists() and metadata.get('schema_version') == 2 and
                   hashlib.sha256(cache.read_bytes()).hexdigest() == metadata.get('cache_sha256'))
    if cache_valid and source_matches:
        return pd.read_csv(cache, dtype={'huc8': str}, low_memory=False)
    if not source_exists:
        raise FileNotFoundError('The large simulation CSV is absent and the compact dashboard dataset is missing or failed checksum validation. Regenerate the stateful simulation and dashboard dataset.')
    signature = {'source': 'outputs/stateful_community_resource_simulation_2023_2030.csv',
                 'size': source.stat().st_size, 'mtime_ns': source.stat().st_mtime_ns, 'schema_version': 2}
    if source_exists:
        columns = set(SUM_FIELDS + list(MEDIAN_FIELDS) + ['site_id', 'state_abbr', 'huc8', 'year',
            'longitude', 'latitude', 'epri_scenario', 'aqueduct_scenario', 'nasa_scenario',
            'pop_1km', 'pop_3km', 'pop_5km', 'incomplete_pop_1km', 'incomplete_pop_3km', 'incomplete_pop_5km'])
        annual = pd.read_csv(source, usecols=lambda c: c in columns, low_memory=False)
        annual.huc8 = huc_ids(annual.huc8)
        annual['screening_scenario'] = pd.NA
        for label, (epri, aq) in PAIRS.items():
            annual.loc[annual.epri_scenario.eq(epri) & annual.aqueduct_scenario.eq(aq), 'screening_scenario'] = label
        annual = annual.loc[annual.screening_scenario.notna()].copy()
        annual.to_csv(cache, index=False)
        signature['cache_sha256'] = hashlib.sha256(cache.read_bytes()).hexdigest()
        cache_meta.write_text(json.dumps(signature, indent=2) + '\n')
    return annual


@lru_cache(maxsize=1)
def load_data():
    if not (PRE / 'huc8_dashboard_geometry.geojson').exists():
        prepare()
    sites = pd.read_csv(PRE / 'master_sites_with_huc8.csv', dtype={'state_fips': str})
    sites.huc8 = huc_ids(sites.huc8)
    annual = read_annual_states(OUT / 'stateful_community_resource_simulation_2023_2030.csv',
                                PRE / 'dashboard_site_states.csv', PRE / 'dashboard_site_states.json')
    assert not annual.duplicated(['site_id', 'year', 'screening_scenario']).any()
    assert len(annual) == len(sites) * 8 * 3
    profiles = pd.read_csv(OUT / 'huc8_dynamic_profiles_2023_2030.csv', dtype={'huc8': str})
    context = pd.read_csv(OUT / 'huc8_dashboard_data.csv', dtype={'huc8': str})
    data = DashboardData(sites, annual, profiles, context,
                         gpd.read_file(PRE / 'us_states_dashboard.geojson'),
                         gpd.read_file(PRE / 'huc8_dashboard_geometry.geojson'),
                         pd.read_csv(PRE / 'state_huc8_dashboard_crosswalk.csv', dtype={'huc8': str, 'state_fips': str}),
                         set(pd.read_csv(OUT / 'huc8_lower_pressure_candidates.csv', dtype={'huc8': str}).huc8),
                         pd.read_csv(PRE / 'stateful_unique_population_5km.csv', dtype={'group_id': str}))
    data.crpi = pd.read_csv(OUT / 'huc8_crpi_scenario_sensitivity_2030.csv', dtype={'huc8': str})
    assert set(data.context.huc8) == set(data.geometry.huc8)
    return data


if __name__ == '__main__':
    prepare()
