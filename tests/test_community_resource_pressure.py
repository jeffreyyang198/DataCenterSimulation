from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from src.pipeline.community_resource_pressure import (
    assign_basins, estimate_population, normalize_future, site_buffers, validate_tracts,
)


def test_population_area_allocation_and_missing_coverage():
    tracts = gpd.GeoDataFrame({'population':[100.,200.]},
        geometry=[box(0,0,10,10),box(10,0,20,10)],crs=6933)
    circles = gpd.GeoDataFrame({'site_id':['a','b']},
        geometry=[box(5,0,15,10),box(-10,0,0,10)],crs=6933)
    result = estimate_population(circles,tracts)
    assert result.loc[0,'population']==pytest.approx(150)
    assert not result.loc[0,'incomplete']
    assert result.loc[1,'incomplete']
    assert pd.isna(result.loc[1,'population'])


def test_missing_population_is_flagged_even_with_complete_geometry():
    tracts = gpd.GeoDataFrame({'population':[None]},geometry=[box(0,0,10,10)],crs=6933)
    circles = gpd.GeoDataFrame({'site_id':['a']},geometry=[box(0,0,10,10)],crs=6933)
    assert estimate_population(circles,tracts).loc[0,'incomplete']


def test_basin_boundary_ambiguity_and_same_basin_parts():
    sites=pd.DataFrame({'site_id':['edge','inside','outside'],
        'longitude':[1,.5,10],'latitude':[.5,.5,10]})
    basins=gpd.GeoDataFrame({'pfaf_id':['111111','222222','111111']},
        geometry=[box(0,0,1,1),box(1,0,2,1),box(0,0,.8,.8)],crs=4326)
    result=assign_basins(sites,basins).set_index('site_id')
    assert result.loc['edge','aqueduct_assignment_status']=='ambiguous'
    assert pd.isna(result.loc['edge','pfaf_id'])
    assert result.loc['inside','pfaf_id']=='111111'
    assert result.loc['outside','aqueduct_assignment_status']=='unmatched'


def test_normalization_preserves_special_codes_and_scenario_identity():
    frame=pd.DataFrame({'pfaf_id':['111111'],'opt30_ws_x_r':[-1],
        'bau30_ws_x_r':[.4],'pes30_ws_x_r':[.8]})
    result=normalize_future(frame).set_index('aqueduct_scenario')
    assert pd.isna(result.loc['optimistic','ws_x_r'])
    assert result.loc['optimistic','ws_x_r_source_value']==-1
    assert result.loc['bau','ws_x_r']==.4
    assert result.loc['pessimistic','ws_x_r']==.8
    with pytest.raises(ValueError,match='unique'):
        normalize_future(pd.concat([frame,frame]))


def test_reject_wrong_tiger_vintage_or_geography():
    frame=gpd.GeoDataFrame({'GEOID':['01001000100'],'STATEFP':['01'],
        'COUNTYFP':['001'],'TRACTCE':['000100']},geometry=[box(0,0,1,1)],crs=4269)
    validate_tracts(frame,Path('tl_2023_01_tract.shp'))
    for name in ['tl_2022_01_tract.shp','tl_2023_01_bg.shp','tl_2023_us_county.shp']:
        with pytest.raises(ValueError,match='2023 TRACT'):
            validate_tracts(frame,Path(name))


def test_site_buffer_area_at_high_latitude():
    sites=pd.DataFrame({'site_id':['a'],'longitude':[-150.],'latitude':[64.]})
    circles=site_buffers(sites,5)
    assert circles.geometry.area.iloc[0]==pytest.approx(3.14159265*5000**2,rel=.002)


def test_acs_summary_file_filters_tracts_and_preserves_geoid(tmp_path, monkeypatch):
    from src.pipeline import fetch_acs2023
    monkeypatch.setattr(fetch_acs2023,'ROOT',tmp_path)
    folder=tmp_path/'data/raw/census/acs2023'
    folder.mkdir(parents=True)
    (folder/'acsdt5y2023-b01003.dat').write_text(
        'GEO_ID|B01003_E001|B01003_M001\n'
        '1400000US01001000100|123|12\n'
        '1400000US01001000200|-666666666|0\n'
        '1500000US010010001001|50|5\n')
    fetch_acs2023.main()
    result=pd.read_csv(folder/'acs2023_tract_population.csv',dtype={'GEOID':str})
    assert result.GEOID.tolist()==['01001000100','01001000200']
    assert result.population.iloc[0]==123
    assert pd.isna(result.population.iloc[1])
