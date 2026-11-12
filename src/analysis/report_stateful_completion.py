"""Print the requested completion record only after validation/tests/figures pass."""
from pathlib import Path
import json
import re
import hashlib
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs'


def main():
    validation=json.loads((OUT/'stateful_simulation_validation.json').read_text())
    assert validation['status']=='passed'
    log=(OUT/'stateful_simulation_tests.txt').read_text()
    matches=re.findall(r'(\d+) passed',log)
    if not matches or re.search(r'\d+ failed|ERRORS|FAILED',log):
        raise ValueError('Final test suite has not passed')
    passed=int(matches[-1])
    summary=pd.read_csv(OUT/'stateful_community_resource_summary_2023_2030.csv')
    row=summary.loc[summary.presentation_scenario.eq('central_2030_screening')&summary.year.eq(2030)].iloc[0]
    files=[OUT/f'{name}_2023_2030.csv' for name in [
        'stateful_community_resource_simulation','stateful_community_resource_summary',
        'stateful_huc8_resource_simulation','stateful_aqueduct_resource_simulation','simulation_animation_frames']]
    files.extend(OUT/'figures'/f'{name}.{ext}' for name in [
        'figure9a_stateful_energy_2023_2030','figure9b_cumulative_co2_2023_2030',
        'figure9c_direct_water_2023_2030','figure9d_resource_climate_trajectory'] for ext in ['png','pdf'])
    assert all(p.is_file() for p in files)
    validation['test_suite']={'passed':passed,'failed':0,'log':'stateful_simulation_tests.txt'}
    review=json.loads((OUT/'stateful_figure_review.json').read_text())
    for relative,expected in review['sha256'].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==expected, 'Figure changed since visual review'
    validation['figure_review']=review['method']
    (OUT/'stateful_simulation_validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    lines=['STATEFUL 2023–2030 SIMULATION COMPLETE','','Central scenario:',
        'EPRI moderate','Aqueduct business_as_usual','NASA SSP2-4.5','Population ACS 2023',
        '','Years:','2023–2030','','Modeled sites:',
        f"{int(row.modeled_sites):,} energy; {int(row.co2_modeled_sites):,} CO2; {int(row.water_modeled_sites):,} WF/WSF; {validation['site_records']:,} retained",
        '','Site-year rows:',f"{validation['central_site_year_rows']:,} central; {validation['site_year_scenario_rows']:,} full sensitivity grid",
        '','Cumulative 2030 CO2:',f'{row.cumulative_co2_metric_tonnes:,.3f} metric tonnes',
        '','Cumulative 2030 direct water:',f'{row.cumulative_direct_water_m3:,.3f} m3',
        '','2030 annual WF:',f'{row.annual_water_footprint_m3:,.3f} m3/year',
        '','2030 annual WSF:',f'{row.annual_water_scarcity_footprint_m3_eq:,.3f} m3-eq/year',
        '','Median 2030 Aqueduct water stress:',f'{row.median_aqueduct_water_stress:.9f} raw ratio',
        '','Median 2030 projected mean temperature:',f'{row.median_temperature_mean_c:.3f} degrees C',
        '','Unique population within 5 km:',f'{row.unique_population_within_5km:,.3f} area-weighted residents (dissolved buffers)',
        '','Files created:',*[str(p.relative_to(ROOT)) for p in files],
        'outputs/stateful_simulation_provenance.json','outputs/stateful_simulation_validation.json',
        'outputs/stateful_simulation_tests.txt','docs/data_sources.md',
        '','Tests:',f'{passed} passed','0 failed',
        '','No adjusted water-stress ratio: supply/demand baseline unavailable; no unverified cm/year to m3/year conversion.',
        'No MP4/GIF created. No GitHub push. DataCenterSimulation/ unchanged.']
    text='\n'.join(lines)+'\n'
    (OUT/'stateful_simulation_completion.txt').write_text(text)
    print(text)


if __name__=='__main__':main()
