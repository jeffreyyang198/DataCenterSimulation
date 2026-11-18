"""Interpretation figures for the HUC8 analysis; use verified watershed polygons."""
from pathlib import Path
import json
import textwrap
import re
import tempfile
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import geopandas as gpd
import numpy as np
import pandas as pd

from src.model.huc8_profiles import FRIENDLY

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs';FIG=OUT/'figures'
PALETTE=['#216478','#d18b40','#6b638c','#4b806a','#ba6158','#7d714b','#6b9298','#9b7191']
CATEGORIES={'persistent_hotspot':('#216478','Persistent hotspot'),
    'emerging_hotspot':('#cc7335','Emerging hotspot'),'existing_constrained':('#7c6998','Existing high burden / lower change'),
    'rising_watchlist':('#78a8b8','Rising watchlist'),'lower_pressure':('#d4dddc','Below high-burden cutoffs'),
    'not_assessable':('#a5a8a8','Insufficient burden data')}
SHORT={
    'energy_2030_mwh':'Energy','energy_growth_pct_2023_2030':'Energy growth',
    'annual_co2_2030':'Annual CO2','cumulative_co2_2023_2030':'Cumulative CO2',
    'annual_direct_water_2030_m3':'Direct water','cumulative_direct_water_2023_2030_m3':'Cumulative direct',
    'water_footprint_2030_m3':'WF','water_scarcity_footprint_2030_m3_eq':'WSF',
    'aqueduct_water_stress_median':'Stress category (median)','aqueduct_water_stress_max':'Stress category (max)',
    'aqueduct_water_depletion_median':'Depletion','prop_sites_high_water_stress':'High-stress share',
    'prop_sites_extremely_high_water_stress':'Extreme-stress share','temperature_mean_2030_c':'Background temperature',
    'warmest_day_mean_2030_c':'Warmest-day mean','temperature_change_2023_2030_c':'Temperature change',
    'unique_population_within_5km':'Nearby population','site_count':'Site records',
    'scarcity_intensity_m3_eq_per_mwh':'Scarcity intensity','carbon_intensity_tonnes_per_mwh':'Carbon intensity'}


def save(fig,name,pdf=False,caption='Central screening scenario; modeled site-record profiles, not environmental-harm predictions.'):
    fig.text(.5,.014,textwrap.fill(caption,int(fig.get_figwidth()*15)),ha='center',va='bottom',fontsize=9,color='#566268')
    fig.tight_layout(rect=(0,.075,1,1))
    fig.savefig(FIG/(name+'.png'),dpi=220)
    if pdf:fig.savefig(FIG/(name+'.pdf'))
    plt.close(fig)


def boundaries(ids):
    path=ROOT/'data/processed/huc8_analysis_boundaries.gpkg'
    meta=path.with_suffix('.json');source=ROOT/'data/raw/siddik/SI_Shapefile.shp'
    signature=dict(source=str(source),size=source.stat().st_size,mtime=source.stat().st_mtime_ns,ids=sorted(ids))
    if path.exists() and meta.exists() and json.loads(meta.read_text())==signature:return gpd.read_file(path)
    if not all(re.fullmatch(r'\d{8}',s) for s in ids):raise ValueError('Invalid HUC8 polygon keys')
    where='HUC_8 IN ('+','.join("'"+s+"'" for s in ids)+')'
    # Read an unchanged scratch copy without legacy spatial-index sidecars.
    # This avoids slow workspace/network-drive seeks in a 324-MB shapefile.
    with tempfile.TemporaryDirectory(prefix='huc8-map-') as folder:
        scratch=Path(folder)/source.name
        for suffix in ['.shp','.shx','.dbf','.prj','.cpg']:
            original=source.with_suffix(suffix)
            if original.exists():shutil.copy2(original,scratch.with_suffix(suffix))
        frame=gpd.read_file(scratch,columns=['HUC_8'],where=where)
    frame=frame.rename(columns={'HUC_8':'huc8'})
    frame['huc8']=frame.huc8.astype(str).str.strip().str.zfill(8)
    frame=frame[frame.huc8.isin(ids)].copy()
    frame['geometry']=frame.geometry.make_valid()
    frame=frame.dissolve('huc8').reset_index().to_crs(5070)
    frame['geometry']=frame.geometry.simplify(500,preserve_topology=True)
    frame.to_file(path,layer='huc8',driver='GPKG')
    meta.write_text(json.dumps(signature,indent=2)+'\n')
    return frame


def map_base(ax):
    path=ROOT/'data/processed/animation_state_outlines.gpkg'
    if path.exists():
        states=gpd.read_file(path);states=states[states.state_fips!='72'].to_crs(5070)
        states.plot(ax=ax,facecolor='#f1f2ef',edgecolor='#c4cbcb',linewidth=.5)
    ax.set_axis_off();ax.set_aspect('equal')


def main():
    FIG.mkdir(parents=True,exist_ok=True)
    metadata=json.loads((OUT/'huc8_analysis_metadata.json').read_text())
    scores=pd.read_csv(OUT/'huc8_pca_scores.csv',dtype={'huc8':str})
    loadings=pd.read_csv(OUT/'huc8_pca_loadings.csv')
    variance=pd.read_csv(OUT/'huc8_pca_explained_variance.csv')
    clusters=pd.read_csv(OUT/'huc8_clusters_2030.csv',dtype={'huc8':str})
    profiles=pd.read_csv(OUT/'huc8_cluster_profiles.csv')
    diagnostics=pd.read_csv(OUT/'huc8_cluster_diagnostics.csv')
    correlations=pd.read_csv(OUT/'huc8_feature_correlations.csv')
    trajectory=pd.read_csv(OUT/'huc8_hotspot_trajectory_2023_2030.csv',dtype={'huc8':str})
    robust=pd.read_csv(OUT/'huc8_scenario_rank_robustness.csv',dtype={'huc8':str})
    with plt.rc_context({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False}):
        corr=correlations.pivot(index='feature_a',columns='feature_b',values='pearson_transformed')
        names=correlations.feature_a.drop_duplicates().tolist();corr=corr.reindex(index=names,columns=names)
        fig,ax=plt.subplots(figsize=(14,12));image=ax.imshow(corr,vmin=-1,vmax=1,cmap='RdBu_r')
        ax.set_xticks(range(len(names)),[SHORT.get(c,c) for c in names],rotation=65,ha='right',fontsize=9)
        ax.set_yticks(range(len(names)),[SHORT.get(c,c) for c in names],fontsize=9)
        ax.set_title('HUC8 candidate-feature correlations after documented transformations')
        fig.colorbar(image,ax=ax,shrink=.7,label='Pairwise-complete Pearson correlation')
        save(fig,'figure10a_huc8_feature_correlation',caption='Eligible HUC8 cohort; profile-only variables remain in this audit. Raw stress is categorized for this correlation view; raw Spearman correlations are exported separately.')

        fig,ax=plt.subplots(figsize=(8.5,5.5));ax.bar(variance.component,variance.explained_variance_ratio*100,color=PALETTE[0])
        ax.plot(variance.component,variance.cumulative_explained_variance*100,color=PALETTE[1],marker='o',label='Cumulative variance')
        ax.set(xlabel='Principal component',ylabel='Explained standardized variance (%)',title='PCA explained variance across retained profile dimensions',ylim=(0,105))
        ax.legend(frameon=False);save(fig,'figure10b_pca_explained_variance')

        xlab=f'PC1 ({variance.explained_variance_ratio.iloc[0]:.1%} of variance)'
        ylab=f'PC2 ({variance.explained_variance_ratio.iloc[1]:.1%} of variance)'
        fig,ax=plt.subplots(figsize=(9,6));ax.scatter(scores.PC1,scores.PC2,s=30,alpha=.65,color=PALETTE[0])
        ax.axhline(0,lw=.6,color='#c9cdcd');ax.axvline(0,lw=.6,color='#c9cdcd')
        ax.set(xlabel=xlab,ylabel=ylab,title='HUC8 profiles in the first two PCA dimensions')
        save(fig,'figure10c_huc8_pca_scatter',caption='PCA is descriptive. Component direction and meaning come from actual loadings; no vulnerability or causal-risk interpretation is assigned.')

        fig,axes=plt.subplots(1,2,figsize=(11,5.5))
        for mask,color,label in [(diagnostics.size_eligible,PALETTE[0],'Meets minimum size'),(~diagnostics.size_eligible,'#a0a8aa','Creates small cluster')]:
            axes[0].scatter(diagnostics.loc[mask,'k'],diagnostics.loc[mask,'silhouette_score'],c=color,label=label,s=60)
        axes[0].plot(diagnostics.k,diagnostics.silhouette_score,color='#c0c8c8',zorder=0)
        axes[1].plot(diagnostics.k,diagnostics.inertia,marker='o',color=PALETTE[0])
        for ax in axes:ax.axvline(metadata['clustering']['chosen_k'],color=PALETTE[1],ls='--');ax.set_xlabel('Cluster count k');ax.set_xticks(diagnostics.k)
        axes[0].set(ylabel='Silhouette score',title='Separation and minimum-size eligibility');axes[0].legend(frameon=False,fontsize=9)
        axes[1].set(ylabel='Within-cluster squared distance (inertia)',title='Inertia / elbow diagnostic')
        save(fig,'figure10d_cluster_diagnostics',caption=metadata['clustering']['rule']+'. Dashed line marks the selected k; a size constraint is a transparent modeling choice, not proof of natural categories.')

        fig,ax=plt.subplots(figsize=(11,7))
        for cluster,group in scores.groupby('cluster_id'):
            label=f'C{int(cluster)} (n={len(group)}): '+group.cluster_label.iloc[0]
            ax.scatter(group.PC1,group.PC2,s=30,alpha=.75,color=PALETTE[int(cluster)],label=textwrap.fill(label,55))
        notable=clusters.dropna(subset=['cluster_id']).nlargest(2,'water_scarcity_footprint_2030_m3_eq').huc8.tolist()
        notable+=clusters.dropna(subset=['cluster_id']).nlargest(2,'unique_population_within_5km').huc8.tolist()
        for row in scores[scores.huc8.isin(set(notable))].itertuples():ax.annotate(row.huc8,(row.PC1,row.PC2),xytext=(5,6),textcoords='offset points',fontsize=9)
        ax.set(xlabel=xlab,ylabel=ylab,title='Unsupervised HUC8 clusters projected into PCA space')
        ax.legend(loc='upper left',bbox_to_anchor=(1.01,1),frameon=False,fontsize=9)
        save(fig,'figure10e_huc8_clusters_pca',caption='KMeans fits the full retained standardized matrix, not the two plotted PCs. Broad screening profiles are not causal mechanisms or harm categories.')

        chosen=metadata['preprocessing']['selected_features']
        z=profiles[profiles.feature.isin(chosen)].pivot(index='cluster_id',columns='feature',values='standardized_mean').reindex(columns=chosen)
        fig,ax=plt.subplots(figsize=(12,5.5));image=ax.imshow(z,aspect='auto',cmap='RdBu_r',vmin=-max(abs(z.to_numpy()).max(),1),vmax=max(abs(z.to_numpy()).max(),1))
        ax.set_xticks(range(len(chosen)),[textwrap.fill(SHORT.get(c,c),16) for c in chosen],fontsize=9)
        ax.set_yticks(range(len(z)),[f'C{int(c)} (n={metadata["clustering"]["cluster_sizes"][str(int(c))]})' for c in z.index])
        for i in range(len(z)):
            for j in range(len(chosen)):ax.text(j,i,f'{z.iloc[i,j]:+.2f}',ha='center',va='center',fontsize=10)
        ax.set_title('Observed cluster profiles: standardized feature means');fig.colorbar(image,ax=ax,label='Mean standard deviations from eligible-cohort average')
        save(fig,'figure10f_cluster_profiles',caption='Means are derived after fitting. Positive values indicate higher values of a feature, not greater environmental harm.')

        geometry=boundaries(set(clusters.huc8));mapped=geometry.merge(clusters[['huc8','cluster_id','cluster_label']],on='huc8',how='left',validate='one_to_one')
        fig,ax=plt.subplots(figsize=(14,8.5));map_base(ax)
        missing=mapped[mapped.cluster_id.isna()]
        if len(missing):missing.plot(ax=ax,facecolor='#b3b8b8',edgecolor='white',linewidth=.4)
        handles=[]
        for cluster,group in mapped.dropna(subset=['cluster_id']).groupby('cluster_id'):
            color=PALETTE[int(cluster)];group.plot(ax=ax,facecolor=color,edgecolor='white',linewidth=.4)
            handles.append(Patch(facecolor=color,label=textwrap.fill(f'C{int(cluster)}: '+group.cluster_label.iloc[0],45)))
        handles.append(Patch(facecolor='#b3b8b8',label='Analyzed; insufficient data for clustering'))
        ax.legend(handles=handles,loc='lower left',frameon=True,fontsize=9)
        ax.set_title('HUC8 watershed screening clusters · central 2030',fontsize=18)
        save(fig,'figure10g_huc8_cluster_map',pdf=True,caption=f'Actual Siddik-source HUC8 polygons; {len(geometry)}/{len(clusters)} profile groups mapped. Light background is outside the fitted sample, not lower pressure. Cluster separation is modest (silhouette {diagnostics.loc[diagnostics.chosen,"silhouette_score"].iloc[0]:.3f}).')

        fig,ax=plt.subplots(figsize=(10,7))
        for category,group in trajectory.groupby('hotspot_category'):
            if category=='not_assessable':continue
            color,label=CATEGORIES[category]
            ax.scatter(group.pressure_2023_percentile,group.pressure_2030_percentile,s=35,color=color,label=f'{label} (n={len(group)})',alpha=.8)
        ax.axhline(75,color='#6b7474',ls='--',lw=.8);ax.axvline(75,color='#6b7474',ls='--',lw=.8)
        for i,row in enumerate(trajectory[trajectory.hotspot_category=='emerging_hotspot'].itertuples()):
            ax.annotate(row.huc8,(row.pressure_2023_percentile,row.pressure_2030_percentile),xytext=(18,18+i*18),textcoords='offset points',fontsize=9,
                        arrowprops={'arrowstyle':'-','color':'#cc7335','lw':0.7},bbox={'facecolor':'white','edgecolor':'none','pad':1})
        ax.set(xlabel='2023 annual WSF · fixed pooled-reference percentile',ylabel='2030 annual WSF · same reference percentile',
               title='Persistent and emerging modeled scarcity-burden hotspots',xlim=(-2,102),ylim=(-2,102))
        ax.legend(frameon=False,fontsize=9,loc='upper left')
        save(fig,'figure11a_emerging_hotspots',caption='High burden uses the pooled 2023/2030 WSF upper quartile. Emerging/persistent hotspot subtypes also require upper-quartile absolute WSF increase. Missing burden endpoints are not lower pressure.')

        fig,axes=plt.subplots(1,3,figsize=(14,5))
        for ax,metric in zip(axes,['WF','WSF','CRPI_equal']):
            part=robust[robust.metric==metric].dropna(subset=['rank_central'])
            stable=part.top25pct_all_scenarios.fillna(False).astype(bool)
            ax.scatter(part.loc[~stable,'rank_central'],part.loc[~stable,'rank_range'],color='#aab5b6',s=23,alpha=.7,label='Other assessable groups')
            ax.scatter(part.loc[stable,'rank_central'],part.loc[stable,'rank_range'],color=PALETTE[0],s=30,label='Top quartile in all pairs')
            ax.set(title=metric.replace('_',' '),xlabel='Central rank (1 = largest metric)',ylabel='Rank range across three paired scenarios')
        axes[0].legend(frameon=False,fontsize=8)
        fig.suptitle('Scenario rank robustness: common complete cohorts')
        save(fig,'figure11b_scenario_rank_robustness',caption='Lower / central / higher pairings are screening combinations, not formally coupled pathways. Tied ranks use the minimum rank; missing scenario values remain unranked.')

        mapped=geometry.merge(trajectory[['huc8','hotspot_category']],on='huc8',how='left',validate='one_to_one')
        fig,ax=plt.subplots(figsize=(14,8.5));map_base(ax);handles=[]
        for category,(color,label) in CATEGORIES.items():
            group=mapped[mapped.hotspot_category==category]
            if group.empty:continue
            group.plot(ax=ax,facecolor=color,edgecolor='white',linewidth=.4)
            handles.append(Patch(facecolor=color,label=f'{label} (n={len(group)})'))
        emergent=mapped[mapped.hotspot_category=='emerging_hotspot']
        for i,row in enumerate(emergent.itertuples()):
            point=row.geometry.representative_point()
            ax.annotate(row.huc8,(point.x,point.y),xytext=(12,12+i*12),textcoords='offset points',fontsize=11,weight='bold',
                color='#9e4f23',bbox=dict(facecolor='white',edgecolor='none',alpha=.85,pad=2),arrowprops=dict(arrowstyle='-',color='#9e4f23'))
        ax.legend(handles=handles,loc='lower left',fontsize=10,frameon=True)
        ax.set_title('HUC8 environmental screening profiles · 2023 to 2030',fontsize=18)
        save(fig,'figure12_huc8_environmental_profiles',pdf=True,caption='Known modeled scarcity-burden trajectories, not environmental-harm predictions. Background watersheds outside the study sample are not assessed. Population is static proximity context; NASA and Aqueduct conditions remain external.')
    (OUT/'huc8_geometry_validation.json').write_text(json.dumps(dict(source='data/raw/siddik/SI_Shapefile.shp',
        source_key='HUC_8',profile_groups=len(clusters),mapped_groups=len(geometry),
        unmatched_huc8=sorted(set(clusters.huc8)-set(geometry.huc8)),
        display_simplification_m=500,model_geometry_changed=False),indent=2)+'\n')
    print('HUC8 figures created; mapped groups:',len(geometry),flush=True)


if __name__=='__main__':main()
