"""Build one master row per IM3 site, with explicitly configured dataset joins."""

import argparse
import json
from pathlib import Path
import re

import pandas as pd

from src.clean.clean_im3 import ROOT, clean_im3, load_im3, save_im3

OUTPUT_FILE = ROOT / 'data/processed/master_sites.csv'
JOIN_KEYS = {'site_id', 'county_fips', 'state_fips'}


def merge_dataset(sites, dataset, name, key, columns):
    """Left join one record per key, preserving sites and prefixing new fields.

    County/state attributes are context shared by sites, not site measurements.
    Missing master keys never match; missing or repeated dataset keys are errors.
    """
    if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', name):
        raise ValueError('Dataset name must use lowercase letters, digits, and underscores')
    if key not in JOIN_KEYS:
        raise ValueError(f'Unsupported join key: {key}')
    if not isinstance(columns, list) or not columns or not all(isinstance(c, str) for c in columns):
        raise ValueError('Select a nonempty list of dataset columns')
    if key in columns or len(set(columns)) != len(columns):
        raise ValueError('Selected columns must be unique and exclude the join key')
    if missing := {key, *columns} - set(dataset.columns):
        raise ValueError(f'{name}: missing columns {sorted(missing)}')
    incoming = dataset[[key, *columns]].copy()
    incoming[key] = incoming[key].astype('string').str.strip()
    pattern = {'site_id': r'im3_[0-9]{11}', 'county_fips': r'[0-9]{5}', 'state_fips': r'[0-9]{2}'}[key]
    if not incoming[key].str.fullmatch(pattern).fillna(False).all():
        raise ValueError(f'{name}: missing or malformed {key}; preserve complete string identifiers')
    if incoming[key].duplicated().any():
        raise ValueError(f'{name}: duplicate {key}; select a year/scenario or reshape before merging')
    renamed = {column: f'{name}__{column}' for column in columns}
    if collisions := set(renamed.values()) & set(sites.columns):
        raise ValueError(f'{name}: output columns already exist: {sorted(collisions)}')
    matched = sites[key].notna() & sites[key].isin(incoming[key])
    result = sites.merge(incoming.rename(columns=renamed), on=key, how='left',
                         sort=False, validate='many_to_one')
    if len(result) != len(sites) or result.site_id.tolist() != sites.site_id.tolist():
        raise ValueError('Merge changed the master site rows or order')
    report = {
        'name': name, 'join_key': key, 'columns': renamed,
        'dataset_rows': len(incoming), 'matched_sites': int(matched.sum()),
        'unmatched_sites': int((~matched).sum()),
        'sites_missing_join_key': int(sites[key].isna().sum()),
        'dataset_rows_without_site_match': int((~incoming[key].isin(sites[key].dropna())).sum()),
    }
    return result, report


def build_database(config_path=None, output_path=OUTPUT_FILE):
    sites = clean_im3(load_im3())
    master = sites.copy()
    master.attrs = {}
    reports = []
    if config_path is not None:
        config_path = Path(config_path).resolve()
        config = json.loads(config_path.read_text())
        if not isinstance(config, dict) or set(config) != {'datasets'} or not isinstance(config['datasets'], list):
            raise ValueError('Merge config must contain a datasets list')
        names = set()
        for entry in config['datasets']:
            if not isinstance(entry, dict) or set(entry) != {'name', 'path', 'key', 'columns'}:
                raise ValueError('Each dataset requires name, path, key, and columns')
            name = entry['name']
            if not isinstance(name, str) or name in names:
                raise ValueError('Dataset names must be unique strings')
            names.add(name)
            path = (config_path.parent / entry['path']).resolve()
            dataset = pd.read_csv(path, dtype='string', keep_default_na=False, na_values=[''])
            master, report = merge_dataset(master, dataset, name, entry['key'], entry['columns'])
            report['path'] = str(path)
            reports.append(report)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve the existing cleaner outputs and its county-review evidence.
    save_im3(sites)
    master.to_csv(output_path, index=False)
    report = {'total_sites': len(master), 'merged_dataset_count': len(reports),
              'datasets': reports, 'base_only': not reports}
    output_path.with_name(output_path.stem + '_merge_report.json').write_text(
        json.dumps(report, indent=2) + '\n')
    print(f'Saved {output_path} ({len(master)} sites; {len(reports)} merged datasets)')
    return master


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, help='JSON merge specification; relative CSV paths resolve from this file')
    parser.add_argument('--output', type=Path, default=OUTPUT_FILE)
    args = parser.parse_args()
    build_database(args.config, args.output)


if __name__ == '__main__':
    main()
