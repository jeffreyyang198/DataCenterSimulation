"""Build reproducible 2023–2030 stateful screening artifacts; no animation."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import shutil

import geopandas as gpd
import numpy as np
import pandas as pd

from src.model.stateful_community import (
    YEARS,EPRI_SCENARIOS,STATE_KEYS,build_states,aqueduct_annual_context,require_unique,
    DIRECT_WATER_M3_PER_MWH,LB_TO_METRIC_TONNES,PRESENTATION_PAIRS,
)
from src.model.epri_projection import load_epri_projections,project_epri_annual
from src.impact.temporal_emissions import prepare_state_growth_factors
from src.pipeline.community_resource_pressure import site_buffers

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs'
PRE=ROOT/'data/processed'
RAW=ROOT/'data/raw'
STEM='stateful_community_resource'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def locate_nasa(supplied=None):
    candidates=[]
    for folder in (ROOT/'data',OUT):
        for path in folder.rglob('*.csv'):
            if path.name.startswith(('stateful_','simulation_animation')):continue
            if not any(token in path.name.lower() for token in ('nasa','climate','processed_data')):continue
            with path.open() as stream:header=stream.readline()
            if all(name in header.split(',') for name in ['site_id','year','temperature_mean_c','warmest_day_mean_c']):
                candidates.append(path)
    if candidates:
        if len({digest(path) for path in candidates})!=1:
            raise ValueError(f'Multiple distinct NASA climate inputs: {candidates}')
        return sorted(candidates)[0]
    if supplied is None or not Path(supplied).is_file():
        raise FileNotFoundError('No site-level NASA climate CSV found in project; supply --nasa-source')
    target=RAW/'nasa'/Path(supplied).name
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and digest(target)!=digest(supplied):
        raise ValueError('Conflicting existing NASA raw source')
    if not target.exists():shutil.copy2(supplied,target)
    (target.parent/'source_metadata.json').write_text(json.dumps(dict(
        source=str(Path(supplied).resolve()),project_copy=str(target.relative_to(ROOT)),
        sha256=digest(target),source_kind='User-supplied processed NASA site climate table',
        scenario='SSP2-4.5',n_models=1,
        note='No finalized climate CSV was found in the project before this supplied copy was preserved.'
    ),indent=2)+'\n')
    return target


def unique_population(sites,water,basins):
    """Dissolve site circles within each site-assignment group; never sum buffers."""
    inputs=[PRE/'tracts_acs2023.gpkg',PRE/'master_sites.csv',PRE/'master_sites_with_huc8.csv',PRE/'site_aqueduct_basins.csv']
    signature={str(p.relative_to(ROOT)):digest(p) for p in inputs}
    path=PRE/'stateful_unique_population_5km.csv'
    meta=path.with_suffix('.json')
    if path.exists() and meta.exists() and json.loads(meta.read_text())['inputs']==signature:
        return pd.read_csv(path,dtype={'group_id':str})
    circles=site_buffers(sites,5).merge(water[['site_id','huc8']],on='site_id',how='left',validate='one_to_one')
    circles=circles.merge(basins[['site_id','pfaf_id']],on='site_id',how='left',validate='one_to_one')
    tracts=gpd.read_file(PRE/'tracts_acs2023.gpkg').to_crs(circles.crs)
    rows=[]
    def calculate(group):
        shape=group.geometry.union_all()
        selected=tracts.iloc[tracts.sindex.query(shape,predicate='intersects')]
        area=selected.geometry.intersection(shape).area
        fraction=(area/selected.geometry.area).clip(0,1)
        value=(selected.population*fraction).sum(min_count=1)
        return float(value),bool((selected.population.isna()&(area>0)).any())
    value,missing=calculate(circles)
    rows.append(dict(group_type='national',group_id='all',unique_population_within_5km=value,missing_tract_population=missing))
    for field in ['huc8','pfaf_id']:
        for key,group in circles.dropna(subset=[field]).groupby(field,sort=True):
            value,missing=calculate(group)
            rows.append(dict(group_type=field,group_id=key,unique_population_within_5km=value,missing_tract_population=missing))
        print('Dissolved population complete:',field,flush=True)
    result=pd.DataFrame(rows)
    result.to_csv(path,index=False)
    meta.write_text(json.dumps(dict(inputs=signature,
        method='Local AEQD 5-km circles; union within each group; EPSG:6933 full-tract area weighting',
        interpretation='People near sites assigned to each group; buffers not clipped to watershed boundaries. Group populations overlap and are not additive.'
    ),indent=2)+'\n')
    return result


SUM_COLUMNS=['projected_energy_mwh']+[f'{kind}_{p}_metric_tonnes'
    for p in ('co2','co2e','nox','so2') for kind in ('annual','cumulative')]+[
    'annual_direct_water_m3','cumulative_direct_water_m3',
    'annual_water_footprint_m3','annual_water_scarcity_footprint_m3_eq']


def summarize(states,keys):
    grouped=states.groupby(keys,dropna=False,sort=True)
    sums=grouped[SUM_COLUMNS].sum(min_count=1)
    medians=grouped[['aqueduct_water_stress','aqueduct_water_depletion','temperature_mean_c','warmest_day_mean_c']].median()
    medians=medians.rename(columns={c:'median_'+c for c in medians})
    counts=grouped.agg(site_count=('site_id','nunique'),modeled_sites=('projected_energy_mwh','count'),
        water_modeled_sites=('annual_water_footprint_m3','count'),co2_modeled_sites=('annual_co2_metric_tonnes','count'))
    return sums.join(medians).join(counts).reset_index()


def validate(states,climate,national,population_context):
    require_unique(states,STATE_KEYS+['year'],'simulation')
    assert len(states)==states.site_id.nunique()*8*4*3
    assert set(states.year)==set(YEARS)
    for col in ['pop_1km','pop_3km','pop_5km']:
        assert states.groupby('site_id')[col].nunique(dropna=False).le(1).all()
    assert states.n_models.eq(1).all() and states.nasa_scenario.eq('SSP2-4.5').all()
    assert states.groupby(['site_id','year']).temperature_mean_c.nunique(dropna=False).eq(1).all()
    assert climate.groupby('site_id').temperature_mean_c.nunique().gt(1).any()
    assert climate.groupby('year').temperature_mean_c.nunique().gt(1).all()
    assert 'dc_adjusted_water_stress_ratio' not in states
    np.testing.assert_allclose(states.projected_energy_mwh,
        states.estimated_annual_facility_energy_mwh*states.epri_growth_factor,equal_nan=True,rtol=1e-12)
    # Check state transitions against relative annual growth as well as baseline factors.
    grouped=states.groupby(STATE_KEYS,sort=False)
    expected=grouped.projected_energy_mwh.shift(1)*(states.epri_growth_factor/grouped.epri_growth_factor.shift(1))
    later=states.year.gt(2023)
    np.testing.assert_allclose(states.loc[later,'projected_energy_mwh'],expected[later],equal_nan=True,rtol=1e-12)
    for p in ('co2','co2e','nox','so2'):
        annual=f'annual_{p}_metric_tonnes';cumulative=f'cumulative_{p}_metric_tonnes'
        np.testing.assert_allclose(states[annual],states.projected_energy_mwh*states[f'{p}_lb_per_mwh']*LB_TO_METRIC_TONNES,equal_nan=True)
        previous=grouped[cumulative].shift(1)
        target=previous+states[annual]
        target=target.where(states.year.ne(2023),states[annual])
        np.testing.assert_allclose(states[cumulative],target,equal_nan=True,rtol=1e-12,atol=1e-8)
        assert grouped[cumulative].diff().dropna().ge(-1e-7).all()
    np.testing.assert_allclose(states.annual_direct_water_m3,states.projected_energy_mwh*DIRECT_WATER_M3_PER_MWH,equal_nan=True)
    previous=grouped.cumulative_direct_water_m3.shift(1)
    target=(previous+states.annual_direct_water_m3).where(states.year.ne(2023),states.annual_direct_water_m3)
    np.testing.assert_allclose(states.cumulative_direct_water_m3,target,equal_nan=True,rtol=1e-12,atol=1e-7)
    assert grouped.cumulative_direct_water_m3.diff().dropna().ge(-1e-7).all()
    for col,coefficient in [('annual_water_footprint_m3','WF_1MW_DC'),('annual_water_scarcity_footprint_m3_eq','WSF_1MW_DC')]:
        np.testing.assert_allclose(states[col],states.projected_energy_mwh*states[coefficient],equal_nan=True)
    for name in ('water_stress','water_depletion'):
        col='aqueduct_'+name
        both=states[[col+'_baseline',col+'_2030']].notna().all(axis=1)
        lo=states[[col+'_baseline',col+'_2030']].min(axis=1)
        hi=states[[col+'_baseline',col+'_2030']].max(axis=1)
        assert ((states.loc[both,col]>=lo[both]-1e-10)&(states.loc[both,col]<=hi[both]+1e-10)).all()
    assert states.huc8.dropna().astype(str).str.fullmatch(r'\d{8}').all()
    assert states.pfaf_id.dropna().astype(str).str.fullmatch(r'\d{6}').all()
    expected_population=population_context.loc[population_context.group_type.eq('national'),'unique_population_within_5km'].iloc[0]
    assert national.unique_population_within_5km.eq(expected_population).all()
    unknown=states.projected_energy_mwh.isna()
    assert states.loc[unknown,['annual_direct_water_m3','annual_co2_metric_tonnes']].isna().all().all()
    central=states[states.presentation_scenario.eq('central_2030_screening')]
    require_unique(central,['site_id','year'],'central scenario')
    return dict(status='passed',site_records=states.site_id.nunique(),site_year_scenario_rows=len(states),
        central_site_year_rows=len(central),checks=[
            'unique keys and years','strict cumulative state transitions','EPRI compounding equivalence',
            'annual eGRID emissions','verified direct-water coefficient','annual Siddik WF/WSF',
            'static population','external single-model climate and join uniqueness',
            'bounded Aqueduct interpolation','no incompatible ratio','distinct HUC8/PFAF identifiers',
            'missing values preserved','dissolved national population'])


def build_artifacts(nasa_source=None, *, baseline_pue=False):
    climate_path=locate_nasa(nasa_source)
    print('NASA source:',climate_path.resolve(),flush=True)
    climate=pd.read_csv(climate_path,dtype={'site_id':str})
    sites_path=(PRE/'energy_scenarios/floor_area_1.0/low_ai_inference.csv' if baseline_pue
                else PRE/'data_centers_with_energy_climate.csv')
    if not sites_path.is_file():
        raise FileNotFoundError(f'Missing energy input {sites_path}. See the Climate-adjusted PUE scenario in README.md.')
    sites=pd.read_csv(sites_path,dtype={'site_id':str})
    if not baseline_pue:
        expected={'power_density_scenario':'low','workload_scenario':'ai_inference','floor_area_multiplier':1.0}
        if any(column not in sites or not sites[column].eq(value).all() for column,value in expected.items()):
            raise ValueError('Climate energy input must use low density, AI inference, and a 1.0 floor-area multiplier')
        if 'pue_source' not in sites or not sites.pue_source.isin(['climate_fitted','scenario_fallback']).all():
            raise ValueError('Climate energy input must identify fitted and fallback PUE values')
    water=pd.read_csv(PRE/'master_sites_with_huc8.csv',dtype={'site_id':str,'huc8':str})
    population=pd.read_csv(PRE/'community_exposure_acs2023.csv',dtype={'site_id':str})
    basins=pd.read_csv(PRE/'site_aqueduct_basins.csv',dtype={'site_id':str,'pfaf_id':str})
    factors=pd.read_csv(PRE/'emissions/egrid2023_factors.csv')
    mapping=pd.read_csv(PRE/'emissions/site_egrid_mapping.csv',dtype={'site_id':str})
    growth=prepare_state_growth_factors(project_epri_annual(load_epri_projections()))
    ids=set(basins.pfaf_id.dropna())
    baseline_path=RAW/'aqueduct/Aqueduct40_baseline_annual_y2023m07d05.csv'
    future_path=RAW/'aqueduct/Aqueduct40_future_annual_y2023m07d05.csv'
    baseline=pd.read_csv(baseline_path,usecols=['pfaf_id','bws_raw','bwd_raw'],dtype={'pfaf_id':str})
    future=pd.read_csv(future_path,usecols=lambda c:c=='pfaf_id' or any(c==f'{s}30_{v}_x_r' for s in ('opt','bau','pes') for v in ('ws','wd','ba','ww')),dtype={'pfaf_id':str})
    aq=aqueduct_annual_context(baseline[baseline.pfaf_id.isin(ids)],future[future.pfaf_id.isin(ids)])
    aq.to_csv(PRE/'aqueduct_annual_screening_2023_2030.csv',index=False)
    states=build_states(sites,growth,factors,mapping,water,population,basins,climate,aq)
    pop=unique_population(sites,water,basins)
    national=summarize(states,['year','epri_scenario','aqueduct_scenario'])
    national=national.rename(columns={'projected_energy_mwh':'total_projected_energy_mwh'})
    national['unique_population_within_5km']=pop.loc[pop.group_type.eq('national'),'unique_population_within_5km'].iloc[0]
    national['population_incomplete_site_buffers_5km']=int(population.incomplete_pop_5km.sum())
    national['presentation_scenario']=[
        PRESENTATION_PAIRS.get((a,b),'sensitivity_grid')
        for a,b in zip(national.epri_scenario,national.aqueduct_scenario)]
    report=validate(states,climate,national,pop)
    national.to_csv(OUT/f'{STEM}_summary_2023_2030.csv',index=False)
    for field,name in [('huc8','huc8'),('pfaf_id','aqueduct')]:
        subset=states[states[field].notna()]
        grouped=summarize(subset,[field,'year','epri_scenario','aqueduct_scenario'])
        if field=='huc8':
            maximum=subset.groupby([field,'year','epri_scenario','aqueduct_scenario']).aqueduct_water_stress.max().rename('max_aqueduct_water_stress').reset_index()
            grouped=grouped.merge(maximum,on=[field,'year','epri_scenario','aqueduct_scenario'],validate='one_to_one')
        else:
            columns=['aqueduct_available_blue_water','aqueduct_background_water_demand','aqueduct_water_stress','aqueduct_water_depletion']
            # These are basin conditions, never sums across sites.
            conditions=subset.groupby([field,'year','epri_scenario','aqueduct_scenario'])[columns].first().reset_index()
            grouped=grouped.merge(conditions,on=[field,'year','epri_scenario','aqueduct_scenario'],validate='one_to_one')
            grouped['aqueduct_supply_demand_unit']='cm/year'
        context=pop[pop.group_type.eq(field)][['group_id','unique_population_within_5km']].rename(columns={'group_id':field})
        grouped=grouped.merge(context,on=field,how='left',validate='many_to_one')
        grouped['population_scope']='dissolved proximity buffers of sites assigned to group;nonadditive across groups'
        grouped.to_csv(OUT/f'stateful_{name}_resource_simulation_2023_2030.csv',index=False)
    states.to_csv(OUT/f'{STEM}_simulation_2023_2030.csv',index=False)
    frames=national[national.presentation_scenario.eq('central_2030_screening')].rename(columns={'total_projected_energy_mwh':'projected_energy_mwh'})
    frames.to_csv(OUT/'simulation_animation_frames_2023_2030.csv',index=False)
    (OUT/'stateful_simulation_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    inputs=[sites_path,climate_path,PRE/'master_sites_with_huc8.csv',PRE/'community_exposure_acs2023.csv',
            PRE/'site_aqueduct_basins.csv',PRE/'emissions/egrid2023_factors.csv',PRE/'emissions/site_egrid_mapping.csv',
            RAW/'epri/EPRI_2024_Projections.xlsx',baseline_path,future_path,PRE/'tracts_acs2023.gpkg']
    metadata=dict(created_utc=datetime.now(timezone.utc).isoformat(),climate_path=str(climate_path.relative_to(ROOT)),
        input_sha256={str(p.relative_to(ROOT)):digest(p) for p in inputs},
        implementation_sha256={str(p.relative_to(ROOT)):digest(p) for p in [
            ROOT/'src/model/stateful_community.py',ROOT/'src/analysis/stateful_community_simulation.py',
            ROOT/'src/analysis/plot_stateful_community.py',ROOT/'docs/data_sources.md']},
        direct_water_coefficient=dict(value=1.8,unit='m3/MWh',
            source='Supplied Siddik supplementary notebook Estimating_WF_CF_WSF_of_data_centers.html',
            section='Direct water footprint of data centers',
            verification_basis='User-supplied source passage and implementation, recorded in docs/data_sources.md; original HTML not located locally.'),
        energy_basis='Low density, AI inference, floor-area multiplier 1.0',
        energy_pue_mode='fixed_scenario' if baseline_pue else 'climate_fitted',
        energy_pue_source_counts=(sites.loc[sites.estimated_annual_facility_energy_mwh.notna(),'pue_source']
                                  .value_counts().to_dict() if not baseline_pue else {}),
        aqueduct_missing_baseline_fields=['available_blue_water','gross_water_demand'],
        adjusted_stress_ratio='Not calculated: cm/year cannot be added to m3/year without a verified hydrologic normalization-area basis.',
        interpretation='Screening of mapped site records, not a fully coupled climate-hydrology model or an independently deduplicated national inventory.',
        population='ACS 2019–2023 static; group proximity populations overlap across groups',
        scenario_pairs='Presentation combinations, not formally coupled climate/socioeconomic pathways',
        nasa_n_models=1,animation_created=False)
    (OUT/'stateful_simulation_provenance.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print('Stateful validation:',report,flush=True)
    return states,national


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--nasa-source',type=Path)
    parser.add_argument('--baseline-pue',action='store_true',help='Rebuild using the fixed-PUE energy scenario')
    args=parser.parse_args()
    build_artifacts(args.nasa_source,baseline_pue=args.baseline_pue)


if __name__=='__main__':main()
