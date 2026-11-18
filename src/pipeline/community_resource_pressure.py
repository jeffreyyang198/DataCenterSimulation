"""Rebuild population and combine independent water/community context sources.

Run with: .venv/bin/python -m src.pipeline.community_resource_pressure
Raw sources and earlier population outputs are preserved.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from pyproj import CRS, Transformer
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'data/raw'
PROCESSED = ROOT / 'data/processed'
OUT = ROOT / 'outputs/community_resource_pressure'


def validate_tracts(frame, path):
    if not re.fullmatch(r'tl_2023_\d{2}_tract', Path(path).stem):
        raise ValueError('Expected TIGER 2023 TRACT geometry')
    required = {'GEOID', 'STATEFP', 'COUNTYFP', 'TRACTCE', 'geometry'}
    if not required.issubset(frame.columns) or frame.crs is None:
        raise ValueError('Missing tract identifiers, geometry, or CRS')
    if not frame.GEOID.astype(str).str.fullmatch(r'\d{11}').all():
        raise ValueError('Invalid tract GEOID')
    if frame.GEOID.duplicated().any():
        raise ValueError('Duplicate tract GEOID')
    if not (frame.GEOID == frame.STATEFP + frame.COUNTYFP + frame.TRACTCE).all():
        raise ValueError('GEOID does not match tract components')
    if frame.geometry.isna().any() or frame.geometry.is_empty.any():
        raise ValueError('Missing tract geometry')
    if not frame.geom_type.isin(['Polygon', 'MultiPolygon']).all():
        raise ValueError('Expected polygons')


def site_buffers(sites, radius_km):
    """Local azimuthal-equidistant circles, returned in global equal-area CRS."""
    shapes = []
    for row in sites.itertuples():
        local = CRS.from_proj4(f'+proj=aeqd +lat_0={row.latitude} +lon_0={row.longitude} +datum=WGS84 +units=m')
        forward = Transformer.from_crs(4326, local, always_xy=True).transform
        reverse = Transformer.from_crs(local, 6933, always_xy=True).transform
        from shapely.geometry import Point
        point = transform(forward, Point(row.longitude, row.latitude))
        shapes.append(transform(reverse, point.buffer(radius_km * 1000, quad_segs=64)))
    return gpd.GeoDataFrame({'site_id': sites.site_id.to_numpy()}, geometry=shapes, crs=6933)


def estimate_population(buffers, tracts):
    """Uniform total-tract-area allocation; missing coverage stays flagged."""
    if buffers.crs != tracts.crs or not tracts.crs.is_projected:
        raise ValueError('Buffers and tracts must share a projected equal-area CRS')
    rows = []
    for row in buffers.itertuples():
        indices = tracts.sindex.query(row.geometry, predicate='intersects')
        candidates = tracts.iloc[indices]
        area = candidates.geometry.intersection(row.geometry).area
        positive = area > 0
        candidates, area = candidates.loc[positive], area.loc[positive]
        values = candidates.population * (area / candidates.geometry.area).clip(0, 1)
        coverage = float(area.sum() / row.geometry.area)
        rows.append(dict(site_id=row.site_id,
            population=values.sum(min_count=1), intersecting_tracts=len(candidates),
            coverage_fraction=min(coverage, 1.0),
            incomplete=bool(coverage < 0.999 or candidates.population.isna().any())))
    return pd.DataFrame(rows)


def normalize_future(frame):
    if frame.pfaf_id.isna().any() or frame.pfaf_id.duplicated().any():
        raise ValueError('Future Aqueduct requires unique nonmissing pfaf_id')
    parts = []
    for code, name in [('opt', 'optimistic'), ('bau', 'bau'), ('pes', 'pessimistic')]:
        columns = [c for c in frame if c.startswith(code + '30_')]
        if not columns or f'{code}30_ws_x_r' not in columns:
            raise ValueError('Missing 2030 scenario columns: ' + code)
        part = frame[['pfaf_id'] + columns].copy()
        part = part.rename(columns={c: c[len(code+'30_'):] for c in columns})
        part['aqueduct_scenario'] = name
        part['aqueduct_year'] = 2030
        for column in part:
            if column.endswith(('_r', '_s', '_c')):
                values = pd.to_numeric(part[column], errors='raise')
                # Negative raw/score/category values are source special codes,
                # including arid/low-use (-1); retain them alongside usable data.
                part[column + '_source_value'] = values
                part[column] = values.where(values >= 0)
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def assign_basins(sites, basins):
    """Assign one Aqueduct PFAF per site, retaining ambiguous candidates."""
    if basins.crs is None or 'pfaf_id' not in basins:
        raise ValueError('Aqueduct polygons require CRS and pfaf_id')
    points = gpd.GeoDataFrame(sites[['site_id']].copy(),
        geometry=gpd.points_from_xy(sites.longitude, sites.latitude), crs=4326).to_crs(basins.crs)
    matches = gpd.sjoin(points, basins[['pfaf_id', 'geometry']], how='left', predicate='intersects')
    rows = []
    for site_id, group in matches.groupby('site_id', sort=False):
        keys = sorted(set(group.pfaf_id.dropna().astype(str)))
        rows.append(dict(site_id=site_id, pfaf_id=keys[0] if len(keys)==1 else pd.NA,
            aqueduct_assignment_status='assigned' if len(keys)==1 else 'ambiguous' if keys else 'unmatched',
            pfaf_id_candidates=';'.join(keys)))
    return pd.DataFrame(rows)


def build_population(sites):
    target = PROCESSED / 'tracts_acs2023.gpkg'
    buffers = {radius: site_buffers(sites, radius) for radius in (1, 3, 5)}
    if target.exists():
        tracts = gpd.read_file(target)
    else:
        search = buffers[5].to_crs(4326)
        selected, inventory = [], []
        for path in sorted((RAW/'census/tiger2023').rglob('*.shp')):
            frame = gpd.read_file(path)
            validate_tracts(frame, path)
            inventory.append(dict(path=str(path.resolve()), tracts=len(frame), crs=str(frame.crs)))
            geographic = frame.to_crs(4326)
            pairs = geographic.sindex.query(search.geometry, predicate='intersects')
            indices = np.unique(pairs[1])
            if len(indices):
                subset = frame.iloc[indices][['GEOID', 'geometry']].to_crs(6933)
                invalid = ~subset.geometry.is_valid
                subset.loc[invalid, 'geometry'] = subset.loc[invalid].geometry.make_valid()
                selected.append(subset)
            print(f'TRACT {path.stem}: {len(frame)} valid identifiers; {len(indices)} nearby', flush=True)
        if not selected:
            raise ValueError('No source tracts intersect the site buffers')
        tracts = gpd.GeoDataFrame(pd.concat(selected, ignore_index=True), crs=6933)
        acs = pd.read_csv(RAW/'census/acs2023/acs2023_tract_population.csv', dtype={'GEOID':str})
        tracts = tracts.merge(acs[['GEOID','population']], on='GEOID', how='left', validate='one_to_one')
        tracts['tract_area_m2'] = tracts.geometry.area
        tracts['geometry_vintage'] = 2023
        tracts['acs_vintage'] = 2023
        tracts.to_file(target, layer='tracts_acs2023', driver='GPKG')
        (RAW/'census/tiger2023/source_metadata.json').write_text(json.dumps(dict(
            geography='TRACT', vintage=2023, inventory=inventory,
            processed_scope='Full tracts intersecting at least one 5-km site buffer',
            selection='All supplied state/territory tract files searched, including neighboring states',
            processed_crs='EPSG:6933', distance='Local AEQD per site'), indent=2)+'\n')
    exposure = sites[['site_id','longitude','latitude']].copy()
    summaries = []
    for radius, circles in buffers.items():
        result = estimate_population(circles, tracts).rename(columns={
            'population':f'pop_{radius}km', 'intersecting_tracts':f'tracts_within_{radius}km',
            'coverage_fraction':f'coverage_fraction_{radius}km', 'incomplete':f'incomplete_pop_{radius}km'})
        exposure = exposure.merge(result, on='site_id', validate='one_to_one')
        dissolved = circles.geometry.union_all()
        area = tracts.geometry.intersection(dissolved).area
        unique = (tracts.population * (area/tracts.geometry.area).clip(0,1)).sum(min_count=1)
        summaries.append(dict(radius_km=radius, unique_nearby_population=unique,
            incomplete_sites=int(result[f'incomplete_pop_{radius}km'].sum())))
    exposure.to_csv(PROCESSED/'community_exposure_acs2023.csv', index=False)
    pd.DataFrame(summaries).to_csv(OUT/'population_summary.csv', index=False)
    old = pd.read_csv(PROCESSED/'community_exposure.csv', dtype={'site_id':str})
    comparison = exposure.merge(old[['site_id','pop_1km','pop_3km','pop_5km']],
        on='site_id', how='outer', suffixes=('_rebuilt','_existing'), validate='one_to_one', indicator=True)
    for radius in (1,3,5):
        a,b = comparison[f'pop_{radius}km_rebuilt'],comparison[f'pop_{radius}km_existing']
        comparison[f'difference_{radius}km'] = a-b
        comparison[f'percent_difference_{radius}km'] = (a-b)/b.where(b!=0)*100
    comparison.to_csv(OUT/'population_comparison.csv', index=False)
    return exposure, comparison


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sites = pd.read_csv(PROCESSED/'master_sites.csv', dtype={'site_id':str})
    if sites.site_id.isna().any() or sites.site_id.duplicated().any():
        raise ValueError('Site master requires unique nonmissing site_id')
    if not (sites.longitude.between(-180,180) & sites.latitude.between(-90,90)).all():
        raise ValueError('Invalid site coordinates')
    exposure, comparison = build_population(sites)
    future_path = RAW/'aqueduct/Aqueduct40_future_annual_y2023m07d05.csv'
    future = normalize_future(pd.read_csv(future_path, dtype={'pfaf_id':str}))
    future.to_csv(PROCESSED/'aqueduct2030_normalized.csv', index=False)
    gdb = RAW/'aqueduct/GDB/Aq40_Y2023D07M05.gdb'
    layers = []
    for layer, geometry_type in pyogrio.list_layers(gdb):
        info = pyogrio.read_info(gdb, layer=layer)
        layers.append(dict(layer=layer, geometry_type=geometry_type, features=info['features'],
                           has_pfaf_id='pfaf_id' in info['fields']))
    candidates = [x for x in layers if x['has_pfaf_id'] and x['geometry_type'] and 'Polygon' in x['geometry_type']]
    preferred = [x for x in candidates if 'future' in x['layer'].lower()]
    if not preferred:
        preferred = [x for x in candidates if 'monthly' in x['layer'].lower()]
    if not preferred:
        preferred = candidates
    if not preferred:
        raise ValueError('No Aqueduct polygon geometry with pfaf_id')
    layer = preferred[0]['layer']
    basins = gpd.read_file(gdb, layer=layer, columns=['pfaf_id'])
    basins['pfaf_id'] = pd.to_numeric(basins.pfaf_id, errors='raise').astype('Int64').astype('string')
    mapping = assign_basins(sites, basins)
    mapping.to_csv(PROCESSED/'site_aqueduct_basins.csv', index=False)
    (RAW/'aqueduct/source_metadata.json').write_text(json.dumps(dict(
        version='4.0', source_package='Aqueduct40_waterrisk_download_Y2023M07D05',
        source_url='https://www.wri.org/data/aqueduct-global-maps-40-data',
        dictionary='https://github.com/wri/Aqueduct40/blob/master/data_dictionary_water-risk-atlas.md',
        inspected_layers=layers, selected_layer=layer, basin_key='pfaf_id',
        scenarios={'optimistic':'SSP1 RCP2.6','bau':'SSP3 RCP7.0','pessimistic':'SSP5 RCP8.5'},
        milestone=2030, climate_period='2015-2045',
        missing_codes='Negative numeric values retained as *_source_value; usable values are null',
        manifest='../source_copy_manifest.json'), indent=2)+'\n')
    from src.analysis.epri_temporal_water import main as rebuild_water
    rebuild_water()
    water = pd.read_csv(ROOT/'outputs/temporal_water_2023_2030.csv', dtype={'site_id':str,'huc8':str})
    water = water.loc[water.year==2030].rename(columns={'scenario':'epri_scenario'})
    combined = water.merge(exposure, on='site_id', validate='many_to_one', suffixes=('','_population'))
    combined = combined.merge(mapping, on='site_id', validate='many_to_one')
    # Cross every EPRI scenario with every independent Aqueduct pathway.
    combined = combined.merge(pd.DataFrame({'aqueduct_scenario':['optimistic','bau','pessimistic']}), how='cross')
    combined = combined.merge(future, on=['pfaf_id','aqueduct_scenario'], how='left', validate='many_to_one')
    combined['aqueduct_risk_available'] = combined.ws_x_s.notna()
    combined['high_water_stress'] = pd.Series(pd.NA,index=combined.index,dtype='boolean')
    valid = combined.ws_x_c.notna()
    combined.loc[valid,'high_water_stress'] = combined.loc[valid,'ws_x_c'] >= 3
    complete = ~combined.incomplete_pop_5km & (combined.pop_5km>0)
    combined['water_m3_per_10000_nearby_residents'] = (
        combined.annual_water_footprint_m3/combined.pop_5km*10000).where(complete)
    combined.to_csv(OUT/'community_resource_pressure_2030.csv', index=False)
    summary = combined.groupby(['epri_scenario','aqueduct_scenario'],as_index=False).agg(
        site_records=('site_id','size'), matched_basins=('pfaf_id','count'),
        usable_water_stress=('ws_x_s','count'), high_stress_site_records=('high_water_stress','sum'),
        modeled_water_m3=('annual_water_footprint_m3',lambda x:x.sum(min_count=1)))
    summary.to_csv(OUT/'scenario_summary.csv', index=False)
    make_figures(comparison, combined)
    (OUT/'run_metadata.json').write_text(json.dumps(dict(
        completed_utc=datetime.now(timezone.utc).isoformat(), sites=len(sites), output_rows=len(combined),
        assignment_counts=mapping.aqueduct_assignment_status.value_counts().to_dict(),
        energy_scenario='low_ai_inference; floor_area_multiplier=1.0',
        population_method='Uniform population density over total tract polygon area; local AEQD circles; EPSG:6933 intersections',
        interpretation='Screening context only; population buffers overlap. No shared water-supply or health-exposure claim. Siddik scarcity footprint is not multiplied by Aqueduct scores.',
        inputs=['data/raw/source_copy_manifest.json','data/raw/census/acs2023/source_metadata.json',
                'data/raw/census/tiger2023/source_metadata.json','data/raw/aqueduct/source_metadata.json']
    ), indent=2)+'\n')
    from src.pipeline.complete_community_scenarios import main as complete_scenarios
    complete_scenarios()
    print('Community-resource-pressure outputs:', OUT, flush=True)


def make_figures(comparison, combined):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1,3,figsize=(12,4))
    for radius, ax in zip((1,3,5), axes):
        ax.scatter(comparison[f'pop_{radius}km_existing'], comparison[f'pop_{radius}km_rebuilt'],s=5,alpha=.4)
        ax.set(xlabel='Existing population estimate',ylabel='ACS 2023 rebuilt estimate',title=f'{radius} km')
    fig.tight_layout(); fig.savefig(OUT/'population_comparison.png',dpi=200); plt.close(fig)
    sample = combined.loc[(combined.epri_scenario=='moderate') & (combined.aqueduct_scenario=='bau')]
    fig, ax = plt.subplots(figsize=(8,5))
    usable = sample.loc[sample.ws_x_s.notna() & ~sample.incomplete_pop_5km]
    dots = ax.scatter(usable.pop_5km, usable.annual_water_footprint_m3,
        c=usable.ws_x_s,vmin=0,vmax=5,cmap='YlOrRd',s=12,alpha=.6)
    ax.set(xlabel='Estimated population within 5 km (ACS 2023)',ylabel='Modeled annual water footprint (m³)',
        title='2030 moderate EPRI demand / Aqueduct BAU water-stress context')
    ax.set_xscale('symlog',linthresh=1); ax.set_yscale('symlog',linthresh=1)
    fig.colorbar(dots,ax=ax,label='Aqueduct water-stress score (0–5)')
    fig.text(.5,.01,'Site records may overlap; proximity does not establish shared water supply.',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.03,1,1)); fig.savefig(OUT/'community_pressure_context.png',dpi=200); plt.close(fig)


if __name__ == '__main__':
    main()
