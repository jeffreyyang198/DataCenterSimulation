"""Presentation animation of existing screening outputs; no simulation equations.

Run: python3 -m src.visualization.animate_resource_pressure
The MP4 uses installed FFmpeg, or installed macOS AVFoundation via a small
local helper. Neither path installs software. Dashboard values always step to
actual annual outputs; only the playback progress strip moves between them.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import geopandas as gpd
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/animations'
CACHE=OUT/'.cache'
YEARS=list(range(2023,2031))
FPS=24
DURATION=36
SCENARIO='central_2030_screening'
COLORS=['#eee5cf','#e6ca91','#dba367','#c67749','#963f36']
BG='#f7f6f2'; INK='#243337'; BLUE='#216478'; MUTED='#617074'
CATEGORY_NAMES=['Low','Low-medium','Medium-high','High','Extremely high']
METRICS={
    'projected_energy_mwh':('Electricity demand',1e6,'TWh/year'),
    'annual_co2_metric_tonnes':('Annual CO₂',1e6,'million metric tonnes/year'),
    'cumulative_co2_metric_tonnes':('Cumulative CO₂',1e6,'million metric tonnes'),
    'annual_direct_water_m3':('Direct water · annual',1e6,'million m³/year'),
    'cumulative_direct_water_m3':('Direct water · cumulative',1e9,'billion m³ · accounting'),
    'annual_water_footprint_m3':('Water footprint',1e9,'billion m³/year'),
    'annual_water_scarcity_footprint_m3_eq':('Scarcity-weighted WF',1e9,'billion m³-eq/year'),
    'unique_population_within_5km':('Population within 5 km\nof mapped sites',1e6,'million · static ACS context'),
}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def central(frame):
    return frame[(frame.epri_scenario=='moderate')&(frame.aqueduct_scenario=='business_as_usual')].copy()


def validate_frames(frames):
    if frames.year.isna().any() or frames.year.duplicated().any():
        raise ValueError('Missing or duplicate animation years')
    if frames.year.tolist()!=YEARS:
        raise ValueError('Animation years must be ordered exactly 2023–2030')
    if not frames.epri_scenario.eq('moderate').all() or not frames.aqueduct_scenario.eq('business_as_usual').all():
        raise ValueError('Animation must use the central screening scenario')
    if not frames.presentation_scenario.eq(SCENARIO).all():raise ValueError('Incorrect presentation scenario')
    if frames.unique_population_within_5km.nunique(dropna=False)!=1:
        raise ValueError('Population must remain constant')
    for name in ['cumulative_co2_metric_tonnes','cumulative_direct_water_m3']:
        if frames[name].isna().any() or frames[name].diff().dropna().lt(-1e-6).any():
            raise ValueError('Cumulative amounts must be known and nondecreasing')
    if frames[list(METRICS)].isna().any().any():raise ValueError('Missing displayed national metric')


def extract_metrics(row):
    return {name:float(row[name])/scale for name,(_,scale,_) in METRICS.items()}


def stress_category(values):
    """WRI raw-ratio thresholds; no-data stays separate, 9999 maps to category 4."""
    values=np.asarray(values,dtype=float)
    result=np.digitize(values,[.1,.2,.4,.8]).astype(int)
    result[~np.isfinite(values)|(values<0)]=-1
    return result


def select_hotspots(huc,site2030,limit=5):
    work=huc.copy()
    known=site2030.aqueduct_water_stress.notna()
    quality=site2030.assign(risk_known=known,high_stress=known&(site2030.aqueduct_water_stress>=.4))
    grouped=quality.groupby('huc8').agg(risk_known=('risk_known','sum'),
        high_count=('high_stress','sum'),records=('site_id','size'),
        incomplete_population=('incomplete_pop_5km','any'),pfaf_count=('pfaf_id','nunique'))
    grouped['risk_coverage']=grouped.risk_known/grouped.records
    grouped['high_stress_proportion']=grouped.high_count/grouped.risk_known.replace(0,np.nan)
    work=work.merge(grouped,on='huc8',how='left',validate='one_to_one')
    eligible=work[work.annual_water_footprint_m3.notna()&work.unique_population_within_5km.notna()
                  &~work.incomplete_population.fillna(True)&(work.risk_coverage>=.8)]
    wf_cut=float(eligible.annual_water_footprint_m3.quantile(.75))
    pop_cut=float(eligible.unique_population_within_5km.quantile(.75))
    selected=eligible[(eligible.annual_water_footprint_m3>=wf_cut)
        &(eligible.unique_population_within_5km>=pop_cut)&(eligible.median_aqueduct_water_stress>=.4)]
    selected=selected.sort_values(['annual_water_footprint_m3','unique_population_within_5km','huc8'],ascending=[False,False,True]).head(limit)
    if selected.empty:raise ValueError('No HUC8 meets the documented hotspot criteria')
    method=dict(group='HUC8',eligible_groups=len(eligible),wf_q75_m3_year=wf_cut,population_q75=pop_cut,
        median_stress_minimum=.4,risk_coverage_minimum=.8,exclude_incomplete_population=True,
        selection='WF ≥ q75 AND unique nearby population ≥ q75 AND median raw stress ≥ 0.4',
        ranking='Annual WF descending, then unique population descending; HUC8 breaks ties. No composite score.',
        population='Dissolved 5-km buffers within HUC8; nonadditive between HUC8 groups',
        risk='Median, maximum and proportion of known site contexts ≥0.4 retained; no arbitrary PFAF assignment')
    return selected,method


def select_contrast(huc):
    valid=huc.dropna(subset=['annual_water_scarcity_footprint_m3_eq','unique_population_within_5km']).copy()
    low=float(valid.unique_population_within_5km.quantile(.25))
    high=float(valid.unique_population_within_5km.quantile(.75))
    a=valid[valid.unique_population_within_5km<=low].sort_values('annual_water_scarcity_footprint_m3_eq',ascending=False).head(1)
    b=valid[valid.unique_population_within_5km>=high].sort_values('annual_water_scarcity_footprint_m3_eq',ascending=False).head(1)
    if a.empty or b.empty or a.huc8.iloc[0]==b.huc8.iloc[0]:raise ValueError('No supported population contrast')
    result=pd.concat([a,b],ignore_index=True)
    result['contrast_role']=['High WSF / lower nearby population','High WSF / larger nearby population']
    result['wsf_rank']=result.huc8.map(valid.set_index('huc8').annual_water_scarcity_footprint_m3_eq.rank(ascending=False,method='min'))
    result['population_rank']=result.huc8.map(valid.set_index('huc8').unique_population_within_5km.rank(ascending=False,method='min'))
    return result,dict(method='Highest WSF within the bottom population quartile versus highest WSF within the top population quartile',
                       population_q25=low,population_q75=high,hard_coded_huc8_ids=False)


def load_inputs():
    provenance=json.loads((ROOT/'outputs/stateful_simulation_provenance.json').read_text())
    paths={
        'states':ROOT/'outputs/stateful_community_resource_simulation_2023_2030.csv',
        'summary':ROOT/'outputs/stateful_community_resource_summary_2023_2030.csv',
        'huc':ROOT/'outputs/stateful_huc8_resource_simulation_2023_2030.csv',
        'aqueduct':ROOT/'outputs/stateful_aqueduct_resource_simulation_2023_2030.csv',
        'frames':ROOT/'outputs/simulation_animation_frames_2023_2030.csv',
        'master':ROOT/'data/processed/master_sites.csv',
        'huc_mapping':ROOT/'data/processed/master_sites_with_huc8.csv',
        'aqueduct_mapping':ROOT/'data/processed/site_aqueduct_basins.csv',
        'population':ROOT/'data/processed/community_exposure_acs2023.csv',
        'nasa':ROOT/provenance['climate_path'],
        'unique_population':ROOT/'data/processed/stateful_unique_population_5km.csv',
    }
    use=['site_id','state_abbr','longitude','latitude','year','huc8','pfaf_id','epri_scenario','aqueduct_scenario',
         'nasa_scenario','n_models','projected_energy_mwh','annual_co2_metric_tonnes','cumulative_co2_metric_tonnes',
         'annual_direct_water_m3','cumulative_direct_water_m3','annual_water_footprint_m3',
         'annual_water_scarcity_footprint_m3_eq','aqueduct_water_stress','temperature_mean_c',
         'warmest_day_mean_c','pop_5km','incomplete_pop_5km']
    data={}
    for name,path in paths.items():
        frame=pd.read_csv(path,usecols=use if name=='states' else None,
            dtype={'site_id':str,'huc8':str,'pfaf_id':str,'group_id':str})
        print(f'SELECTED {name}: {path.resolve()}\n  columns: {list(frame.columns)}',flush=True)
        data[name]=frame
    states=central(data['states']);frames=data['frames']
    validate_frames(frames)
    if states.duplicated(['site_id','year']).any():raise ValueError('Duplicate central site-year rows')
    if not states.groupby('site_id').year.nunique().eq(8).all():raise ValueError('Incomplete site-year inventory')
    if not states.nasa_scenario.eq('SSP2-4.5').all() or not states.n_models.eq(1).all():raise ValueError('Unexpected NASA scenario/model count')
    if not states.groupby('site_id').pop_5km.nunique(dropna=False).eq(1).all():raise ValueError('Site population changed')
    master=data['master'].set_index('site_id')
    if set(states.site_id)!=set(master.index):raise ValueError('Site inventory differs from master')
    np.testing.assert_allclose(states[['longitude','latitude']],master.loc[states.site_id,['longitude','latitude']],rtol=0,atol=1e-10)
    summary=central(data['summary']).sort_values('year')
    for col in METRICS:
        name='total_projected_energy_mwh' if col=='projected_energy_mwh' else col
        np.testing.assert_allclose(frames[col],summary[name],equal_nan=True,rtol=1e-10)
        if col!='unique_population_within_5km':
            totals=states.groupby('year')[col].sum(min_count=1)
            np.testing.assert_allclose(frames[col],totals,equal_nan=True,rtol=1e-10)
    for col in ['aqueduct_water_stress','temperature_mean_c','warmest_day_mean_c']:
        np.testing.assert_allclose(frames['median_'+col],states.groupby('year')[col].median(),rtol=1e-10)
    unique=data['unique_population']
    national=unique[(unique.group_type=='national')&(unique.group_id=='all')].unique_population_within_5km.iloc[0]
    np.testing.assert_allclose(frames.unique_population_within_5km,national)
    huc=central(data['huc']);huc=huc[huc.year==2030]
    for col in ['projected_energy_mwh','annual_direct_water_m3','annual_water_footprint_m3','annual_water_scarcity_footprint_m3_eq']:
        actual=states[states.year==2030].groupby('huc8')[col].sum(min_count=1)
        np.testing.assert_allclose(huc.set_index('huc8')[col].sort_index(),actual.sort_index(),equal_nan=True,rtol=1e-10)
    context=unique[unique.group_type=='huc8'].set_index('group_id')
    np.testing.assert_allclose(huc.unique_population_within_5km,context.loc[huc.huc8].unique_population_within_5km)
    data['states']=states;data['huc2030']=huc
    return data,paths


def state_outlines():
    files=sorted((ROOT/'data/raw/census/tiger2023').rglob('tl_2023_*_tract.shp'))
    if not files:raise FileNotFoundError('Existing TIGER 2023 geometry is required for the basemap')
    files=[p for p in files if re.search(r'tl_2023_(\d{2})_tract',p.stem).group(1) not in {'02','15','60','66','69','78'}]
    signatures={str(p.relative_to(ROOT)):[p.stat().st_size,p.stat().st_mtime_ns] for p in files}
    cache=ROOT/'data/processed/animation_state_outlines.gpkg';meta=cache.with_suffix('.json')
    if cache.exists() and meta.exists() and json.loads(meta.read_text())['source_signatures']==signatures:
        return gpd.read_file(cache),json.loads(meta.read_text())
    rows=[]
    for path in files:
        code=re.search(r'tl_2023_(\d{2})_tract',path.stem).group(1)
        frame=gpd.read_file(path,columns=[])
        merged=frame.geometry.make_valid().union_all()
        simple=gpd.GeoSeries([merged],crs=frame.crs).to_crs(5070).simplify(1800).to_crs(4326).iloc[0]
        rows.append(dict(state_fips=code,geometry=simple))
        print('Basemap: dissolved TIGER state',code,flush=True)
    result=gpd.GeoDataFrame(rows,crs=4326)
    result.to_file(cache,driver='GPKG',layer='state_outlines')
    metadata=dict(source_signatures=signatures,source='Existing TIGER 2023 tract polygons dissolved by state',
        simplification='1,800 m for national display only; simulation geometry unchanged',
        source_copy_manifest='data/raw/source_copy_manifest.json',source_copy_manifest_sha256=sha(ROOT/'data/raw/source_copy_manifest.json'))
    meta.write_text(json.dumps(metadata,indent=2)+'\n')
    return result,metadata


def marker_size(values):
    return 7+17*np.log1p(np.maximum(np.nan_to_num(values,nan=0),0)/10000)


class Renderer:
    def __init__(self,data,outlines,hotspots,contrast,method):
        self.data=data;self.outlines=outlines;self.hotspots=hotspots;self.contrast=contrast;self.method=method
        sites=data['states'][data['states'].year==2023]
        unsupported=set(sites.state_abbr)-set(data['master'].state_abbr)
        if unsupported or sites.state_abbr.isin(['AK','HI','AS','GU','MP','VI']).any():
            raise ValueError('Current map layout supports the actual CONUS/Puerto Rico inventory only')
        points=gpd.GeoDataFrame(sites[['site_id']].copy(),geometry=gpd.points_from_xy(sites.longitude,sites.latitude),crs=4326).to_crs(5070)
        self.xy=pd.DataFrame({'site_id':sites.site_id.to_numpy(),'x':points.geometry.x.to_numpy(),'y':points.geometry.y.to_numpy()}).set_index('site_id')
        self.land=outlines[outlines.state_fips!='72'].to_crs(5070)
        self.pr=outlines[outlines.state_fips=='72']
        self.frames=data['frames'].set_index('year')

    def figure(self,title,subtitle,stage,year=2030):
        fig=plt.figure(figsize=(19.2,10.8),dpi=100,facecolor=BG)
        fig.text(.035,.956,title,fontsize=27,weight='bold',color=INK,va='top')
        fig.text(.035,.909,subtitle,fontsize=14,color=MUTED)
        fig.text(.965,.944,str(year),fontsize=47,weight='bold',color=BLUE,ha='right',va='top')
        labels=['01  BASELINE','02  ANNUAL PROGRESSION','03  HUC8 HOTSPOTS','04  2030 SUMMARY']
        for i,(x,label) in enumerate(zip([.035,.215,.455,.69],labels)):
            fig.text(x,.866,label,fontsize=11.5,color=BLUE if i==stage else '#849092',weight='bold' if i==stage else 'normal')
        return fig

    def footer(self,fig,kind='annual'):
        if kind=='hotspot':
            a='HUC8 groups aggregate mapped records; nearby population is unique within each group but overlaps between groups.'
            b='Screening estimates, not measured national totals. Proximity does not establish direct exposure.'
        elif kind=='contrast':
            a='WSF is Siddik’s scarcity-weighted footprint, distinct from Aqueduct background stress. No composite score is used.'
            b='Population: static ACS 2019–2023. These HUC8 examples are selected from the current output, not hard-coded.'
        else:
            a='Scenario-based screening estimates; not measured national totals. Population: static ACS 2019–2023, dissolved 5-km buffers.'
            b='NASA SSP2-4.5: one model, external climate. Aqueduct intermediate years are interpolated, not official annual WRI forecasts.'
        fig.text(.035,.058,a,fontsize=11.7,color=MUTED)
        fig.text(.035,.033,b,fontsize=11.7,color=MUTED)
        if kind=='annual':fig.text(.035,.082,'Cumulative direct water is accounting across years, not permanent watershed depletion.',fontsize=11.7,color=MUTED)

    def map(self,fig,year,rect=(.035,.41,.575,.405),highlight=None):
        ax=fig.add_axes(rect,facecolor=BG)
        self.land.plot(ax=ax,facecolor='#eaece7',edgecolor='#aeb8b8',linewidth=.5)
        site=self.data['states'][self.data['states'].year==year].set_index('site_id').join(self.xy)
        conus=site[site.state_abbr!='PR']
        colors=np.array([COLORS[c] if c>=0 else '#9ba7a7' for c in stress_category(conus.aqueduct_water_stress)],dtype=object)
        known=conus.annual_direct_water_m3.notna()
        alpha=.55 if highlight is None else .16
        ax.scatter(conus.loc[known,'x'],conus.loc[known,'y'],s=marker_size(conus.loc[known,'annual_direct_water_m3']),
            c=colors[known],alpha=alpha,edgecolors='white',linewidths=.25,zorder=3)
        ax.scatter(conus.loc[~known,'x'],conus.loc[~known,'y'],s=14,facecolors='none',edgecolors='#718081',linewidths=.6,alpha=.6,zorder=2)
        if highlight is not None:
            for number,key in enumerate(highlight,1):
                part=conus[conus.huc8==key]
                ax.scatter(part.x,part.y,s=marker_size(part.annual_direct_water_m3)+12,facecolors='none',edgecolors=BLUE,linewidths=1.1,zorder=5)
                anchor=part.sort_values('annual_water_footprint_m3',ascending=False).iloc[0]
                offset=[(16,18),(18,-24),(-22,20),(-30,-24),(16,30)][(number-1)%5]
                ax.annotate(str(number),(anchor.x,anchor.y),xytext=offset,textcoords='offset points',fontsize=15,weight='bold',
                            color='white',bbox=dict(boxstyle='circle,pad=.25',facecolor=BLUE,edgecolor='white'),
                            arrowprops=dict(arrowstyle='-',color=BLUE,linewidth=.8),zorder=6)
        ax.set_axis_off();ax.set_aspect('equal')
        if not self.pr.empty and highlight is None:
            inset=fig.add_axes([rect[0]+.005,rect[1]+.025,.13,.085],facecolor=BG)
            self.pr.plot(ax=inset,facecolor='#eaece7',edgecolor='#aeb8b8',linewidth=.5)
            pr=site[site.state_abbr=='PR']
            inset.scatter(pr.longitude,pr.latitude,s=18,facecolors='none',edgecolors='#718081',linewidths=.8)
            inset.set_axis_off();inset.set_title('Puerto Rico (inset)',fontsize=10.5,color=MUTED)
        return ax

    def legend(self,fig):
        fig.text(.05,.393,'Color: Aqueduct stress category    |    Size: modeled direct water demand (log scale)',fontsize=12,color=INK)
        names=['Low <10%','10–20%','20–40%','High 40–80%','Extreme ≥80%']
        for i,(color,name) in enumerate(zip(COLORS,names)):
            x=.05+i*.111
            fig.add_artist(Rectangle((x,.362),.012,.013,transform=fig.transFigure,facecolor=color,edgecolor='none'))
            fig.text(x+.016,.362,name,fontsize=10.5,color=INK)
        fig.text(.05,.337,'Hollow gray: demand unavailable. Outlines: existing TIGER 2023 tracts dissolved by state.',fontsize=10.5,color=MUTED)

    def dashboard(self,fig,row):
        fig.text(.646,.817,'MODELED DEMAND & CUMULATIVE ACCOUNTING',fontsize=12,color=MUTED,weight='bold')
        metrics=extract_metrics(row)
        for index,(key,(label,_,unit)) in enumerate(METRICS.items()):
            col=index%2;r=index//2;x=.646+col*.163;y=.77-r*.111
            value=metrics[key]
            number=f'{value:,.1f}' if key not in ['cumulative_direct_water_m3','annual_water_footprint_m3','annual_water_scarcity_footprint_m3_eq','unique_population_within_5km'] else f'{value:,.2f}'
            fig.text(x,y,label,fontsize=12.3,color=INK)
            pop=key=='unique_population_within_5km'
            fig.text(x,y-(.059 if pop else .043),number,fontsize=26 if pop else 30,weight='bold',color=BLUE)
            fig.text(x,y-(.083 if pop else .066),unit,fontsize=10.6,color=MUTED)
        fig.text(.646,.325,'Direct-water coefficient: Siddik supplementary workflow, 1.8 m³/MWh.',fontsize=10.3,color=MUTED)

    def environment(self,fig,row):
        fig.text(.646,.283,'Background environmental context',fontsize=15,color=INK,weight='bold')
        fig.text(.646,.25,'Watershed stress',fontsize=11.8,color=MUTED)
        fig.text(.646,.205,f'{row.median_aqueduct_water_stress:.3f}',fontsize=27,color='#963f36',weight='bold')
        fig.text(.646,.179,'median raw ratio · external',fontsize=10.6,color=MUTED)
        fig.text(.81,.25,'Projected mean temperature',fontsize=11.3,color=MUTED)
        fig.text(.81,.205,f'{row.median_temperature_mean_c:.2f}°C',fontsize=27,color=BLUE,weight='bold')
        fig.text(.81,.179,'NASA SSP2-4.5 · 1 model',fontsize=10.6,color=MUTED)

    def annual(self,year,stage=1,final=False):
        row=self.frames.loc[year]
        title='2030 CENTRAL SCREENING SCENARIO' if final else 'U.S. DATA-CENTER RESOURCE PRESSURE'
        fig=self.figure(title,'Combined screening case: EPRI moderate · Aqueduct BAU · NASA SSP2-4.5 · static ACS population',3 if final else stage,year)
        fig.text(.05,.835,'2023 BASELINE' if stage==0 else f'{year} · actual annual simulation output',fontsize=15,color=INK,weight='bold')
        fig.text(.05,.811,f'{int(row.site_count):,} mapped records · {int(row.modeled_sites):,} energy / {int(row.co2_modeled_sites):,} CO₂ / {int(row.water_modeled_sites):,} WF estimates',fontsize=10.8,color=MUTED)
        self.map(fig,year);self.legend(fig);self.dashboard(fig,row);self.environment(fig,row)
        if final:
            fig.text(.05,.258,'Growing modeled demand may increasingly coincide',fontsize=19,color=INK,weight='bold')
            fig.text(.05,.219,'with water-constrained environments and large nearby populations.',fontsize=17,color=INK)
            fig.text(.05,.174,'Screening analysis; proximity does not establish direct exposure.',fontsize=15,color=BLUE)
        else:
            ax=fig.add_axes([.065,.15,.525,.14],facecolor=BG)
            values=self.data['frames'].projected_energy_mwh/1e6
            ax.plot(YEARS,values,color='#b8c3c5',linewidth=1.4,linestyle='--')
            mask=np.array(YEARS)<=year
            ax.plot(np.array(YEARS)[mask],values[mask],color=BLUE,linewidth=2.5)
            ax.scatter([year],[row.projected_energy_mwh/1e6],s=65,c=BLUE,zorder=4)
            ax.set(title='Annual electricity trajectory · displayed values step by year',ylabel='TWh/year',xticks=[2023,2026,2030],ylim=(0,math.ceil(values.max()/50)*50))
            ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.15);ax.tick_params(labelsize=10)
        self.footer(fig)
        return fig

    def hotspots_frame(self):
        fig=self.figure('2030 · HUC8 RESOURCE-PRESSURE HOTSPOTS','Transparent intersection of high modeled WF, high background stress, and large nearby population',2)
        ids=self.hotspots.huc8.tolist();self.map(fig,2030,(.035,.418,.575,.41),ids)
        fig.text(.645,.8,'SELECTION RULES',fontsize=16,color=BLUE,weight='bold')
        lines=[f'Water footprint ≥ top-quartile cutoff',f'{self.method["wf_q75_m3_year"]/1e6:.2f} million m³/year',
               'Nearby population ≥ top-quartile cutoff',f'{self.method["population_q75"]:,.0f} unique nearby residents',
               'Median stress ratio ≥ 0.40', 'At least 80% known stress contexts',
               'Rank qualifying HUC8 groups by annual WF.', 'No opaque composite score.']
        for i,line in enumerate(lines):fig.text(.645,.755-i*.038,line,fontsize=13.5,color=INK if i%2==0 else MUTED)
        fig.text(.05,.388,'Numbers identify HUC8 groups; callouts anchor at real site locations. Group stress is a median across sites.',fontsize=11.5,color=MUTED)
        for i,row in enumerate(self.hotspots.itertuples()):
            x=.035+i*.19;ax=fig.add_axes([x,.12,.178,.24]);ax.set_axis_off()
            ax.add_patch(Rectangle((0,0),1,1,transform=ax.transAxes,facecolor='white',edgecolor='#c8d0d0',linewidth=.8))
            category=CATEGORY_NAMES[int(stress_category([row.median_aqueduct_water_stress])[0])]
            lines=[(f'{i+1}  HUC8 {row.huc8}',15,BLUE),
                (f'{row.modeled_sites} modeled / {row.site_count} records',11.5,MUTED),
                (f'Energy  {row.projected_energy_mwh/1e6:.2f} TWh/y',13,INK),
                (f'Direct  {row.annual_direct_water_m3/1e6:.1f}M m³/y',13,INK),
                (f'WF  {row.annual_water_footprint_m3/1e6:.1f}M m³/y',13,INK),
                (f'Median stress: {category}',11.5,INK),
                (f'Nearby pop  {row.unique_population_within_5km:,.0f}',13,BLUE)]
            for j,(text,size,color) in enumerate(lines):ax.text(.045,.89-j*.133,text,fontsize=size,color=color,transform=ax.transAxes,weight='bold' if j in (0,6) else 'normal')
        self.footer(fig,'hotspot');return fig

    def contrast_frame(self):
        fig=self.figure('2030 · RESOURCE DEMAND AND COMMUNITY CONTEXT DIFFER','High resource demand ≠ high scarcity impact ≠ large nearby population',2)
        for i,row in enumerate(self.contrast.itertuples()):
            x=.045+i*.49
            fig.text(x,.795,row.contrast_role,fontsize=20,weight='bold',color=BLUE)
            fig.text(x,.745,f'HUC8 {row.huc8}',fontsize=24,weight='bold',color=INK)
            lines=[('Annual direct water',f'{row.annual_direct_water_m3/1e6:.2f} million m³/year'),
                   ('Annual total water footprint',f'{row.annual_water_footprint_m3/1e6:.2f} million m³/year'),
                   ('Annual scarcity-weighted WF',f'{row.annual_water_scarcity_footprint_m3_eq/1e9:.3f} billion m³-eq/year'),
                   ('Unique nearby population',f'{row.unique_population_within_5km:,.0f} residents within 5 km')]
            for j,(label,value) in enumerate(lines):
                y=.66-j*.115
                fig.text(x,y,label,fontsize=14,color=MUTED)
                fig.text(x,y-.047,value,fontsize=24,weight='bold',color=INK)
            fig.text(x,.165,f'WSF rank {int(row.wsf_rank)} · nearby-population rank {int(row.population_rank)}',fontsize=15,color=BLUE)
        self.footer(fig,'contrast');return fig


def save_figure(fig,path):
    fig.savefig(path,dpi=100,facecolor=BG)
    plt.close(fig)


def render_previews(renderer):
    deck={}
    path=OUT/'frame_2023.png';save_figure(renderer.annual(2023,stage=0),path);deck['opening']=path
    for year in YEARS:
        path=CACHE/f'annual_{year}.png';save_figure(renderer.annual(year),path);deck[str(year)]=path
        if year in [2026,2030]:shutil.copy2(path,OUT/f'frame_{year}.png')
    path=OUT/'frame_hotspots.png';save_figure(renderer.hotspots_frame(),path);deck['hotspots']=path
    path=OUT/'frame_contrast.png';save_figure(renderer.contrast_frame(),path);deck['contrast']=path
    path=OUT/'powerpoint_poster_frame.png';save_figure(renderer.annual(2030,final=True),path);deck['final']=path
    return deck


def key_at_time(t):
    if t<4:return 'opening'
    if t<20:return str(2023+min(7,int((t-4)//2)))
    if t<25:return 'hotspots'
    if t<30:return 'contrast'
    return 'final'


def composed_frame(images,t,width,height):
    image=images[key_at_time(t)].copy()
    if image.size!=(width,height):image=image.resize((width,height),Image.Resampling.LANCZOS)
    draw=ImageDraw.Draw(image)
    left,right=int(width*.035),int(width*.965);y=int(height*.987)
    draw.rectangle((left,y,right,y+max(3,height//270)),fill='#d7dfdf')
    draw.rectangle((left,y,left+int((right-left)*min(t/DURATION,1)),y+max(3,height//270)),fill=BLUE)
    return image


def native_encoder():
    source=Path(__file__).with_name('native_h264.swift')
    compiler=shutil.which('swiftc')
    if platform.system()!='Darwin' or not compiler:return None
    binary=CACHE/'native_h264';stamp=binary.with_suffix('.json')
    if binary.exists() and stamp.exists() and json.loads(stamp.read_text()).get('source_sha256')==sha(source):return binary
    sdk_root=Path('/Library/Developer/CommandLineTools/SDKs')
    sdks=sorted([p for p in sdk_root.glob('MacOSX*.sdk') if re.fullmatch(r'MacOSX\d+\.\d+\.sdk',p.name)],reverse=True)
    host_major=platform.mac_ver()[0].split('.')[0]
    sdks=sorted(sdks,key=lambda p:not p.name.startswith('MacOSX'+host_major+'.'))
    # Compile an immutable snapshot: workspace synchronization can update mtimes.
    snapshot=Path(tempfile.mkdtemp(prefix='resource-animation-swift-'))/'encoder.swift'
    snapshot.write_bytes(source.read_bytes())
    errors=[]
    for sdk in sdks+[None]:
        command=[compiler,'-suppress-warnings','-module-cache-path','/tmp/resource-animation-swift-cache']
        if sdk:command+=['-sdk',str(sdk)]
        command+=[str(snapshot),'-o',str(binary)]
        result=subprocess.run(command,capture_output=True,text=True)
        if result.returncode==0:
            stamp.write_text(json.dumps(dict(source_sha256=sha(source),sdk=str(sdk) if sdk else 'default')))
            return binary
        errors.append(result.stderr[-1200:])
    (CACHE/'native_compile_errors.txt').write_text('\n\n'.join(errors))
    return None


def write_video(images,width,height,fps):
    ffmpeg=shutil.which('ffmpeg')
    native=native_encoder() if not ffmpeg else None
    temporary=CACHE/'resource_pressure.partial.mp4'
    if temporary.exists():temporary.unlink()
    frames=int(DURATION*fps)
    if ffmpeg:
        command=[ffmpeg,'-y','-f','rawvideo','-pixel_format','bgra','-video_size',f'{width}x{height}',
            '-framerate',str(fps),'-i','-','-an','-c:v','libx264','-profile:v','main','-pix_fmt','yuv420p',
            '-crf','19','-movflags','+faststart',str(temporary)]
        encoder='Installed FFmpeg / libx264'
    elif native:
        command=[str(native),'encode',str(temporary),str(width),str(height),str(fps),str(frames),'6500000']
        encoder='Installed macOS AVFoundation / H.264 Main; FFmpeg unavailable'
    else:return None,dict(status='unavailable',reason='No installed FFmpeg or compatible native H.264 toolchain; no software installed')
    with (CACHE/'encode.log').open('wb') as log:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=log,stderr=log)
        try:
            for index in range(frames):
                image=composed_frame(images,index/fps,width,height)
                process.stdin.write(image.convert('RGBA').tobytes('raw','BGRA'))
                if index%(fps*4)==0:print(f'Encoding {index/fps:.0f}/{DURATION} seconds',flush=True)
            process.stdin.close();returncode=process.wait()
        except (BrokenPipeError,OSError):
            process.wait();raise RuntimeError('Video encoding failed; see '+str(CACHE/'encode.log'))
    if returncode!=0:raise RuntimeError('Video encoding failed; see '+str(CACHE/'encode.log'))
    verification=CACHE/'video_verification.json'
    verifier=native or native_encoder()
    if verifier:
        subprocess.run([str(verifier),'verify',str(temporary),str(verification)],check=True)
        report=json.loads(verification.read_text())
        if report['decoded_frames']!=frames or report['width']!=width or report['height']!=height or abs(report['duration_seconds']-DURATION)>.05:
            raise ValueError('Decoded video differs from requested dimensions/duration/frame count')
    else:
        probe=shutil.which('ffprobe')
        if not probe:raise RuntimeError('ffprobe is required to verify exported video on this platform')
        raw=json.loads(subprocess.check_output([probe,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(temporary)]))
        stream=next(x for x in raw['streams'] if x['codec_type']=='video')
        subprocess.run([ffmpeg,'-v','error','-i',str(temporary),'-f','null','-'],check=True)
        report=dict(status='passed',codec=stream['codec_name'],width=stream['width'],height=stream['height'],decoded_frames=int(stream['nb_read_frames']),duration_seconds=float(raw['format']['duration']),fps=fps)
    target=OUT/'data_center_resource_pressure_2023_2030.mp4'
    temporary.replace(target)
    return target,dict(encoder=encoder,**report)


def write_gif(images):
    fps=10;width,height=960,540
    first=composed_frame(images,0,width,height).convert('P',palette=Image.Palette.ADAPTIVE,colors=192)
    frames=[]
    for index in range(DURATION*fps):
        image=composed_frame(images,index/fps,width,height).convert('RGB').quantize(palette=first,dither=Image.Dither.NONE)
        frames.append(image)
    target=OUT/'data_center_resource_pressure_2023_2030.gif'
    frames[0].save(target,save_all=True,append_images=frames[1:],duration=100,loop=0,optimize=True,disposal=2)
    with Image.open(target) as check:
        count=check.n_frames;duration=0
        for index in range(count):check.seek(index);duration+=check.info.get('duration',0)
        if check.size!=(width,height) or abs(duration/1000-DURATION)>.1:raise ValueError('GIF dimensions/duration invalid')
    return target,dict(fps=fps,resolution=[width,height],frame_count=count,duration_seconds=duration/1000)


def print_completion(manifest):
    log=OUT/'animation_tests.txt'
    test_text=log.read_text() if log.exists() else ''
    passed=re.findall(r'(\d+) passed',test_text)
    tests=f'{passed[-1]} passed' if passed and not re.search(r'\d+ failed|FAILED|ERRORS',test_text) else 'Test suite has not passed; see animation_tests.txt'
    lines=['ANIMATED 2023–2030 SIMULATION COMPLETE','','Scenario:',
        'EPRI moderate','Aqueduct business_as_usual','NASA SSP2-4.5','Population ACS 2023',
        '','Years:','2023–2030','','Animation:',manifest['video'] or 'Unavailable; see codec limitation in manifest',
        '','GIF:',manifest['gif'] or 'unavailable','','Resolution:',f"{manifest['resolution'][0]} × {manifest['resolution'][1]}",
        '','Duration:',f"{manifest['duration_seconds']} seconds",'','FPS:',str(manifest['fps'])]
    for title,key in [('2023 baseline metrics:','baseline_metrics'),('2030 metrics:','final_metrics')]:
        lines.extend(['',title])
        values=extract_metrics(manifest[key])
        for name,(label,_,unit) in METRICS.items():lines.append(f"{label.replace(chr(10),' ')}: {values[name]:,.3f} {unit}")
        lines.append(f"Median Aqueduct raw stress: {manifest[key]['median_aqueduct_water_stress']:.6f}")
        lines.append(f"Median projected background temperature: {manifest[key]['median_temperature_mean_c']:.3f} °C")
    lines.extend(['','Hotspots displayed:',', '.join(manifest['hotspots_displayed']),
        'Contrast HUC8 groups: '+', '.join(manifest['contrast_huc8_ids']),'','Static preview frames:'])
    lines.extend(manifest['preview_frames'].values())
    lines.extend(['','Tests:',tests,'','Important caveats:',*['- '+c for c in manifest['important_caveats']],
        '','No software installed. No GitHub push. DataCenterSimulation/ unchanged.'])
    text='\n'.join(lines)+'\n'
    (OUT/'animation_completion.txt').write_text(text)
    print(text,flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--previews-only',action='store_true')
    parser.add_argument('--no-gif',action='store_true');parser.add_argument('--fps',type=int,default=FPS)
    parser.add_argument('--width',type=int,default=1920);parser.add_argument('--height',type=int,default=1080)
    args=parser.parse_args()
    if args.fps<=0 or args.width*9!=args.height*16 or args.width%2 or args.height%2:raise ValueError('Use positive FPS and even 16:9 video dimensions')
    OUT.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True)
    data,paths=load_inputs()
    site2030=data['states'][data['states'].year==2030]
    hotspots,method=select_hotspots(data['huc2030'],site2030)
    contrast,contrast_method=select_contrast(data['huc2030'])
    hotspots.to_csv(OUT/'hotspots_2030.csv',index=False);contrast.to_csv(OUT/'contrast_2030.csv',index=False)
    outlines,basemap=state_outlines()
    with plt.rc_context({'font.family':'DejaVu Sans','text.color':INK,'axes.labelcolor':MUTED,'axes.titlesize':12,'axes.titlecolor':INK}):
        renderer=Renderer(data,outlines,hotspots,contrast,method)
        deck=render_previews(renderer)
    if args.previews_only:
        print('Static animation previews created; video not yet encoded.',flush=True);return
    images={key:Image.open(path).convert('RGB') for key,path in deck.items()}
    try:
        video,verification=write_video(images,args.width,args.height,args.fps)
    except (RuntimeError,subprocess.CalledProcessError) as error:
        video=None;verification=dict(status='unavailable',reason=str(error),log=str(CACHE/'encode.log'))
        print('MP4 unavailable:',error,flush=True)
    gif,gif_info=(None,dict(status='not_requested')) if args.no_gif else write_gif(images)
    caveats=[
        'Scenario-based screening estimates; not measured or independently deduplicated national totals.',
        'Population held constant using ACS 2019–2023; national and HUC8 values use dissolved buffers; HUC8 populations are not additive.',
        'NASA SSP2-4.5 background projected climate conditions are external; n_models=1; no data-center-caused local warming is inferred.',
        'Aqueduct intermediate years are interpolated for visualization and are not official annual WRI forecasts; no data-center-caused stress is inferred.',
        'Cumulative modeled direct water demand is accounting, not permanent watershed depletion.',
        'Direct demand uses Siddik supplementary workflow 1.8 m3/MWh; WF and WSF remain separate; WSF is not multiplied by Aqueduct stress.',
        'HUC8 and PFAF are distinct; HUC8 risk is summarized across site contexts, not one arbitrarily assigned basin.',
        'Dashboard values step to actual annual outputs. Only playback progress moves between snapshots.',
        'Missing estimates are not zero; hollow gray markers identify unavailable modeled demand.',
        'Study inventory has CONUS and Puerto Rico sites; Puerto Rico inset has a separate scale.',
    ]
    manifest=dict(scenario=dict(name=SCENARIO,epri='moderate',aqueduct='business_as_usual',nasa='SSP2-4.5',n_models=1,population='ACS 2019–2023 static'),
        years=YEARS,source_files={name:dict(path=str(path.resolve()),sha256=sha(path),columns=list(data[name].columns)) for name,path in paths.items()},
        metrics_displayed={name:dict(label=label,scale=scale,unit=unit) for name,(label,scale,unit) in METRICS.items()},
        environmental_context=['median_aqueduct_water_stress','median_temperature_mean_c'],
        frame_count=DURATION*args.fps if video else gif_info.get('frame_count',0),
        fps=args.fps if video else gif_info.get('fps',0),duration_seconds=DURATION,
        resolution=[args.width,args.height] if video else gif_info.get('resolution',[args.width,args.height]),
        generation_date=datetime.now(timezone.utc).isoformat(),video=str(video) if video else None,
        video_verification=verification,gif=str(gif) if gif else None,gif_metadata=gif_info,
        stages=[dict(name='2023 baseline',start=0,end=4),dict(name='annual progression',start=4,end=20,seconds_per_year=2),
                dict(name='HUC8 hotspots and contrast',start=20,end=30,overview_seconds=5,contrast_seconds=5),dict(name='2030 summary',start=30,end=36)],
        hotspot_selection=method,contrast_selection=contrast_method,hotspots_displayed=hotspots.huc8.tolist(),
        contrast_huc8_ids=contrast.huc8.tolist(),basemap=basemap,
        map_encoding=dict(marker_size='7 + 17*log1p(direct_water_m3/10000), points squared',color='Raw stress categories at 0.1,0.2,0.4,0.8',
                          transparency=.55,hotspot_callout='Highest-WF real site coordinate within each highlighted HUC8'),
        preview_frames={key:str(OUT/f'frame_{key}.png' if key in ['2026','2030'] else path)
                        for key,path in deck.items() if key in ['opening','2026','2030','hotspots','contrast','final']},
        baseline_metrics=data['frames'].iloc[0].to_dict(),final_metrics=data['frames'].iloc[-1].to_dict(),
        important_caveats=caveats,data_validation='passed',test_log='animation_tests.txt',
        implementation_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),Path(__file__).with_name('native_h264.swift')]})
    (OUT/'animation_manifest.json').write_text(json.dumps(manifest,indent=2,default=lambda v:v.item() if isinstance(v,np.generic) else str(v))+'\n')
    print('Animation assets encoded and decoded successfully.' if video else 'GIF exported; MP4 unavailable.',flush=True)
    print_completion(manifest)


if __name__=='__main__':main()
