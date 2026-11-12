"""Annual screening states, with external environmental conditions and no feedback.

Direct water coefficient provenance: supplied Siddik supplementary notebook
Estimating_WF_CF_WSF_of_data_centers.html, section 'Direct water footprint of
data centers'. The source explanation and implementation supplied by the user
multiply scaled electricity consumption (MWh) by 1.8 m3/MWh. This is direct
data-center water demand, not total blue water footprint (direct + indirect).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

YEARS = tuple(range(2023, 2031))
EPRI_SCENARIOS = ('low', 'moderate', 'high', 'higher')
AQUEDUCT_SCENARIOS = {'optimistic':'opt', 'business_as_usual':'bau', 'pessimistic':'pes'}
PRESENTATION_PAIRS = {
    ('moderate','business_as_usual'):'central_2030_screening',
    ('low','optimistic'):'lower_pressure',
    ('higher','pessimistic'):'higher_pressure',
}
DIRECT_WATER_M3_PER_MWH = 1.8
LB_TO_METRIC_TONNES = 0.00045359237
STATE_KEYS = ['site_id','epri_scenario','aqueduct_scenario']


def require_unique(frame, keys, name):
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError(f'{name}: missing or duplicate keys {keys}')


def clean_raw(series):
    values = pd.to_numeric(series, errors='raise').astype(float)
    return values.where(np.isfinite(values) & (values >= 0))


def interpolate_aqueduct(baseline, future, years):
    """Screening interpolation only; retain known endpoints if the other is NA."""
    years = np.asarray(years)
    if not np.isin(years, YEARS).all():
        raise ValueError('Aqueduct interpolation only supports 2023–2030')
    baseline, future = np.asarray(baseline, dtype=float), np.asarray(future, dtype=float)
    alpha = (years - 2023) / 7
    values = baseline + alpha * (future - baseline)
    return np.where(alpha == 0, baseline, np.where(alpha == 1, future, values))


def compatible_adjusted_ratio(demand, direct, supply, background_unit, direct_unit,
                              normalization_area_verified=False):
    """Reject depth/volume mixing; no implicit or guessed basin-area conversion."""
    if background_unit != 'm3/year' or direct_unit != 'm3/year':
        raise ValueError('Incompatible water units; verified depth-to-volume conversion required')
    if not normalization_area_verified:
        raise ValueError('Hydrologic normalization/volume basis must be verified')
    supply = np.asarray(supply,dtype=float)
    return np.divide(np.asarray(demand)+np.asarray(direct), supply,
                     out=np.full(supply.shape,np.nan),where=np.isfinite(supply)&(supply>0))


def aqueduct_annual_context(baseline, future):
    """Use basin-constant baseline raw values, not fragment-weighted risk scores."""
    require_unique(future,['pfaf_id'],'Aqueduct future')
    for column in ['bws_raw','bwd_raw']:
        if baseline.groupby('pfaf_id')[column].nunique(dropna=False).gt(1).any():
            raise ValueError('Conflicting baseline risk values within a PFAF basin')
    base = baseline[['pfaf_id','bws_raw','bwd_raw']].drop_duplicates('pfaf_id')
    merged = future.merge(base,on='pfaf_id',how='outer',validate='one_to_one')
    rows=[]
    for scenario,code in AQUEDUCT_SCENARIOS.items():
        for year in YEARS:
            part=merged[['pfaf_id']].copy()
            part['year']=year
            part['aqueduct_scenario']=scenario
            for variable,bcol,fcol,unit in [
                ('water_stress','bws_raw',f'{code}30_ws_x_r','ratio'),
                ('water_depletion','bwd_raw',f'{code}30_wd_x_r','ratio'),
                ('available_blue_water',None,f'{code}30_ba_x_r','cm/year'),
                ('background_water_demand',None,f'{code}30_ww_x_r','cm/year'),
            ]:
                start=clean_raw(merged[bcol]) if bcol else pd.Series(np.nan,index=merged.index)
                end=clean_raw(merged[fcol])
                name='aqueduct_'+variable
                part[name]=interpolate_aqueduct(start,end,np.full(len(part),year))
                part[name+'_baseline']=start.to_numpy()
                part[name+'_2030']=end.to_numpy()
                part[name+'_unit']=unit
            part['aqueduct_interpolation_status']='screening_interpolation_of_raw_stress_and_depletion'
            part['aqueduct_supply_demand_status']='baseline_unavailable;2030_endpoints_only;cm/year'
            rows.append(part)
    return pd.concat(rows,ignore_index=True)


def prepare_nasa(frame):
    required=['site_id','year','scenario','temperature_mean_c','warmest_day_mean_c',
              'coldest_day_mean_c','n_models']
    if missing := set(required)-set(frame):
        raise ValueError(f'NASA missing columns: {sorted(missing)}')
    require_unique(frame,['site_id','year'],'NASA site/year')
    if not frame.scenario.isin(['ssp245','SSP2-4.5']).all():
        raise ValueError('Only the supplied SSP2-4.5 climate scenario is supported')
    if not frame.year.isin(YEARS).all() or not frame.n_models.eq(1).all():
        raise ValueError('Expected 2023–2030, single-model NASA data')
    if not frame.groupby('site_id').year.nunique().eq(8).all():
        raise ValueError('NASA requires eight years per site')
    extras=[c for c in frame if c.startswith(('precip','pr_'))]
    anomaly='temperature_anomaly_vs_2023_2030_c'
    cols=[c for c in required if c!='scenario']+extras
    if anomaly in frame:cols.append(anomaly)
    result=frame[cols].copy().rename(columns={anomaly:'temperature_deviation_from_2023_2030_mean_c'})
    result['nasa_scenario']='SSP2-4.5'
    return result


def accumulate(frame, annual_column):
    """Each state inherits the prior cumulative amount; unknown history propagates."""
    groups=[frame[key] for key in STATE_KEYS]
    running=frame[annual_column].groupby(groups,sort=False).cumsum()
    missing_history=frame[annual_column].isna().groupby(groups,sort=False).cummax()
    return running.mask(missing_history)


def build_states(sites, growth, factors, mapping, water, population, basins, nasa, aqueduct):
    for frame,keys,name in [
        (sites,['site_id'],'sites'),(growth,['state_abbr','scenario','year'],'EPRI growth'),
        (factors,['egrid_subregion'],'eGRID'),(mapping,['site_id'],'eGRID mapping'),
        (water,['site_id'],'Siddik'),(population,['site_id'],'population'),
        (basins,['site_id'],'PFAF assignment')]:
        require_unique(frame,keys,name)
    climate=prepare_nasa(nasa)
    if set(climate.site_id)!=set(sites.site_id):
        raise ValueError('NASA site inventory differs from the site master')
    base=sites[['site_id','state_abbr','longitude','latitude','estimated_annual_facility_energy_mwh']].copy()
    base=base.merge(mapping[['site_id','egrid_subregion']],on='site_id',how='left',validate='one_to_one')
    base=base.merge(factors,on='egrid_subregion',how='left',validate='many_to_one')
    base=base.merge(water[['site_id','huc8','WF_1MW_DC','WSF_1MW_DC']],on='site_id',how='left',validate='one_to_one')
    popcols=['site_id']+[c for c in population if c.startswith(('pop_','incomplete_pop_','coverage_fraction_'))]
    base=base.merge(population[popcols],on='site_id',how='left',validate='one_to_one')
    base=base.merge(basins[['site_id','pfaf_id','aqueduct_assignment_status']],on='site_id',how='left',validate='one_to_one')
    grid=pd.MultiIndex.from_product([EPRI_SCENARIOS,YEARS],names=['epri_scenario','year']).to_frame(index=False)
    result=base.merge(grid,how='cross')
    result=result.merge(growth[['state_abbr','scenario','year','epri_growth_factor']].rename(
        columns={'scenario':'epri_scenario'}),on=['state_abbr','epri_scenario','year'],how='left',validate='many_to_one')
    factor=result.epri_growth_factor.where(np.isfinite(result.epri_growth_factor)&(result.epri_growth_factor>0))
    result['epri_growth_factor']=factor
    # Exact existing EPRI geometric-compounding trajectory, relative to 2023.
    result['projected_energy_mwh']=result.estimated_annual_facility_energy_mwh*factor
    for pollutant in ('co2','co2e','nox','so2'):
        result[f'annual_{pollutant}_metric_tonnes']=(
            result.projected_energy_mwh*result[f'{pollutant}_lb_per_mwh']*LB_TO_METRIC_TONNES)
    result['direct_water_coefficient_m3_per_mwh']=DIRECT_WATER_M3_PER_MWH
    result['annual_direct_water_m3']=result.projected_energy_mwh*DIRECT_WATER_M3_PER_MWH
    result['annual_water_footprint_m3']=result.projected_energy_mwh*result.WF_1MW_DC
    result['annual_water_scarcity_footprint_m3_eq']=result.projected_energy_mwh*result.WSF_1MW_DC
    result=result.merge(climate,on=['site_id','year'],how='left',validate='many_to_one')
    result=result.merge(pd.DataFrame({'aqueduct_scenario':list(AQUEDUCT_SCENARIOS)}),how='cross')
    require_unique(aqueduct,['pfaf_id','year','aqueduct_scenario'],'Aqueduct annual')
    result=result.merge(aqueduct,on=['pfaf_id','year','aqueduct_scenario'],how='left',validate='many_to_one')
    # Explicit parallel raw-risk fields for the unit-incompatible adjusted-ratio fallback.
    result['aqueduct_water_stress_raw']=result.aqueduct_water_stress
    result['aqueduct_water_depletion_raw']=result.aqueduct_water_depletion
    result=result.sort_values(STATE_KEYS+['year']).reset_index(drop=True)
    for pollutant in ('co2','co2e','nox','so2'):
        result[f'cumulative_{pollutant}_metric_tonnes']=accumulate(result,f'annual_{pollutant}_metric_tonnes')
    result['cumulative_direct_water_m3']=accumulate(result,'annual_direct_water_m3')
    result['presentation_scenario']=[PRESENTATION_PAIRS.get((a,b),'sensitivity_grid')
                                    for a,b in zip(result.epri_scenario,result.aqueduct_scenario)]
    result['adjusted_water_stress_status']='not_computed:cm/year_vs_m3/year;normalization_area_unverified'
    result['simulation_status']=''
    checks={
        'no_projected_energy':result.projected_energy_mwh.isna(),
        'missing_emission_factor':result[[f'annual_{p}_metric_tonnes' for p in ('co2','co2e','nox','so2')]].isna().any(axis=1),
        'missing_siddik_factor':result[['annual_water_footprint_m3','annual_water_scarcity_footprint_m3_eq']].isna().any(axis=1),
        'missing_aqueduct_stress':result.aqueduct_water_stress.isna(),
        'missing_aqueduct_depletion':result.aqueduct_water_depletion.isna(),
        'missing_climate':result.temperature_mean_c.isna(),
        'incomplete_population_buffer':result.incomplete_pop_5km.fillna(True).astype(bool),
    }
    for reason,mask in checks.items():
        result.loc[mask,'simulation_status']+=reason+';'
    result['simulation_status']=result.simulation_status.str.rstrip(';').replace('','complete_available_context')
    require_unique(result,STATE_KEYS+['year'],'annual simulation')
    return result
