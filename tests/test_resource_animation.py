import numpy as np
import pandas as pd
import pytest

from src.visualization.animate_resource_pressure import (
    YEARS,SCENARIO,METRICS,validate_frames,extract_metrics,select_hotspots,
    select_contrast,stress_category,key_at_time,
)


@pytest.fixture
def frames():
    frame=pd.DataFrame({'year':YEARS,'epri_scenario':['moderate']*8,
        'aqueduct_scenario':['business_as_usual']*8,'presentation_scenario':[SCENARIO]*8})
    for col in METRICS:frame[col]=np.arange(1,9,dtype=float)*1e6
    frame['unique_population_within_5km']=10e6
    return frame


def test_valid_frame_table_and_actual_year_order(frames):
    validate_frames(frames)
    with pytest.raises(ValueError,match='ordered'):validate_frames(frames.iloc[::-1])


@pytest.mark.parametrize('change',['duplicate','missing'])
def test_incomplete_or_duplicate_years_rejected(frames,change):
    bad=pd.concat([frames,frames.iloc[:1]]) if change=='duplicate' else frames.iloc[:-1]
    with pytest.raises(ValueError):validate_frames(bad)


def test_metric_extraction_preserves_unit_distinctions(frames):
    row=frames.iloc[0].copy()
    row['projected_energy_mwh']=2.5e6;row['annual_direct_water_m3']=3e6
    row['annual_water_footprint_m3']=4e9;row['annual_water_scarcity_footprint_m3_eq']=5e9
    values=extract_metrics(row)
    assert values['projected_energy_mwh']==2.5
    assert values['annual_direct_water_m3']==3
    assert values['annual_water_footprint_m3']==4
    assert values['annual_water_scarcity_footprint_m3_eq']==5


def test_population_cannot_animate_growth(frames):
    frames.loc[3,'unique_population_within_5km']+=1
    with pytest.raises(ValueError,match='constant'):validate_frames(frames)


@pytest.mark.parametrize('column',['cumulative_co2_metric_tonnes','cumulative_direct_water_m3'])
def test_cumulative_decline_rejected(frames,column):
    frames.loc[4,column]=0
    with pytest.raises(ValueError,match='nondecreasing'):validate_frames(frames)


def hotspot_fixture():
    ids=[f'010100{i:02}' for i in range(1,9)]
    huc=pd.DataFrame({'huc8':ids,'annual_water_footprint_m3':np.array([1,2,3,4,10,20,30,40])*1e6,
        'unique_population_within_5km':[1,2,3,4,100,200,300,400],
        'median_aqueduct_water_stress':[.5]*7+[.2],
        'annual_water_scarcity_footprint_m3_eq':[1000,2,3,4,5,6,7,900]})
    sites=pd.DataFrame({'huc8':ids,'site_id':ids,'pfaf_id':[f'{i:06}' for i in range(8)],
        'aqueduct_water_stress':[.5]*7+[.2],'incomplete_pop_5km':[False]*8})
    return huc,sites


def test_hotspots_are_transparent_intersection_not_only_largest_demand():
    huc,sites=hotspot_fixture()
    chosen,method=select_hotspots(huc,sites)
    assert chosen.huc8.tolist()==['01010007']
    assert chosen.annual_water_footprint_m3.min()>=method['wf_q75_m3_year']
    assert chosen.unique_population_within_5km.min()>=method['population_q75']
    assert 'No composite score' in method['ranking']


def test_incomplete_population_group_is_not_promoted_to_hotspot():
    huc,sites=hotspot_fixture();sites.loc[sites.huc8=='01010007','incomplete_pop_5km']=True
    chosen,_=select_hotspots(huc,sites)
    assert '01010007' not in chosen.huc8.tolist()
    assert not chosen.incomplete_population.any()


def test_contrasts_selected_from_independent_ranks():
    huc,_=hotspot_fixture();pair,method=select_contrast(huc)
    assert pair.huc8.tolist()==['01010001','01010008']
    assert pair.population_rank.tolist()==[8,1]
    assert method['hard_coded_huc8_ids'] is False


def test_stress_categories_keep_missing_separate_and_extreme_values_extreme():
    assert stress_category([.05,.15,.3,.5,.9,9999,np.nan,-1]).tolist()==[0,1,2,3,4,4,-1,-1]


def test_narrative_timeline_uses_all_eight_annual_outputs():
    assert key_at_time(0)=='opening' and key_at_time(3.99)=='opening'
    assert [key_at_time(4+2*i) for i in range(8)]==list(map(str,YEARS))
    assert key_at_time(20)=='hotspots' and key_at_time(25)=='contrast' and key_at_time(30)=='final'
