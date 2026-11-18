"""Static presentation figures; no MP4/GIF or implied environmental feedback."""
from pathlib import Path
import textwrap

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
FIGURES=ROOT/'outputs/figures'
SCENARIOS={
    'lower_pressure':('Lower: EPRI low / Aqueduct optimistic','#009E73'),
    'central_2030_screening':('Central: EPRI moderate / Aqueduct BAU','#0072B2'),
    'higher_pressure':('Higher: EPRI higher / Aqueduct pessimistic','#D55E00'),
}
FOOTNOTE='Mapped site records; scenario estimates, not measured national totals. NASA SSP2-4.5 is held fixed.'


def save(fig,name,footnote=FOOTNOTE):
    caption=textwrap.fill(footnote,width=int(fig.get_figwidth()*14))
    fig.text(.5,.012,caption,ha='center',va='bottom',fontsize=8)
    fig.tight_layout(rect=(0,.105,1,1))
    for extension in ('png','pdf'):
        fig.savefig(FIGURES/f'{name}.{extension}',dpi=220)
    plt.close(fig)


def scenario_lines(ax,data,column,scale=1):
    for key,(label,color) in SCENARIOS.items():
        part=data[data.presentation_scenario.eq(key)].sort_values('year')
        ax.plot(part.year,part[column]/scale,color=color,label=label,marker='o',markersize=4)
    ax.set_xlabel('Year')
    ax.set_xticks(range(2023,2031))
    ax.grid(alpha=.2)


def main():
    FIGURES.mkdir(parents=True,exist_ok=True)
    data=pd.read_csv(ROOT/'outputs/stateful_community_resource_summary_2023_2030.csv')
    with plt.rc_context({'font.size':10,'axes.spines.top':False,'axes.spines.right':False}):
        fig,ax=plt.subplots(figsize=(10,5.7))
        scenario_lines(ax,data,'total_projected_energy_mwh',1e6)
        ax.set(title='Annual modeled electricity demand, 2023–2030',ylabel='Annual electricity demand (TWh/year)')
        ax.legend(loc='upper left',frameon=False,fontsize=9)
        save(fig,'figure9a_stateful_energy_2023_2030')

        fig,ax=plt.subplots(figsize=(10,5.7))
        scenario_lines(ax,data,'cumulative_co2_metric_tonnes',1e6)
        ax.set(title='Cumulative electricity-related CO2, 2023–2030',ylabel='Cumulative CO2 (million metric tonnes)')
        ax.legend(loc='upper left',frameon=False,fontsize=9)
        save(fig,'figure9b_cumulative_co2_2023_2030',
             'Fixed eGRID 2023 factors. Cumulative accounting starts with the annual 2023 amount. '+FOOTNOTE)

        fig,axes=plt.subplots(1,2,figsize=(12,5.7))
        scenario_lines(axes[0],data,'annual_direct_water_m3',1e6)
        scenario_lines(axes[1],data,'cumulative_direct_water_m3',1e9)
        axes[0].set(title='Annual modeled direct demand',ylabel='Direct water demand (million m³/year)')
        axes[1].set(title='Cumulative modeled direct demand',ylabel='Cumulative direct water demand (billion m³)')
        axes[0].legend(loc='upper left',frameon=False,fontsize=8)
        fig.suptitle('Modeled direct data-center water demand, 2023–2030',fontsize=14)
        save(fig,'figure9c_direct_water_2023_2030',
             'Siddik supplementary workflow: 1.8 m³/MWh. Cumulative demand is accounting, not permanent watershed depletion.')

        central=data[data.presentation_scenario.eq('central_2030_screening')].sort_values('year')
        fig,axes=plt.subplots(1,3,figsize=(14,5.5))
        axes[0].plot(central.year,central.total_projected_energy_mwh/1e6,color='#0072B2',marker='o')
        axes[0].set(title='Resource demand: EPRI moderate',ylabel='Annual electricity demand (TWh/year)')
        axes[1].plot(central.year,central.median_aqueduct_water_stress,color='#D55E00',marker='o')
        axes[1].set(title='Background watershed stress: BAU',ylabel='Median Aqueduct raw water-stress ratio')
        axes[2].plot(central.year,central.median_temperature_mean_c,color='#0072B2',marker='o',label='Mean temperature')
        axes[2].plot(central.year,central.median_warmest_day_mean_c,color='#D55E00',marker='o',label='Warmest-day mean')
        axes[2].set(title='Background climate: SSP2-4.5',ylabel='Median projected temperature (°C)')
        axes[2].legend(frameon=False,fontsize=8)
        for ax in axes:
            ax.set_xlabel('Year');ax.set_xticks([2023,2025,2027,2030]);ax.grid(alpha=.2)
        fig.suptitle('Central screening trajectory: resource demand and external environmental conditions',fontsize=14)
        save(fig,'figure9d_resource_climate_trajectory',
             'Aqueduct intermediate years are screening interpolation, not official annual WRI forecasts. NASA: one model; no emissions-to-climate feedback.')
    print('Created figure9a–9d as PNG and PDF.',flush=True)


if __name__=='__main__':main()
