import numpy as np
import pandas as pd
import pytest

from src.model.huc8_profiles import (
    PAIRS,SHORTLIST,WEIGHTS,aggregate_profiles,feature_table,preprocess,
    cluster_and_pca,normalize_reference,rank_robustness,crpi,hotspot_trajectories,
)


@pytest.fixture
def data():
    rows=[];pop=[]
    for i in range(24):
        huc=f'0101{i:04}';pop.append(dict(group_type='huc8',group_id=huc,unique_population_within_5km=100*(i+1)))
        for scenario,(epri,aq) in PAIRS.items():
            for year in [2023,2030]:
                factor=1 if year==2023 else {'lower_pressure':1.2,'central':1.4,'higher_pressure':1.8}[scenario]+(i%5)*.03
                for j in range(2):
                    energy=(i+1)**2*(j+1)*factor
                    rows.append(dict(site_id=f's{i}_{j}',huc8=huc,pfaf_id=f'{100000+i:06}',year=year,
                        epri_scenario=epri,aqueduct_scenario=aq,nasa_scenario='SSP2-4.5',n_models=1,
                        projected_energy_mwh=energy,annual_co2_metric_tonnes=energy*(.1+i*.005),
                        cumulative_co2_metric_tonnes=energy,annual_direct_water_m3=energy*1.8,
                        cumulative_direct_water_m3=energy*10,annual_water_footprint_m3=energy*4,
                        annual_water_scarcity_footprint_m3_eq=energy*(1+i%7),
                        aqueduct_water_stress=.05+(i%5)*.2,aqueduct_water_depletion=.02+i*.01,
                        temperature_mean_c=10+i*.3+(year-2023)*(.1 if i%2 else -.1),
                        warmest_day_mean_c=30+i*.2,incomplete_pop_5km=False,pop_5km=9999))
    return pd.DataFrame(rows),pd.DataFrame(pop)


def test_huc8_aggregation_and_unique_population_not_site_sum(data):
    sites,pop=data;result=aggregate_profiles(sites,pop)
    row=result[(result.huc8=='01010000')&(result.year==2023)&(result.screening_scenario=='central')].iloc[0]
    assert row.site_count==2 and row.projected_energy_mwh==3
    assert row.unique_population_within_5km==100
    assert row.unique_population_within_5km!=2*9999
    assert result.groupby('huc8').unique_population_within_5km.nunique().eq(1).all()


def test_unknown_risk_not_counted_as_low_risk(data):
    sites,pop=data
    mask=(sites.huc8=='01010000')
    sites.loc[mask&(sites.site_id=='s0_0'),'aqueduct_water_stress']=.9
    sites.loc[mask&(sites.site_id=='s0_1'),'aqueduct_water_stress']=np.nan
    result=aggregate_profiles(sites,pop)
    row=result[result.huc8=='01010000'].iloc[0]
    assert row.proportion_sites_high_water_stress==1
    assert row.proportion_sites_extremely_high_water_stress==1
    assert row.stress_site_coverage==.5


def test_matched_intensity_denominator_does_not_dilute_missing_coefficient(data):
    sites,pop=data
    first=(sites.huc8=='01010000')
    sites.loc[first&(sites.site_id=='s0_0'),'projected_energy_mwh']=100
    sites.loc[first&(sites.site_id=='s0_1'),'projected_energy_mwh']=5
    sites.loc[first&(sites.site_id=='s0_0'),'annual_co2_metric_tonnes']=30
    sites.loc[first&(sites.site_id=='s0_1'),'annual_co2_metric_tonnes']=np.nan
    result=feature_table(aggregate_profiles(sites,pop)).set_index('huc8')
    assert result.loc['01010000','carbon_intensity_tonnes_per_mwh']==pytest.approx(.3)


def test_preprocessing_standardization_and_identifier_exclusion(data):
    features=feature_table(aggregate_profiles(*data))
    X,enriched,report,correlations,metadata=preprocess(features)
    assert 'huc8' not in X and set(X).issubset(SHORTLIST)
    np.testing.assert_allclose(X.mean(),0,atol=1e-10)
    np.testing.assert_allclose(X.std(ddof=0),1,atol=1e-10)
    assert np.isfinite(X).all().all()
    assert 'log1p' in report.transform_applied.tolist()
    assert len(correlations)==report.shape[0]**2


def test_missing_raw_values_remain_missing_and_only_ml_matrix_is_imputed(data):
    features=feature_table(aggregate_profiles(*data))
    features['carbon_intensity_tonnes_per_mwh']=np.random.default_rng(10).uniform(.1,.8,len(features))
    features.loc[0,'carbon_intensity_tonnes_per_mwh']=np.nan
    X,enriched,report,_,_=preprocess(features)
    assert np.isnan(enriched.loc[0,'carbon_intensity_tonnes_per_mwh'])
    assert enriched.loc[0,'ml_imputed_feature_count']==1
    assert np.isfinite(X.loc[0,'carbon_intensity_tonnes_per_mwh'])
    assert report.set_index('feature').loc['carbon_intensity_tonnes_per_mwh','missing_count']==1


def test_unsupported_resource_group_not_assigned_zero_or_ml_cluster(data):
    features=feature_table(aggregate_profiles(*data));features.loc[0,'energy_2030_mwh']=np.nan
    X,enriched,_,_,_=preprocess(features)
    assert 0 not in X.index and not enriched.loc[0,'ml_eligible']
    assert np.isnan(enriched.loc[0,'energy_2030_mwh'])


def test_pca_alignment_cluster_diagnostics_and_reproducibility(data):
    features=feature_table(aggregate_profiles(*data));X,enriched,*_=preprocess(features)
    a=cluster_and_pca(X,enriched);b=cluster_and_pca(X,enriched)
    pd.testing.assert_series_equal(a[0].cluster_id,b[0].cluster_id)
    assert a[1].shape[0]==len(X) and {'PC1','PC2','PC3','huc8','cluster'}.issubset(a[1])
    assert a[2].feature.tolist()==X.columns.tolist()
    assert a[3].explained_variance_ratio.sum()==pytest.approx(1)
    diag=a[4]
    assert diag.k.tolist()==list(range(2,9))
    chosen=diag[diag.chosen].iloc[0]
    assert chosen.size_eligible and chosen.silhouette_score>=diag[diag.size_eligible].silhouette_score.max()-.02


def test_fixed_reference_normalization_and_missingness():
    result=normalize_reference(pd.Series([0,10,20,np.nan,30]),[0,10,20])
    np.testing.assert_allclose(result.iloc[:3],[0,50,100]);assert np.isnan(result.iloc[3]) and result.iloc[4]==100
    assert normalize_reference([5,np.nan],[5,5]).iloc[0]==50
    np.testing.assert_allclose(normalize_reference([4,5,6],[5,5]),[0,50,100])


def test_machine_precision_growth_is_not_an_ml_signal(data):
    features=feature_table(aggregate_profiles(*data))
    features['energy_growth_pct_2023_2030']=40.+np.arange(len(features))*1e-13
    X,_,report,_,_=preprocess(features)
    assert 'energy_growth_pct_2023_2030' not in X
    normalized=normalize_reference(features.energy_growth_pct_2023_2030,features.energy_growth_pct_2023_2030)
    assert normalized.eq(50).all()
    features['energy_growth_pct_2023_2030']=40.71+np.linspace(-.002,.002,len(features))
    X,_,_,_,_=preprocess(features)
    assert 'energy_growth_pct_2023_2030' not in X
    assert normalize_reference(features.energy_growth_pct_2023_2030,features.energy_growth_pct_2023_2030,absolute_tolerance=.01).eq(50).all()


def test_rank_robustness_common_cohort_and_missing_not_low():
    rows=[]
    for huc,values in [('A',[10,20,30]),('B',[5,15,40]),('C',[1,np.nan,1])]:
        for scenario,value in zip(PAIRS,values):rows.append(dict(huc8=huc,screening_scenario=scenario,value=value))
    result=rank_robustness(pd.DataFrame(rows),'value').set_index('huc8')
    assert result.loc['A','rank_range']==1
    assert result.loc['A','comparison_cohort_size']==2
    assert pd.isna(result.loc['C','rank_central']) and pd.isna(result.loc['C','top25pct_all_scenarios'])


def test_crpi_weights_reproducible_bounded_and_missing_dimension_unscored(data):
    dynamic=aggregate_profiles(*data)
    a,weights,_=crpi(dynamic);b,_,_=crpi(dynamic)
    pd.testing.assert_frame_equal(a,b)
    assert all(np.isclose(sum(w),1) for w in WEIGHTS.values())
    assert weights.groupby('scheme').weight.sum().eq(1).all()
    assert a.crpi_equal.between(0,100).all()
    dynamic.loc[dynamic.huc8=='01010000','annual_co2_metric_tonnes']=np.nan
    changed,_,_=crpi(dynamic)
    assert changed[changed.huc8=='01010000'].crpi_equal.isna().all()


def test_hotspot_classification_endpoint_change_and_unknowns():
    rows=[]
    for i,(start,end) in enumerate(zip([1000,800,100,50,10,1,np.nan],[1100,850,1050,60,15,2,np.nan])):
        for year,value in [(2023,start),(2030,end)]:
            rows.append(dict(huc8=f'{i:08}',year=year,screening_scenario='central',projected_energy_mwh=value,
                annual_direct_water_m3=value,annual_water_footprint_m3=value,
                annual_water_scarcity_footprint_m3_eq=value,median_aqueduct_water_stress=9999 if i==0 else .3))
    result,method=hotspot_trajectories(pd.DataFrame(rows));result=result.set_index('huc8')
    assert result.loc['00000000','hotspot_category']=='persistent_hotspot'
    assert result.loc['00000002','hotspot_category']=='emerging_hotspot'
    assert result.loc['00000006','hotspot_category']=='not_assessable'
    assert pd.isna(result.loc['00000000','aqueduct_stress_absolute_change'])
    assert method['pressure_metric'].startswith('Annual scarcity-weighted')
