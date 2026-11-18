"""Validate generated community context artifacts without modifying them."""
from pathlib import Path
import csv
import json
import math
import hashlib
import statistics

ROOT = Path(__file__).resolve().parents[2]


def main():
    folder = ROOT/'outputs/community_resource_pressure'
    with (ROOT/'data/processed/community_exposure_acs2023.csv').open() as stream:
        exposure = list(csv.DictReader(stream))
    ids = [r['site_id'] for r in exposure]
    assert len(ids) == len(set(ids)), 'Duplicate population site IDs'
    for row in exposure:
        values = [float(row[f'pop_{r}km']) for r in (1,3,5) if row[f'pop_{r}km']]
        assert all(math.isfinite(x) and x >= 0 for x in values), 'Invalid population'
        assert all(a <= b + 1e-5 for a,b in zip(values, values[1:])), 'Nonmonotonic proximity population'
    with (folder/'community_resource_pressure_2030.csv').open() as stream:
        combined = list(csv.DictReader(stream))
    keys = [(r['site_id'], r['epri_scenario'], r['aqueduct_scenario']) for r in combined]
    assert len(keys) == len(set(keys)), 'Duplicate site/scenario records'
    assert len(combined) == len(ids)*12, 'Expected four EPRI by three Aqueduct scenarios per site'
    assert {r['aqueduct_scenario'] for r in combined} == {'optimistic','bau','pessimistic'}
    assert {r['site_id'] for r in combined} == set(ids), 'Site coverage changed'
    for row in combined:
        if row['aqueduct_assignment_status'] != 'assigned':
            assert not row['pfaf_id'], 'Ambiguous or unmatched site assigned a basin'
        if row['ws_x_s']:
            assert 0 <= float(row['ws_x_s']) <= 5, 'Invalid usable stress score'
        if row['incomplete_pop_5km'] == 'True':
            assert not row['water_m3_per_10000_nearby_residents'], 'Partial population used in ratio'
    result = dict(site_records=len(ids), combined_records=len(combined),
                  checks='passed', expected_scenarios_per_site=12)
    inputs = [
        'data/raw/source_copy_manifest.json',
        'data/raw/census/acs2023/source_metadata.json',
        'data/raw/epri/EPRI_2024_Projections.xlsx',
        'data/processed/master_sites.csv',
        'data/processed/master_sites_with_huc8.csv',
        'data/processed/table3.csv',
        'data/processed/energy_scenarios/floor_area_1.0/low_ai_inference.csv',
        'data/processed/community_exposure.csv',
        'src/pipeline/community_resource_pressure.py',
        'src/pipeline/complete_community_scenarios.py',
        'src/impact/temporal_water.py',
        'src/model/epri_projection.py',
    ]
    result['input_sha256'] = {
        path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in inputs
    }
    with (folder/'population_comparison.csv').open() as stream:
        comparison = list(csv.DictReader(stream))
    differences = []
    for radius in (1,3,5):
        values = [float(row[f'difference_{radius}km']) for row in comparison
                  if row[f'difference_{radius}km']]
        differences.append(dict(radius_km=radius,compared_sites=len(values),
            median_signed_difference=statistics.median(values),
            median_absolute_difference=statistics.median(abs(v) for v in values),
            max_absolute_difference=max(abs(v) for v in values)))
    (folder/'population_comparison_summary.json').write_text(json.dumps(differences,indent=2)+'\n')
    (folder/'validation_report.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
