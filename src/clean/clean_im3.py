"""Build a validated master site table and a county-assignment review file."""
import json
from pathlib import Path
import pandas as pd

if __package__:
    from .site_schema import MASTER_SITE_SCHEMA, SITE_TYPES
else:
    from site_schema import MASTER_SITE_SCHEMA, SITE_TYPES

ROOT = Path(__file__).resolve().parents[2]
SOURCE_VERSION = '2026.02.09'
RAW_FILE = ROOT / ('data/raw/im3/p147s-4h760/'
                   f'im3_open_source_data_center_atlas_v{SOURCE_VERSION}/'
                   f'im3_open_source_data_center_atlas_v{SOURCE_VERSION}.csv')
OUTPUT_FILE = ROOT / 'data/processed/data_centers.csv'
RENAME = {'id': 'source_site_id', 'state_abb': 'state_abbr',
          'state_id': 'state_fips', 'county_id': 'county_fips',
          'ref': 'reference', 'name': 'site_name', 'sqft': 'square_feet',
          'lon': 'longitude', 'lat': 'latitude', 'type': 'site_type'}
REQUIRED = set(RENAME) | {'state', 'county', 'operator'}
# Spelling/name variants only; no ownership inference or acquisition rollups.
OPERATOR_ALIASES = {
    'databank': 'DataBank', 'google llc': 'Google', 'apple inc.': 'Apple',
    'meta platforms': 'Meta', 'ntt limited': 'NTT',
    'stack infrastructure, incorporated': 'Stack Infrastructure',
    'aligned': 'Aligned Data Centers', 'aligned data centers, llc': 'Aligned Data Centers',
    'vantage': 'Vantage Data Centers', 'sabey': 'Sabey Data Centers',
    'h5': 'H5 Data Centers', 'serverfarm llc.': 'Serverfarm', 'centurylink': 'CenturyLink',
}


def load_im3(path=RAW_FILE):
    return pd.read_csv(path, dtype='string', keep_default_na=False)


def _text(series):
    return series.astype('string').str.strip().str.replace(r'\s+', ' ', regex=True).replace('', pd.NA)


def _require(condition, message):
    if not condition.fillna(False).all():
        raise ValueError(message)


def _digits(series, width, name):
    result = _text(series).str.replace(r'\.0+$', '', regex=True)
    _require(result.str.fullmatch(rf'[0-9]{{1,{width}}}'), f'Invalid or missing {name}')
    return result.str.zfill(width)


def clean_im3(df):
    """Keep one row per site; preserve county-only conflicts for review."""
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f'Missing IM3 columns: {sorted(missing)}')
    result = df[sorted(REQUIRED)].copy().rename(columns=RENAME)
    for column in result:
        result[column] = _text(result[column])
    result['source_site_id'] = _digits(result.source_site_id, 11, 'site ID')
    result['site_id'] = 'im3_' + result.source_site_id
    result['source'] = 'im3'
    result['source_version'] = SOURCE_VERSION
    result['state_abbr'] = result.state_abbr.str.upper()
    result['state_fips'] = _digits(result.state_fips, 2, 'state FIPS')
    county = result.county_fips.str.replace(r'\.0+$', '', regex=True)
    _require(county.str.fullmatch(r'[0-9]{1,3}|[0-9]{5}'), 'Invalid or missing county FIPS')
    result['county_fips'] = county.where(county.str.len() == 5, result.state_fips + county.str.zfill(3))
    _require(result.county_fips.str[:2].eq(result.state_fips) & result.county_fips.str[2:].ne('000'), 'County/state FIPS mismatch')
    result['site_type'] = result.site_type.str.lower()
    result['operator_raw'] = result.operator
    result['operator'] = result.operator.map(lambda v: OPERATOR_ALIASES.get(v.casefold(), v) if pd.notna(v) else pd.NA)
    for column in ['latitude', 'longitude', 'square_feet']:
        numeric = pd.to_numeric(result[column], errors='coerce').astype('Float64')
        _require(result[column].isna() | numeric.notna(), f'Non-numeric {column}')
        result[column] = numeric
    result['quality_flags'] = pd.Series('', index=result.index, dtype='string')
    result = result.drop_duplicates()
    county_reviews, rows = [], []
    for site_id, group in result.groupby('site_id', sort=True):
        if len(group) > 1:
            if len(group.drop(columns=['county', 'county_fips']).drop_duplicates()) != 1:
                raise ValueError(f'Conflicting non-county attributes for {site_id}')
            county_reviews.append(group[['site_id', 'state_fips', 'county', 'county_fips']])
        row = group.iloc[0].copy()
        flags = []
        if len(group) > 1:
            row['county'] = row['county_fips'] = pd.NA
            flags.append('ambiguous_county')
        for column in ['operator', 'square_feet']:
            if pd.isna(row[column]):
                flags.append('missing_' + column)
        row['quality_flags'] = ';'.join(flags) or pd.NA
        rows.append(row)
    output = pd.DataFrame(rows, columns=list(MASTER_SITE_SCHEMA)).astype(MASTER_SITE_SCHEMA).reset_index(drop=True)
    validate_im3(output)
    output.attrs['county_review'] = pd.concat(county_reviews, ignore_index=True).sort_values(['site_id', 'county_fips']).reset_index(drop=True) if county_reviews else pd.DataFrame(columns=['site_id', 'state_fips', 'county', 'county_fips'])
    output.attrs['input_rows'] = len(df)
    output.attrs['exact_duplicates_removed'] = len(df) - len(result)
    return output


def validate_im3(df):
    """Enforce the master contract before saving; never silently discard invalid rows."""
    if list(df.columns) != list(MASTER_SITE_SCHEMA):
        raise ValueError('Master schema columns or order differ')
    if df.site_id.duplicated().any():
        raise ValueError('Duplicate master site IDs')
    _require(df.site_id.eq('im3_' + df.source_site_id), 'Invalid site ID namespace')
    _require(df.source_site_id.str.fullmatch(r'[0-9]{11}'), 'Invalid source site ID')
    _require(df.state_fips.str.fullmatch(r'[0-9]{2}') & df.state_fips.ne('00'), 'Invalid state FIPS')
    _require(df.state_abbr.str.fullmatch(r'[A-Z]{2}'), 'Invalid state abbreviation')
    _require(df.county_fips.isna() | (df.county_fips.str.fullmatch(r'[0-9]{5}') & df.county_fips.str[:2].eq(df.state_fips) & df.county_fips.str[2:].ne('000')), 'County/state FIPS mismatch')
    _require(df.county_fips.notna() | df.quality_flags.str.contains('ambiguous_county', na=False), 'Missing county without review flag')
    _require(df.latitude.between(-90, 90) & df.longitude.between(-180, 180), 'Missing or out-of-range coordinates')
    _require(df.square_feet.isna() | (df.square_feet.gt(0) & df.square_feet.lt(float('inf'))), 'Footprint must be finite and positive')
    _require(df.site_type.isin(SITE_TYPES), 'Unknown site type')


def save_im3(df, path=OUTPUT_FILE):
    validate_im3(df)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    review = df.attrs.get('county_review')
    if review is not None:
        review.to_csv(path.with_name('im3_county_review.csv'), index=False)
    report = {
        'source_version': SOURCE_VERSION, 'input_rows': df.attrs.get('input_rows'),
        'output_sites': len(df), 'exact_duplicates_removed': df.attrs.get('exact_duplicates_removed'),
        'ambiguous_county_sites': int(df.county_fips.isna().sum()),
        'missing_values': {c: int(n) for c, n in df.isna().sum().items()},
        'site_types': {c: int(n) for c, n in df.site_type.value_counts().items()},
    }
    path.with_name('im3_quality_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print(f'Saved {path}')


def main():
    save_im3(clean_im3(load_im3()))


if __name__ == '__main__':
    main()
