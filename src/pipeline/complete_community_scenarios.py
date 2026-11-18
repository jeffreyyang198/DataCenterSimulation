"""Retain sites without EPRI coverage in the community-context scenario grid."""
from pathlib import Path
import csv
import json
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]


def read_rows(path):
    with path.open() as stream:
        reader = csv.DictReader(stream)
        return list(reader), reader.fieldnames


def write_rows(path, rows, fields):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def complete_rows(rows, fields, exposure, mapping, future, water):
    """Add missing site/pathway rows; unknown modeled quantities stay blank."""
    scenarios = sorted({r['epri_scenario'] for r in rows})
    if len(scenarios) != 4:
        raise ValueError('Expected four EPRI demand scenarios')
    keys = {(r['site_id'],r['epri_scenario'],r['aqueduct_scenario']) for r in rows}
    mapping = {r['site_id']:r for r in mapping}
    future = {(r['pfaf_id'],r['aqueduct_scenario']):r for r in future}
    base = {r['site_id']:r for r in water}
    added = set()
    for site in exposure:
        site_id = site['site_id']
        basin = mapping[site_id]
        for demand in scenarios:
            for climate in ('optimistic','bau','pessimistic'):
                key = (site_id,demand,climate)
                if key in keys:
                    continue
                row = dict.fromkeys(fields,'')
                row.update(base.get(site_id,{}))
                row.update(site)
                row.update(basin)
                row.update(future.get((basin['pfaf_id'],climate),{}))
                row.update(epri_scenario=demand,aqueduct_scenario=climate,
                    year=2030,aqueduct_year=2030,water_status='no_epri_growth',has_epri_growth='False')
                for column in row:
                    if column.startswith(('projected_energy','annual_water','cumulative_')):
                        row[column] = ''
                row['growth_factor'] = ''
                row['water_m3_per_10000_nearby_residents'] = ''
                row['aqueduct_risk_available'] = str(bool(row.get('ws_x_s')))
                category = row.get('ws_x_c','')
                row['high_water_stress'] = str(float(category)>=3) if category else ''
                rows.append(row)
                keys.add(key)
                added.add(site_id)
    return rows, sorted(added)


def main():
    folder = ROOT/'outputs/community_resource_pressure'
    path = folder/'community_resource_pressure_2030.csv'
    rows,fields = read_rows(path)
    rows,added = complete_rows(rows,fields,
        read_rows(ROOT/'data/processed/community_exposure_acs2023.csv')[0],
        read_rows(ROOT/'data/processed/site_aqueduct_basins.csv')[0],
        read_rows(ROOT/'data/processed/aqueduct2030_normalized.csv')[0],
        read_rows(ROOT/'outputs/temporal_water_2023_2030.csv')[0])
    if added:
        write_rows(path,rows,fields)
        groups = defaultdict(list)
        for row in rows:
            groups[(row['epri_scenario'],row['aqueduct_scenario'])].append(row)
        summary=[]
        for (demand,climate),group in sorted(groups.items()):
            values=[float(r['annual_water_footprint_m3']) for r in group if r['annual_water_footprint_m3']]
            summary.append(dict(epri_scenario=demand,aqueduct_scenario=climate,
                site_records=len(group),matched_basins=sum(bool(r['pfaf_id']) for r in group),
                usable_water_stress=sum(bool(r['ws_x_s']) for r in group),
                high_stress_site_records=sum(r['high_water_stress']=='True' for r in group),
                modeled_water_m3=sum(values) if values else ''))
        write_rows(folder/'scenario_summary.csv',summary,list(summary[0]))
    metadata_path=folder/'run_metadata.json'
    metadata=json.loads(metadata_path.read_text())
    metadata['output_rows']=len(rows)
    if added:
        metadata['sites_retained_without_epri_growth']=added
    metadata_path.write_text(json.dumps(metadata,indent=2)+'\n')
    print('Scenario records:',len(rows),'sites restored without EPRI coverage:',added)


if __name__ == '__main__':
    main()
