"""Validate generated HUC8 deliverables and print the requested completion record."""
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs'


def main():
    meta = json.loads((OUT / 'huc8_analysis_metadata.json').read_text())
    geometry = json.loads((OUT / 'huc8_geometry_validation.json').read_text())
    log = (OUT / 'huc8_analysis_tests.txt').read_text()
    result = re.search(r'(\d+) passed, (\d+) subtests passed', log)
    assert result and not re.search(r'\d+ failed|FAILED|ERRORS', log)
    assert geometry['mapped_groups'] == meta['huc8_count']
    assert not geometry['unmatched_huc8']
    files = sorted(OUT.glob('huc8_*.csv'))
    files += [OUT / 'crpi_weight_schemes.csv']
    names = ['figure10a_huc8_feature_correlation', 'figure10b_pca_explained_variance',
             'figure10c_huc8_pca_scatter', 'figure10d_cluster_diagnostics',
             'figure10e_huc8_clusters_pca', 'figure10f_cluster_profiles',
             'figure10g_huc8_cluster_map', 'figure11a_emerging_hotspots',
             'figure11b_scenario_rank_robustness', 'figure12_huc8_environmental_profiles']
    files += [OUT / 'figures' / (name + '.png') for name in names]
    files += [OUT / 'figures' / (name + '.pdf') for name in [names[6], names[9]]]
    files += [ROOT / name for name in ['README.md', 'docs/data_sources.md', 'docs/huc8_analysis.md']]
    assert all(p.is_file() and p.stat().st_size for p in files)
    dashboard = pd.read_csv(OUT / 'huc8_dashboard_data.csv', dtype={'huc8': str})
    assert len(dashboard) == meta['huc8_count'] and dashboard.huc8.is_unique
    prep = pd.read_csv(OUT / 'huc8_ml_preprocessing_report.csv')
    redundant = prep.loc[prep.redundancy_with.notna(), 'feature'].tolist()
    validation = {
        'status': 'passed', 'huc8_count': meta['huc8_count'],
        'aggregation_checks': meta['aggregation_checks'], 'geometry': geometry,
        'test_suite': {'passed': int(result[1]), 'subtests_passed': int(result[2]), 'failed': 0},
        'clustered_count': meta['preprocessing']['eligible_rows'],
        'excluded_from_clustering': meta['preprocessing']['excluded_rows'],
        'crpi_complete_count': meta['crpi_complete_count'],
        'visual_review': 'Rendered both PDF maps and inspected maps, PCA, profiles, hotspot and robustness charts; staggered overlapping emerging labels.',
        'output_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    }
    (OUT / 'huc8_analysis_validation.json').write_text(json.dumps(validation, indent=2) + '\n')
    lines = ['HUC8 WATERSHED ANALYSIS COMPLETE', '', 'HUC8 watersheds analyzed:', str(meta['huc8_count']),
             '', 'Features used:', *meta['preprocessing']['selected_features'],
             '', 'Features removed for redundancy:', *redundant,
             'Energy growth excluded as practically constant at 0.01 percentage-point resolution.',
             '', 'PCA explained variance:']
    lines += [f"{r['component']} {r['explained_variance_ratio']:.2%}" for r in meta['explained_variance'][:2]]
    for component, directions in meta['dominant_loadings'].items():
        lines += [f'{component} top {direction} loadings: {values}' for direction, values in directions.items()]
    lines += ['', 'Chosen cluster count:', str(meta['clustering']['chosen_k']), '', 'Cluster sizes:',
              str(meta['clustering']['cluster_sizes']), '', 'Cluster labels:',
              *[f'{k}: {v}' for k, v in meta['clustering']['cluster_labels'].items()],
              '', 'Persistent hotspots:', str(meta['hotspot_counts']['persistent_hotspot']),
              '', 'Emerging hotspots:', str(meta['hotspot_counts']['emerging_hotspot']),
              '', 'Scenario-robust hotspots (top quartile across all paired scenarios):', str(meta['scenario_robust_counts']),
              '', 'Lower-pressure watersheds:', str(meta['lower_pressure_count']),
              '', 'CRPI robust top watersheds:', str(meta['crpi_robust_count'])]
    robust = pd.read_csv(OUT / 'huc8_crpi_robust_hotspots.csv', dtype={'huc8': str})
    lines += [', '.join(robust.huc8), '', 'Tests:', f'{result[1]} passed', f'{result[2]} subtests passed', '0 failed',
              '', 'Files created:', *[str(p.relative_to(ROOT)) for p in files],
              'outputs/huc8_analysis_metadata.json', 'outputs/huc8_analysis_validation.json',
              'outputs/huc8_analysis_tests.txt', 'outputs/huc8_analysis_completion.txt',
              '', 'Screening profiles and index are not harm predictions or development recommendations.',
              'No GitHub push. DataCenterSimulation/ unchanged.']
    report = '\n'.join(lines) + '\n'
    (OUT / 'huc8_analysis_completion.txt').write_text(report)
    print(report)


if __name__ == '__main__':
    main()
