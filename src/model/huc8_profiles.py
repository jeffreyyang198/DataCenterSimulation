"""Unsupervised HUC8 profiles and explicitly normative screening comparisons.

No environmental-harm target is fitted. Raw burdens, external conditions and
community proximity remain distinct; missing physical quantities are not zero.
"""
from __future__ import annotations

import math
import os
os.environ.setdefault('LOKY_MAX_CPU_COUNT','1')
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score,calinski_harabasz_score,davies_bouldin_score

PAIRS={'lower_pressure':('low','optimistic'),'central':('moderate','business_as_usual'),
       'higher_pressure':('higher','pessimistic')}
KEYS=['huc8','year','screening_scenario']
SEED=42
SHORTLIST=['energy_2030_mwh','scarcity_intensity_m3_eq_per_mwh','carbon_intensity_tonnes_per_mwh',
    'energy_growth_pct_2023_2030','prop_sites_high_water_stress','unique_population_within_5km',
    'temperature_mean_2030_c','temperature_change_2023_2030_c']
FRIENDLY={
    'energy_2030_mwh':'electricity demand',
    'scarcity_intensity_m3_eq_per_mwh':'scarcity-weighted intensity',
    'carbon_intensity_tonnes_per_mwh':'electricity carbon intensity',
    'energy_growth_pct_2023_2030':'demand growth',
    'prop_sites_high_water_stress':'high-stress site share',
    'unique_population_within_5km':'nearby population',
    'temperature_mean_2030_c':'background temperature',
    'temperature_change_2023_2030_c':'projected temperature change',
}
DIMENSIONS=['water_burden','watershed_stress','carbon_burden','growth_pressure','population_context','climate_context']
WEIGHTS={
    'equal_weight':[1/6]*6,
    'water_focused':[.35,.25,.10,.10,.10,.10],
    'community_focused':[.15,.15,.10,.10,.40,.10],
    'carbon_focused':[.10,.10,.40,.15,.15,.10],
}


def unique(frame,keys,name):
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError(f'{name}: missing or duplicate identifiers')


def aggregate_profiles(states,unique_pop):
    unique(states,['site_id','year','epri_scenario','aqueduct_scenario'],'site simulation')
    pairs=pd.DataFrame([dict(screening_scenario=name,epri_scenario=e,aqueduct_scenario=a) for name,(e,a) in PAIRS.items()])
    selected=states.merge(pairs,on=['epri_scenario','aqueduct_scenario'],how='inner',validate='many_to_one')
    selected=selected[selected.huc8.notna()].copy()
    if not selected.nasa_scenario.eq('SSP2-4.5').all() or not selected.n_models.eq(1).all():
        raise ValueError('Expected the validated single-model SSP2-4.5 context')
    selected['risk_known']=selected.aqueduct_water_stress.notna()
    selected['high_stress']=selected.risk_known&(selected.aqueduct_water_stress>=.4)
    selected['extreme_stress']=selected.risk_known&(selected.aqueduct_water_stress>=.8)
    selected['co2_covered_energy_mwh']=selected.projected_energy_mwh.where(selected.annual_co2_metric_tonnes.notna())
    selected['wsf_covered_energy_mwh']=selected.projected_energy_mwh.where(selected.annual_water_scarcity_footprint_m3_eq.notna())
    grouped=selected.groupby(KEYS,sort=True)
    sumcols=['projected_energy_mwh','annual_co2_metric_tonnes','cumulative_co2_metric_tonnes',
        'annual_direct_water_m3','cumulative_direct_water_m3','annual_water_footprint_m3',
        'annual_water_scarcity_footprint_m3_eq','co2_covered_energy_mwh','wsf_covered_energy_mwh']
    result=grouped[sumcols].sum(min_count=1)
    result=result.join(grouped.agg(site_count=('site_id','nunique'),modeled_sites=('projected_energy_mwh','count'),
        co2_modeled_sites=('annual_co2_metric_tonnes','count'),wsf_modeled_sites=('annual_water_scarcity_footprint_m3_eq','count'),
        median_aqueduct_water_stress=('aqueduct_water_stress','median'),max_aqueduct_water_stress=('aqueduct_water_stress','max'),
        median_aqueduct_water_depletion=('aqueduct_water_depletion','median'),
        median_temperature_mean_c=('temperature_mean_c','median'),median_warmest_day_mean_c=('warmest_day_mean_c','median'),
        known_stress_sites=('risk_known','sum'),high_stress_sites=('high_stress','sum'),extreme_stress_sites=('extreme_stress','sum'),
        population_incomplete_site_count=('incomplete_pop_5km','sum'),pfaf_count=('pfaf_id','nunique'))).reset_index()
    denom=result.known_stress_sites.replace(0,np.nan)
    result['proportion_sites_high_water_stress']=result.high_stress_sites/denom
    result['proportion_sites_extremely_high_water_stress']=result.extreme_stress_sites/denom
    result['stress_site_coverage']=result.known_stress_sites/result.site_count
    for name in ['co2','wsf']:
        result[name+'_energy_coverage']=result[name+'_covered_energy_mwh']/result.projected_energy_mwh.where(result.projected_energy_mwh>0)
    context=unique_pop[unique_pop.group_type=='huc8'][['group_id','unique_population_within_5km']].rename(columns={'group_id':'huc8'})
    unique(context,['huc8'],'dissolved population')
    result=result.merge(context,on='huc8',how='left',validate='many_to_one')
    result['nasa_scenario']='SSP2-4.5';result['n_models']=1
    result['population_scope']='Static ACS 2019–2023; dissolved group buffers; nonadditive across HUC8 groups'
    unique(result,KEYS,'HUC8 dynamic profiles')
    if result.groupby('huc8').unique_population_within_5km.nunique(dropna=False).gt(1).any():
        raise ValueError('Population changed across years/scenarios')
    return result


def feature_table(profiles,scenario='central'):
    subset=profiles[profiles.screening_scenario==scenario]
    start=subset[subset.year==2023].set_index('huc8');end=subset[subset.year==2030].set_index('huc8')
    if set(start.index)!=set(end.index):raise ValueError('Endpoint HUC8 inventories differ')
    result=pd.DataFrame(index=end.index)
    names={
        'projected_energy_mwh':'energy_2030_mwh','annual_co2_metric_tonnes':'annual_co2_2030',
        'cumulative_co2_metric_tonnes':'cumulative_co2_2023_2030','annual_direct_water_m3':'annual_direct_water_2030_m3',
        'cumulative_direct_water_m3':'cumulative_direct_water_2023_2030_m3',
        'annual_water_footprint_m3':'water_footprint_2030_m3','annual_water_scarcity_footprint_m3_eq':'water_scarcity_footprint_2030_m3_eq',
        'median_aqueduct_water_stress':'aqueduct_water_stress_median','max_aqueduct_water_stress':'aqueduct_water_stress_max',
        'median_aqueduct_water_depletion':'aqueduct_water_depletion_median',
        'proportion_sites_high_water_stress':'prop_sites_high_water_stress',
        'proportion_sites_extremely_high_water_stress':'prop_sites_extremely_high_water_stress',
        'median_temperature_mean_c':'temperature_mean_2030_c','median_warmest_day_mean_c':'warmest_day_mean_2030_c',
        'unique_population_within_5km':'unique_population_within_5km','site_count':'site_count',
        'co2_energy_coverage':'co2_energy_coverage','wsf_energy_coverage':'wsf_energy_coverage',
        'stress_site_coverage':'stress_site_coverage','population_incomplete_site_count':'population_incomplete_site_count'}
    for source,target in names.items():result[target]=end[source]
    result['energy_growth_pct_2023_2030']=(end.projected_energy_mwh/start.projected_energy_mwh.where(start.projected_energy_mwh>0)-1)*100
    result['temperature_change_2023_2030_c']=end.median_temperature_mean_c-start.median_temperature_mean_c
    # Matched numerators/denominators prevent missing-coefficient sites diluting intensity.
    result['scarcity_intensity_m3_eq_per_mwh']=(end.annual_water_scarcity_footprint_m3_eq/
        end.wsf_covered_energy_mwh.where(end.wsf_covered_energy_mwh>0)).where(end.wsf_energy_coverage>=.8)
    result['carbon_intensity_tonnes_per_mwh']=(end.annual_co2_metric_tonnes/
        end.co2_covered_energy_mwh.where(end.co2_covered_energy_mwh>0)).where(end.co2_energy_coverage>=.8)
    return result.reset_index()


def preprocess(features,redundancy_threshold=.97):
    quality=['co2_energy_coverage','wsf_energy_coverage','stress_site_coverage','population_incomplete_site_count']
    columns=[c for c in features if c not in ['huc8']+quality]
    eligible=(features.energy_2030_mwh>0)&features.scarcity_intensity_m3_eq_per_mwh.notna()
    eligible&=features.population_incomplete_site_count.eq(0)&features.stress_site_coverage.ge(.8)
    eligible&=features[SHORTLIST].isna().mean(axis=1).le(.25)
    if eligible.sum()<12:raise ValueError('Insufficient assessable HUC8 profiles for clustering')
    transformed=features.loc[eligible,columns].astype(float).replace([np.inf,-np.inf],np.nan)
    transforms={}
    resource_tokens=('energy_2030','annual_co2','cumulative_co2','annual_direct','cumulative_direct','water_footprint',
                     'water_scarcity','scarcity_intensity','carbon_intensity','unique_population','site_count')
    for col in columns:
        series=transformed[col]
        if col.startswith(('aqueduct_water_stress_median','aqueduct_water_stress_max')):
            # Raw 9999 belongs to WRI's open-ended extreme category, not a precise ratio.
            values=series.to_numpy();category=np.digitize(values,[.1,.2,.4,.8]).astype(float)
            category[~np.isfinite(values)|(values<0)]=np.nan
            transformed[col]=category;transforms[col]='WRI raw-ratio category 0–4 (correlation/profile only)'
        elif col.startswith(resource_tokens) and series.dropna().ge(0).all() and series.skew()>1:
            transformed[col]=np.log1p(series);transforms[col]='log1p'
        else:transforms[col]='identity'
    correlation=transformed.corr(method='pearson')
    raw_spearman=features.loc[eligible,columns].corr(method='spearman')
    selected=[];reasons={};partners={}
    for col in SHORTLIST:
        series=transformed[col].dropna()
        near_constant=series.empty or (series.max()-series.min()<=1e-10*max(float(series.abs().max()),1.))
        if col=='energy_growth_pct_2023_2030' and not series.empty and series.max()-series.min()<.01:
            reasons[col]='insufficient practical growth variation (<0.01 percentage points)';continue
        if transformed[col].notna().mean()<.5 or near_constant:
            reasons[col]='insufficient variation/coverage';continue
        matches=[x for x in selected if abs(correlation.loc[col,x])>=redundancy_threshold]
        if matches:
            reasons[col]='extreme redundancy with retained feature';partners[col]=matches[0]
        else:selected.append(col)
    if len(selected)<3:raise ValueError('Fewer than three usable independent feature dimensions')
    medians=transformed.median()
    imputed=transformed.fillna(medians)
    scaler=StandardScaler()
    X=pd.DataFrame(scaler.fit_transform(imputed[selected]),columns=selected,index=imputed.index)
    report=[]
    mechanical={'annual_direct_water_2030_m3':'energy_2030_mwh',
        'cumulative_direct_water_2023_2030_m3':'annual_direct_water_2030_m3',
        'cumulative_co2_2023_2030':'annual_co2_2030','warmest_day_mean_2030_c':'temperature_mean_2030_c'}
    for col in columns:
        raw=features[col];before=features.loc[eligible,col]
        all_after=imputed[col];sd=all_after.std(ddof=0)
        standardized=(all_after-all_after.mean())/sd if sd>0 else pd.Series(0. if all_after.notna().any() else np.nan,index=all_after.index)
        partner=partners.get(col,mechanical.get(col,''))
        reason=reasons.get(col,'retained: distinct profile dimension' if col in selected else
            'profile only: balanced dimension set avoids repeated totals/cumulative proxies')
        if col not in selected and partner and abs(correlation.loc[col,partner])>=redundancy_threshold:
            reason='profile only: extreme redundancy / shared accounting basis'
        report.append(dict(feature=col,missing_count=int(raw.isna().sum()),missing_fraction=float(raw.isna().mean()),
            ml_cohort_missing_count=int(before.isna().sum()),transform_applied=transforms[col],
            median_imputation_transformed=float(medians[col]),mean_before=raw.mean(),std_before=raw.std(ddof=0),
            mean_after=standardized.mean(),std_after=standardized.std(ddof=0),
            selected_for_clustering=col in selected,selection_reason=reason,redundancy_with=partner,
            transformed_correlation_with_partner=correlation.loc[col,partner] if partner else np.nan))
    missing=transformed[selected].isna()
    result=features.copy();result['ml_eligible']=eligible
    result['ml_imputed_feature_count']=np.nan;result.loc[eligible,'ml_imputed_feature_count']=missing.sum(axis=1)
    result['ml_imputed_features']='';result.loc[eligible,'ml_imputed_features']=missing.apply(lambda r:';'.join(r.index[r]),axis=1)
    result['ml_status']=np.where(eligible,'eligible','insufficient resource/coverage data; not classified as low pressure')
    pairs=[]
    for a in columns:
        for b in columns:
            pairs.append(dict(feature_a=a,feature_b=b,pearson_transformed=correlation.loc[a,b],spearman_raw=raw_spearman.loc[a,b],
                pairwise_count=int(transformed[[a,b]].notna().all(axis=1).sum()),
                extreme_redundancy=bool(abs(correlation.loc[a,b])>=redundancy_threshold) if a!=b else False))
    metadata=dict(selected_features=selected,eligible_rows=int(eligible.sum()),excluded_rows=int((~eligible).sum()),
        redundancy_threshold=redundancy_threshold,imputation='Per-feature transformed median within eligible HUC8s, ML matrix only',
        transforms={c:transforms[c] for c in selected},imputation_medians={c:float(medians[c]) for c in selected},
        scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),
        selection='Balanced dimensions: demand, matched-cohort intensities, growth, stress, proximity, climate. No identifier or target feature.')
    metadata['practical_growth_resolution_percentage_points']=.01
    metadata['raw_growth_range_percentage_points']=[float(features.energy_growth_pct_2023_2030.min()),float(features.energy_growth_pct_2023_2030.max())]
    return X,result,pd.DataFrame(report),pd.DataFrame(pairs),metadata


def cluster_and_pca(X,features):
    minimum=max(5,math.ceil(.05*len(X)))
    diagnostics=[];models={}
    for k in range(2,min(8,len(X)-1)+1):
        model=KMeans(n_clusters=k,random_state=SEED,n_init=50,algorithm='lloyd').fit(X)
        labels=model.labels_;sizes=np.bincount(labels,minlength=k)
        diagnostics.append(dict(k=k,silhouette_score=silhouette_score(X,labels),inertia=model.inertia_,
            calinski_harabasz=calinski_harabasz_score(X,labels),davies_bouldin=davies_bouldin_score(X,labels),
            minimum_cluster_size=int(sizes.min()),required_minimum_size=minimum,size_eligible=bool(sizes.min()>=minimum)))
        models[k]=model
    table=pd.DataFrame(diagnostics)
    candidates=table[table.size_eligible]
    if candidates.empty:raise ValueError('No tested cluster count meets the minimum-size criterion')
    best=candidates.silhouette_score.max()
    k=int(candidates[candidates.silhouette_score>=best-.02].k.min())
    table['chosen']=table.k.eq(k)
    original=models[k].labels_
    ranks=pd.DataFrame({'algorithmic':original,'energy':features.loc[X.index,'energy_2030_mwh']}).groupby('algorithmic').energy.median().sort_values()
    remap={int(old):new for new,old in enumerate(ranks.index)}
    labels=pd.Series([remap[int(x)] for x in original],index=X.index,name='cluster_id')
    pca=PCA(n_components=min(X.shape),svd_solver='full')
    components=pca.fit_transform(X)
    scores=pd.DataFrame(components,index=X.index,columns=[f'PC{i+1}' for i in range(components.shape[1])])
    scores.insert(0,'huc8',features.loc[X.index,'huc8'])
    scores['cluster']=labels;scores['cluster_id']=labels;scores['algorithmic_cluster_id']=original
    loadings=pd.DataFrame(pca.components_.T,index=X.columns,columns=[f'PC{i+1}' for i in range(components.shape[1])]).rename_axis('feature').reset_index()
    variance=pd.DataFrame({'component':scores.filter(regex=r'^PC\d+$').columns,
        'explained_variance_ratio':pca.explained_variance_ratio_,'cumulative_explained_variance':np.cumsum(pca.explained_variance_ratio_)})
    names={};zmeans=X.groupby(labels).mean()
    for cluster,row in zmeans.iterrows():
        positive=row.sort_values(ascending=False);negative=row.sort_values()
        descriptions=[]
        if positive.iloc[0]>.25:descriptions.append('Higher '+FRIENDLY[positive.index[0]])
        if negative.iloc[0]<-.25:descriptions.append('lower '+FRIENDLY[negative.index[0]])
        names[int(cluster)]=' / '.join(descriptions) if descriptions else 'Near-cohort-average profile'
    scores['cluster_label']=scores.cluster_id.map(names)
    clusters=features.merge(scores,on='huc8',how='left',validate='one_to_one')
    clusters['cluster_label']=clusters.cluster_label.fillna('Insufficient resource/coverage data')
    profiles=[]
    for cluster,indices in labels.groupby(labels).groups.items():
        for col in [c for c in features if c not in ['huc8','ml_status','ml_imputed_features'] and pd.api.types.is_numeric_dtype(features[c])]:
            profiles.append(dict(cluster_id=int(cluster),cluster_label=names[int(cluster)],huc8_count=len(indices),feature=col,
                raw_median=features.loc[indices,col].median(),standardized_mean=X.loc[indices,col].mean() if col in X else np.nan))
    metadata=dict(chosen_k=k,random_state=SEED,n_init=50,
        rule='Smallest size-eligible k within 0.02 silhouette of the best size-eligible k; ≥5 HUC8s and ≥5% cohort per cluster',
        label_mapping=remap,cluster_labels=names,cluster_sizes={int(c):int(n) for c,n in labels.value_counts().sort_index().items()})
    return clusters,scores,loadings,variance,table,pd.DataFrame(profiles),metadata


def significant_round(values,digits=10):
    """Suppress floating-point ranking artifacts; raw source quantities unchanged."""
    values=pd.Series(values,dtype=float)
    absolute=values.abs().where(values.abs()>0,1.)
    scales=10.**(digits-1-np.floor(np.log10(absolute)))
    return (values*scales).round()/scales


def normalize_reference(values,reference,absolute_tolerance=0.):
    """Fixed-reference tied midrank percentiles, 0–100; no missing-as-zero."""
    ref=significant_round(reference).dropna()
    values=significant_round(values)
    if ref.empty:return pd.Series(np.nan,index=values.index)
    if ref.nunique()==1 or ref.max()-ref.min()<=absolute_tolerance:
        constant=ref.median()
        return pd.Series(np.where(values.isna(),np.nan,np.where(values<constant-absolute_tolerance,0.,np.where(values>constant+absolute_tolerance,100.,50.))),index=values.index)
    ranks=(ref.rank(method='average')-1)/(len(ref)-1)*100
    knots=pd.DataFrame({'value':ref,'percentile':ranks}).groupby('value').percentile.mean()
    result=pd.Series(np.interp(values,knots.index,knots.to_numpy(),left=0,right=100),index=values.index)
    return result.where(values.notna())


def crpi(profiles):
    dims=[]
    for scenario in PAIRS:
        feature=feature_table(profiles,scenario).set_index('huc8')
        result=pd.DataFrame(index=feature.index)
        result['water_burden']=feature.water_scarcity_footprint_2030_m3_eq.where(feature.wsf_energy_coverage>=.8)
        result['watershed_stress']=feature.prop_sites_high_water_stress.where(feature.stress_site_coverage>=.8)
        result['carbon_burden']=feature.annual_co2_2030.where(feature.co2_energy_coverage>=.8)
        result['growth_pressure']=feature.energy_growth_pct_2023_2030
        result['population_context']=feature.unique_population_within_5km.where(feature.population_incomplete_site_count.eq(0))
        result['climate_context']=feature.warmest_day_mean_2030_c
        result['screening_scenario']=scenario;dims.append(result.reset_index())
    values=pd.concat(dims,ignore_index=True)
    reference=values[values.screening_scenario=='central']
    normalized=values.copy();refs={}
    for dimension in DIMENSIONS:
        normalized[dimension]=normalize_reference(values[dimension],reference[dimension],absolute_tolerance=.01 if dimension=='growth_pressure' else 0.)
        refs[dimension]=reference[dimension].dropna().tolist()
    complete=normalized[DIMENSIONS].notna().all(axis=1)
    for name,weights in WEIGHTS.items():
        if not np.isclose(sum(weights),1):raise ValueError('CRPI weights must sum to one')
        output='crpi_equal' if name=='equal_weight' else 'crpi_'+name
        normalized[output]=(normalized[DIMENSIONS]*np.asarray(weights)).sum(axis=1,min_count=6).where(complete)
    normalized['crpi_status']=np.where(complete,'complete six-dimension screening index','missing dimension/coverage; index not calculated')
    schemes=pd.DataFrame([dict(scheme=name,dimension=dimension,weight=float(weight)) for name,weights in WEIGHTS.items() for dimension,weight in zip(DIMENSIONS,weights)])
    return normalized,schemes,dict(normalization='Fixed central-2030 tied-midrank reference, 0–100; interpolation/clipping outside reference range',
        references=refs,missing='All six dimensions required; no index imputation or missing-weight redistribution',
        interpretation='Analyst-defined screening index, not an observed harm measure, probability or supervised target',
        climate='Warmest-day background temperature is a context choice, not a validated vulnerability dose-response')


def rank_robustness(values,value_column,scenario_column='screening_scenario',scenarios=None):
    scenarios=scenarios or ['lower_pressure','central','higher_pressure']
    unique(values,['huc8',scenario_column],'ranking inputs')
    wide=values.pivot(index='huc8',columns=scenario_column,values=value_column).reindex(columns=scenarios)
    complete=wide.notna().all(axis=1)
    ranked=wide.loc[complete].apply(significant_round).rank(ascending=False,method='min')
    result=pd.DataFrame(index=wide.index)
    for name in scenarios:result['rank_'+name]=ranked[name]
    columns=['rank_'+name for name in scenarios]
    result['rank_min']=result[columns].min(axis=1);result['rank_max']=result[columns].max(axis=1)
    result['rank_range']=result.rank_max-result.rank_min
    result['top10_all_scenarios']=result[columns].le(10).all(axis=1).astype('boolean').where(complete)
    result['top25pct_all_scenarios']=result[columns].le(math.ceil(.25*complete.sum())).all(axis=1).astype('boolean').where(complete)
    result['comparison_cohort_size']=int(complete.sum())
    result['ranking_status']=np.where(complete,'common complete cohort','missing scenario; unranked')
    result=result.rename(columns={'rank_lower_pressure':'rank_lower','rank_higher_pressure':'rank_higher'})
    return result.reset_index()


def hotspot_trajectories(profiles):
    central=profiles[profiles.screening_scenario=='central']
    baseline=central[central.year==2023].set_index('huc8');future=central[central.year==2030].set_index('huc8')
    result=pd.DataFrame(index=future.index)
    fields={'energy':'projected_energy_mwh','direct_water':'annual_direct_water_m3','wf':'annual_water_footprint_m3',
            'wsf':'annual_water_scarcity_footprint_m3_eq','aqueduct_stress':'median_aqueduct_water_stress'}
    for name,col in fields.items():
        result[name+'_2023']=baseline[col];result[name+'_2030']=future[col]
        result[name+'_absolute_change']=future[col]-baseline[col]
        result[name+'_change_pct']=(future[col]/baseline[col].where(baseline[col]>0)-1)*100
        result[name+'_change_percentile']=normalize_reference(result[name+'_absolute_change'],result[name+'_absolute_change'])
    # Do not interpret an open-ended extreme source value as a precise finite change.
    capped=(result.aqueduct_stress_2023>=9999)|(result.aqueduct_stress_2030>=9999)
    result['aqueduct_stress_change_censored']=capped
    for col in ['aqueduct_stress_absolute_change','aqueduct_stress_change_pct','aqueduct_stress_change_percentile']:
        result.loc[capped,col]=np.nan
    pool=pd.concat([baseline.annual_water_scarcity_footprint_m3_eq,future.annual_water_scarcity_footprint_m3_eq],ignore_index=True).dropna()
    cutoff=float(pool.quantile(.75))
    change_cutoff=float(result.wsf_absolute_change.quantile(.75))
    result['pressure_2023_percentile']=normalize_reference(result.wsf_2023,pool)
    result['pressure_2030_percentile']=normalize_reference(result.wsf_2030,pool)
    valid=result[['wsf_2023','wsf_2030','wsf_absolute_change']].notna().all(axis=1)
    high23=result.wsf_2023>=cutoff;high30=result.wsf_2030>=cutoff;high_change=result.wsf_absolute_change>=change_cutoff
    result['persistent_high_burden']=high23&high30
    result['hotspot_category']='not_assessable'
    result.loc[valid,'hotspot_category']='lower_pressure'
    result.loc[valid&~high23&high30,'hotspot_category']='rising_watchlist'
    result.loc[valid&high23,'hotspot_category']='existing_constrained'
    result.loc[valid&high23&high30&high_change,'hotspot_category']='persistent_hotspot'
    result.loc[valid&~high23&high30&high_change,'hotspot_category']='emerging_hotspot'
    return result.reset_index(),dict(pressure_metric='Annual scarcity-weighted water footprint only; not a new opaque composite',
        pressure_reference='Pooled central 2023 and 2030 values, fixed for both endpoints',pressure_q75_m3_eq=cutoff,
        change_metric='Absolute 2023–2030 WSF increase',change_q75_m3_eq=change_cutoff,
        rules=dict(persistent_hotspot='High at both endpoints AND increase ≥ change q75',
            emerging_hotspot='Below high at baseline, high in 2030 AND increase ≥ change q75',
            existing_constrained='High baseline burden, but not persistent high-and-high-change subtype',
            rising_watchlist='Newly high in 2030 but below high-change threshold',lower_pressure='Below high-pressure endpoint criteria',
            not_assessable='Missing required WSF endpoint; never classified as lower pressure'),
        caveat='Existing-constrained is a modeled burden label, not measured local water-supply constraint. All five metric changes are reported separately; population change is not invented.')
