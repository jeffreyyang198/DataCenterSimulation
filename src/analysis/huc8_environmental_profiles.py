"""Reproducible, unsupervised watershed screening analysis of existing outputs."""
from pathlib import Path
from datetime import datetime,timezone
import json
import hashlib
import argparse
import importlib.metadata
import struct

import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio

from src.model.huc8_profiles import (
    PAIRS,KEYS,SHORTLIST,DIMENSIONS,WEIGHTS,FRIENDLY,
    aggregate_profiles,feature_table,preprocess,cluster_and_pca,crpi,
    rank_robustness,hotspot_trajectories,unique,
)

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def read_inputs():
    metadata=json.loads((OUT/'stateful_simulation_provenance.json').read_text())
    paths=dict(huc=OUT/'stateful_huc8_resource_simulation_2023_2030.csv',
        states=OUT/'stateful_community_resource_simulation_2023_2030.csv',
        combined=OUT/'community_resource_pressure/community_resource_pressure_2030.csv',
        mapping=ROOT/'data/processed/master_sites_with_huc8.csv',
        population=ROOT/'data/processed/community_exposure_acs2023.csv',
        aqueduct=ROOT/'data/processed/site_aqueduct_basins.csv',
        nasa=ROOT/metadata['climate_path'],unique_pop=ROOT/'data/processed/stateful_unique_population_5km.csv',
        geometry=ROOT/'data/raw/siddik/SI_Shapefile.shp')
    columns=['site_id','huc8','pfaf_id','year','epri_scenario','aqueduct_scenario','nasa_scenario','n_models',
        'projected_energy_mwh','annual_co2_metric_tonnes','cumulative_co2_metric_tonnes','annual_direct_water_m3',
        'cumulative_direct_water_m3','annual_water_footprint_m3','annual_water_scarcity_footprint_m3_eq',
        'aqueduct_water_stress','aqueduct_water_depletion','temperature_mean_c','warmest_day_mean_c','incomplete_pop_5km']
    data={}
    for name,path in paths.items():
        if name=='geometry':continue
        if name in ['huc','states','unique_pop']:
            frame=pd.read_csv(path,usecols=columns if name=='states' else None,dtype={'huc8':str,'pfaf_id':str,'site_id':str,'group_id':str})
            data[name]=frame;header=frame.columns.tolist()
        else:header=pd.read_csv(path,nrows=0).columns.tolist()
        print(f'SELECTED {name}: {path}\n  columns: {header}',flush=True)
    with paths['geometry'].with_suffix('.dbf').open('rb') as stream:
        header=stream.read(32);length=struct.unpack('<H',header[8:10])[0]
        descriptors=stream.read(length-32)
    fields=[descriptors[i:i+11].split(b'\0')[0].decode() for i in range(0,len(descriptors)-1,32)]
    print('SELECTED geometry:',paths['geometry'],'\n  DBF fields:',fields,
          '\n  CRS:',paths['geometry'].with_suffix('.prj').read_text()[:160],flush=True)
    return data,paths


def verify_aggregation(dynamic,source):
    pair=pd.DataFrame([dict(screening_scenario=s,epri_scenario=e,aqueduct_scenario=a) for s,(e,a) in PAIRS.items()])
    expected=source.merge(pair,on=['epri_scenario','aqueduct_scenario'],how='inner',validate='many_to_one')
    compare=dynamic.merge(expected,on=KEYS,validate='one_to_one',suffixes=('','_source'))
    assert len(compare)==len(dynamic)==len(expected)
    columns=['site_count','projected_energy_mwh','annual_co2_metric_tonnes','cumulative_co2_metric_tonnes',
        'annual_direct_water_m3','cumulative_direct_water_m3','annual_water_footprint_m3',
        'annual_water_scarcity_footprint_m3_eq','median_aqueduct_water_stress','max_aqueduct_water_stress',
        'median_aqueduct_water_depletion','median_temperature_mean_c','median_warmest_day_mean_c','unique_population_within_5km']
    for col in columns:np.testing.assert_allclose(compare[col],compare[col+'_source'],equal_nan=True,rtol=1e-10)
    assert dynamic.huc8.str.fullmatch(r'\d{8}').all()
    assert set(dynamic.year)==set(range(2023,2031))
    assert dynamic.groupby(['huc8','screening_scenario']).year.nunique().eq(8).all()
    return columns


def weight_stability(central):
    fields=['crpi_equal','crpi_water_focused','crpi_community_focused','crpi_carbon_focused']
    long=central.melt(id_vars=['huc8'],value_vars=fields,var_name='weight_scheme',value_name='score')
    result=rank_robustness(long,'score','weight_scheme',fields)
    result=result.rename(columns={f'rank_{name}':'rank_'+name.replace('crpi_','') for name in fields})
    result=result.rename(columns={'top10_all_scenarios':'top10_all_weight_schemes','top25pct_all_scenarios':'top25pct_all_weight_schemes'})
    return result


def build_dashboard(features,clusters,central_crpi,hotspots,robustness):
    dashboard=features.merge(clusters[['huc8','cluster_id','cluster_label','PC1','PC2']],on='huc8',how='left',validate='one_to_one')
    dashboard=dashboard.merge(central_crpi[['huc8','crpi_equal','crpi_water_focused','crpi_community_focused','crpi_carbon_focused','crpi_status']],on='huc8',how='left',validate='one_to_one')
    dashboard=dashboard.merge(hotspots[['huc8','hotspot_category']],on='huc8',how='left',validate='one_to_one')
    stable=robustness[robustness.metric=='WSF'][['huc8','top25pct_all_scenarios','rank_range']]
    stable=stable.rename(columns={'top25pct_all_scenarios':'scenario_robust','rank_range':'wsf_scenario_rank_range'})
    dashboard=dashboard.merge(stable,on='huc8',how='left',validate='one_to_one')
    dashboard['scenario_robust_definition']='WSF top quartile in all three paired scenarios, common complete cohort'
    aliases={'energy_growth_pct_2023_2030':'energy_growth_pct','annual_co2_2030':'co2_2030',
        'cumulative_co2_2023_2030':'cumulative_co2','annual_direct_water_2030_m3':'direct_water_2030',
        'water_footprint_2030_m3':'wf_2030','water_scarcity_footprint_2030_m3_eq':'wsf_2030',
        'aqueduct_water_stress_median':'aqueduct_stress','aqueduct_water_depletion_median':'aqueduct_depletion',
        'temperature_mean_2030_c':'temperature_2030','temperature_change_2023_2030_c':'temperature_change'}
    return dashboard.rename(columns=aliases)


def lower_pressure(central_features,central_crpi):
    index=central_features.merge(central_crpi[['huc8','crpi_equal','crpi_water_focused','crpi_community_focused','crpi_carbon_focused']],on='huc8',validate='one_to_one')
    metrics=['water_scarcity_footprint_2030_m3_eq','aqueduct_water_stress_median','annual_co2_2030','crpi_equal']
    complete=index[metrics].notna().all(axis=1)&index.co2_energy_coverage.ge(.8)&index.wsf_energy_coverage.ge(.8)
    cuts={col:float(index.loc[complete,col].quantile(.25)) for col in metrics}
    mask=complete.copy()
    for col,value in cuts.items():mask&=index[col]<=value
    selected=index[mask].copy()
    selected['interpretation']='Comparatively lower-pressure watersheds under modeled criteria; not recommended or safe development sites'
    selected['not_evaluated']='grid availability;land use;permitting;latency;water rights;economic feasibility;biodiversity;local infrastructure'
    return selected,cuts


def run_analysis():
    data,paths=read_inputs()
    dynamic=aggregate_profiles(data['states'],data['unique_pop'])
    aggregation_checks=verify_aggregation(dynamic,data['huc'])
    dynamic.to_csv(OUT/'huc8_dynamic_profiles_2023_2030.csv',index=False)
    features=feature_table(dynamic)
    X,enriched,preprocessing,correlations,pre_meta=preprocess(features)
    enriched.to_csv(OUT/'huc8_ml_features_2030.csv',index=False)
    preprocessing.to_csv(OUT/'huc8_ml_preprocessing_report.csv',index=False)
    correlations.to_csv(OUT/'huc8_feature_correlations.csv',index=False)
    X.assign(huc8=enriched.loc[X.index,'huc8']).to_csv(OUT/'huc8_clustering_matrix_2030.csv',index=False)
    clusters,scores,loadings,variance,diagnostics,profiles,cluster_meta=cluster_and_pca(X,enriched)
    for frame,name in [(clusters,'huc8_clusters_2030'),(scores,'huc8_pca_scores'),(loadings,'huc8_pca_loadings'),
                       (variance,'huc8_pca_explained_variance'),(diagnostics,'huc8_cluster_diagnostics'),(profiles,'huc8_cluster_profiles')]:
        frame.to_csv(OUT/(name+'.csv'),index=False)
    hotspots,hotspot_meta=hotspot_trajectories(dynamic)
    hotspots.to_csv(OUT/'huc8_hotspot_trajectory_2023_2030.csv',index=False)
    hotspots[hotspots.hotspot_category=='emerging_hotspot'].sort_values('wsf_absolute_change',ascending=False).to_csv(OUT/'huc8_top_emerging_hotspots.csv',index=False)
    all_crpi,weights,index_meta=crpi(dynamic)
    central_crpi=all_crpi[all_crpi.screening_scenario=='central'].copy()
    central_crpi.to_csv(OUT/'huc8_crpi_2030.csv',index=False)
    all_crpi.to_csv(OUT/'huc8_crpi_scenario_sensitivity_2030.csv',index=False)
    weights.to_csv(OUT/'crpi_weight_schemes.csv',index=False)
    stability=weight_stability(central_crpi)
    stability.to_csv(OUT/'huc8_crpi_weight_rank_stability.csv',index=False)
    stable=stability[stability.top25pct_all_weight_schemes.fillna(False)|stability.top10_all_weight_schemes.fillna(False)]
    stable.merge(central_crpi,on='huc8',validate='one_to_one').to_csv(OUT/'huc8_crpi_robust_hotspots.csv',index=False)
    rankings=[]
    end=dynamic[dynamic.year==2030]
    for metric,col in [('WF','annual_water_footprint_m3'),('WSF','annual_water_scarcity_footprint_m3_eq')]:
        ranks=rank_robustness(end[['huc8','screening_scenario',col]],col);ranks['metric']=metric;rankings.append(ranks)
    ranks=rank_robustness(all_crpi[['huc8','screening_scenario','crpi_equal']],'crpi_equal');ranks['metric']='CRPI_equal';rankings.append(ranks)
    robustness=pd.concat(rankings,ignore_index=True)
    robustness.to_csv(OUT/'huc8_scenario_rank_robustness.csv',index=False)
    lower,lower_cuts=lower_pressure(features,central_crpi)
    lower.to_csv(OUT/'huc8_lower_pressure_candidates.csv',index=False)
    dashboard=build_dashboard(enriched,clusters,central_crpi,hotspots,robustness)
    dashboard.to_csv(OUT/'huc8_dashboard_data.csv',index=False)
    unique(dashboard,['huc8'],'dashboard');assert len(dashboard)==dynamic.huc8.nunique()
    assert 'huc8' not in X and all(c in SHORTLIST for c in X)
    assert np.isfinite(X.to_numpy()).all()
    np.testing.assert_allclose(X.mean(),0,atol=1e-10);np.testing.assert_allclose(X.std(ddof=0),1,atol=1e-10)
    assert scores.shape[0]==len(X) and loadings.shape[0]==X.shape[1]
    assert diagnostics[diagnostics.chosen].size_eligible.all()
    assert dashboard.loc[~dashboard.ml_eligible,'cluster_id'].isna().all()
    for col in [c for c in central_crpi if c.startswith('crpi_') and c!='crpi_status']:
        assert central_crpi[col].dropna().between(0,100).all()
    assert np.allclose(weights.groupby('scheme').weight.sum(),1)
    top={}
    for pc in ['PC1','PC2']:
        series=loadings.set_index('feature')[pc]
        top[pc]=dict(positive=series[series>0].nlargest(3).to_dict(),negative=series[series<0].nsmallest(3).to_dict())
        print(pc,'top positive:',top[pc]['positive'],'top negative:',top[pc]['negative'],flush=True)
    summary=dict(huc8_count=len(features),dynamic_rows=len(dynamic),preprocessing=pre_meta,clustering=cluster_meta,
        explained_variance=variance.to_dict('records'),dominant_loadings=top,hotspots=hotspot_meta,
        hotspot_counts=hotspots.hotspot_category.value_counts().to_dict(),
        lower_pressure_count=len(lower),lower_pressure_thresholds=lower_cuts,crpi_robust_count=len(stable),
        crpi_complete_count=int(central_crpi.crpi_equal.notna().sum()),
        scenario_robust_counts=robustness.groupby('metric').top25pct_all_scenarios.sum().to_dict(),
        crpi=index_meta,aggregation_checks=aggregation_checks,seed=42,
        package_versions={name:importlib.metadata.version(name) for name in ['numpy','pandas','scipy','scikit-learn','geopandas']},
        input_sha256={str(path.relative_to(ROOT)):sha(path) for path in paths.values()},
        code_sha256={str(path.relative_to(ROOT)):sha(path) for path in [Path(__file__),ROOT/'src/model/huc8_profiles.py']},
        created_utc=datetime.now(timezone.utc).isoformat(),
        constraints='No supervised target, causal mechanism inference, harm probability, exposed-population label or development recommendation',
        scenarios={key:dict(epri=value[0],aqueduct=value[1],nasa='SSP2-4.5',n_models=1) for key,value in PAIRS.items()})
    (OUT/'huc8_analysis_metadata.json').write_text(json.dumps(summary,indent=2,default=lambda v:v.item() if isinstance(v,np.generic) else str(v))+'\n')
    print('HUC8 analytical tables validated:',len(features),'watersheds;',len(X),'eligible for clustering.',flush=True)
    return summary


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tables-only',action='store_true')
    args=parser.parse_args();run_analysis()
    if not args.tables_only:
        from src.visualization.plot_huc8_profiles import main as figures
        figures()


if __name__=='__main__':main()
