import numpy as np
import pandas as pd
import pytest

from src.model.stateful_community import (
    YEARS,EPRI_SCENARIOS,STATE_KEYS,aqueduct_annual_context,build_states,
    prepare_nasa,interpolate_aqueduct,compatible_adjusted_ratio,accumulate,require_unique,
)


@pytest.fixture
def inputs():
    sites=pd.DataFrame(dict(site_id=['a','b','c'],state_abbr=['XX','XX','ZZ'],
        longitude=[-80.,-81.,-82.],latitude=[35.,36.,37.],
        estimated_annual_facility_energy_mwh=[100.,200.,300.]))
    growth=pd.DataFrame([dict(state_abbr='XX',scenario=s,year=y,epri_growth_factor=1.1**(y-2023))
                         for s in EPRI_SCENARIOS for y in YEARS])
    factors=pd.DataFrame(dict(egrid_subregion=['R'],co2_lb_per_mwh=[100.],co2e_lb_per_mwh=[110.],
                              nox_lb_per_mwh=[1.],so2_lb_per_mwh=[2.]))
    mapping=pd.DataFrame(dict(site_id=['a','b','c'],egrid_subregion=['R']*3))
    water=pd.DataFrame(dict(site_id=['a','b','c'],huc8=['01010001','01010002','01010003'],
                             WF_1MW_DC=[4.,np.nan,4.],WSF_1MW_DC=[8.,np.nan,8.]))
    population=pd.DataFrame(dict(site_id=['a','b','c'],pop_1km=[10.,20.,30.],
        pop_3km=[100.,200.,300.],pop_5km=[1000.,2000.,3000.],incomplete_pop_5km=[False]*3))
    basins=pd.DataFrame(dict(site_id=['a','b','c'],pfaf_id=['111111','222222','333333'],
                              aqueduct_assignment_status=['assigned']*3))
    nasa=pd.DataFrame([dict(site_id=s,year=y,scenario='ssp245',temperature_mean_c=10+i+(y-2023)*.1,
        warmest_day_mean_c=30+i+(y-2023)*.2,coldest_day_mean_c=-2+i,n_models=1,
        temperature_anomaly_vs_2023_2030_c=(y-2023)*.1-.35)
        for i,s in enumerate(['a','b','c']) for y in YEARS])
    base=pd.DataFrame(dict(pfaf_id=['111111','222222','333333'],bws_raw=[.2]*3,bwd_raw=[.1]*3))
    future=base[['pfaf_id']].copy()
    for scenario,end in [('opt',.3),('bau',.4),('pes',.6)]:
        for variable,value in [('ws',end),('wd',end/2),('ba',12.),('ww',6.)]:
            future[f'{scenario}30_{variable}_x_r']=value
    aq=aqueduct_annual_context(base,future)
    return dict(sites=sites,growth=growth,factors=factors,mapping=mapping,water=water,
                population=population,basins=basins,nasa=nasa,aqueduct=aq)


@pytest.fixture
def states(inputs):return build_states(**inputs)


def central(states,site='a'):
    return states[(states.site_id==site)&(states.presentation_scenario=='central_2030_screening')]


@pytest.mark.parametrize('pollutant',['co2','co2e','nox','so2'])
def test_cumulative_emissions_inherit_prior_state(states,pollutant):
    sample=central(states)
    annual=sample[f'annual_{pollutant}_metric_tonnes'].to_numpy()
    np.testing.assert_allclose(sample[f'cumulative_{pollutant}_metric_tonnes'],np.cumsum(annual))
    assert sample[f'cumulative_{pollutant}_metric_tonnes'].diff().dropna().ge(0).all()


def test_direct_water_annual_and_cumulative_are_distinct(states):
    sample=central(states)
    np.testing.assert_allclose(sample.annual_direct_water_m3,sample.projected_energy_mwh*1.8)
    np.testing.assert_allclose(sample.cumulative_direct_water_m3,np.cumsum(sample.annual_direct_water_m3))
    assert sample.annual_direct_water_m3.iloc[0]==180
    assert sample.cumulative_direct_water_m3.iloc[-1]>sample.annual_direct_water_m3.iloc[-1]


def test_existing_compounding_equivalence(states):
    sample=central(states)
    np.testing.assert_allclose(sample.projected_energy_mwh,100*1.1**np.arange(8))
    np.testing.assert_allclose(sample.projected_energy_mwh.iloc[1:].to_numpy(),sample.projected_energy_mwh.iloc[:-1].to_numpy()*1.1)


def test_aqueduct_interpolation_bounds_endpoints_and_missingness():
    np.testing.assert_allclose(interpolate_aqueduct([.2]*3,[.9]*3,[2023,2026,2030]),[.2,.5,.9])
    result=interpolate_aqueduct([.2,np.nan,np.nan],[np.nan,.9,.9],[2023,2026,2030])
    assert result[0]==.2 and np.isnan(result[1]) and result[2]==.9
    with pytest.raises(ValueError):interpolate_aqueduct([.2],[.9],[2031])


def test_population_static_through_time(states):
    for col in ['pop_1km','pop_3km','pop_5km']:
        assert states.groupby('site_id')[col].nunique().eq(1).all()


def test_nasa_join_rejects_duplicate_year_and_other_scenarios(inputs):
    with pytest.raises(ValueError,match='duplicate'):
        prepare_nasa(pd.concat([inputs['nasa'],inputs['nasa'].iloc[:1]]))
    bad=inputs['nasa'].copy();bad.loc[0,'scenario']='ssp126'
    with pytest.raises(ValueError,match='SSP2-4.5'):prepare_nasa(bad)


def test_nasa_remains_external_and_deviation_is_named_honestly(states):
    assert states.groupby(['site_id','year']).temperature_mean_c.nunique().eq(1).all()
    assert states.n_models.eq(1).all()
    assert 'temperature_anomaly_vs_2023_2030_c' not in states
    assert 'temperature_deviation_from_2023_2030_mean_c' in states


def test_unit_compatibility_prevents_depth_plus_volume():
    with pytest.raises(ValueError,match='Incompatible'):
        compatible_adjusted_ratio([5.],[1.],[10.],'cm/year','m3/year',True)
    with pytest.raises(ValueError,match='basis'):
        compatible_adjusted_ratio([5.],[1.],[10.],'m3/year','m3/year')
    result=compatible_adjusted_ratio([5.,5.],[1.,1.],[10.,0.],'m3/year','m3/year',True)
    assert result[0]==.6 and np.isnan(result[1])


def test_simulation_grid_unique_and_presentation_pairs(states):
    assert len(states)==3*8*4*3
    require_unique(states,STATE_KEYS+['year'],'test')
    expected={'central_2030_screening':('moderate','business_as_usual'),
              'lower_pressure':('low','optimistic'),'higher_pressure':('higher','pessimistic')}
    for name,pair in expected.items():
        sample=states[states.presentation_scenario==name]
        assert set(zip(sample.epri_scenario,sample.aqueduct_scenario))=={pair}
        assert len(sample)==24
    with pytest.raises(ValueError,match='duplicate'):
        require_unique(pd.concat([states,states.iloc[:1]]),STATE_KEYS+['year'],'test')


def test_missing_demand_and_coefficients_remain_nan(states):
    missing=central(states,'c')
    assert missing[['projected_energy_mwh','annual_co2_metric_tonnes','cumulative_co2_metric_tonnes',
                    'annual_direct_water_m3','cumulative_direct_water_m3']].isna().all().all()
    partial=central(states,'b')
    assert partial.annual_water_footprint_m3.isna().all()
    assert partial.annual_direct_water_m3.notna().all()


def test_unknown_cumulative_history_does_not_silently_resume():
    frame=pd.DataFrame(dict(site_id=['a']*4,epri_scenario=['moderate']*4,
        aqueduct_scenario=['business_as_usual']*4,annual=[1.,np.nan,2.,3.]))
    result=accumulate(frame,'annual')
    assert result.iloc[0]==1 and result.iloc[1:].isna().all()


def test_siddik_is_annual_and_not_multiplied_by_aqueduct(states):
    sample=central(states)
    np.testing.assert_allclose(sample.annual_water_footprint_m3,sample.projected_energy_mwh*4)
    np.testing.assert_allclose(sample.annual_water_scarcity_footprint_m3_eq,sample.projected_energy_mwh*8)
    assert sample.aqueduct_available_blue_water.iloc[:-1].isna().all()
    assert sample.aqueduct_available_blue_water.iloc[-1]==12
    assert 'dc_adjusted_water_stress_ratio' not in states
