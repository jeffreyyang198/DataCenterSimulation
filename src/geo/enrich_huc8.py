"""Attach WBD HUC8 and Siddik Table 3 parameters without estimating site impacts."""

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pandas.testing import assert_frame_equal

ROOT = Path(__file__).resolve().parents[2]
PARAMETERS = ['WF_1MW_DC', 'WSF_1MW_DC', 'CF_1MW_DC']


def normalize_huc8(values: pd.Series) -> pd.Series:
    """Preserve missing codes; pad digit strings and reject malformed identifiers."""
    codes = values.astype('string').str.strip().replace('', pd.NA)
    codes = codes.str.replace(r'\.0$', '', regex=True)
    invalid = codes.notna() & ~codes.str.fullmatch(r'[0-9]{1,8}', na=False)
    if invalid.any():
        raise ValueError(f'Invalid HUC8 values: {codes[invalid].unique().tolist()}')
    return codes.str.zfill(8)


def load_huc8_boundaries(path: str | Path, layer: str | None = None) -> gpd.GeoDataFrame:
    """Read a supplied USGS WBD HUC8 polygon layer with a declared CRS."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f'{path} does not exist. A USGS WBD HUC8 polygon dataset is required; '
            'supply --boundaries PATH and, for multilayer files, --layer WBDHU8.'
        )
    return _prepare_boundaries(gpd.read_file(path, layer=layer))


def _prepare_boundaries(boundaries: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Validate geometry metadata and normalize the layer's HUC8 field."""
    fields = [c for c in boundaries.columns if c.lower().replace('_', '') == 'huc8']
    if len(fields) != 1 or boundaries.crs is None:
        raise ValueError('WBD boundaries require one HUC8 field and a declared CRS.')
    result = boundaries[[fields[0], boundaries.geometry.name]].copy()
    result = result.rename(columns={fields[0]: 'huc8'})
    result['huc8'] = normalize_huc8(result.huc8)

    # Repair invalid source polygons while preserving valid geometries.
    invalid_geometry = ~result.geometry.is_valid
    if invalid_geometry.any():
        result.loc[invalid_geometry, result.geometry.name] = (
            result.loc[invalid_geometry, result.geometry.name].make_valid()
        )

    if (result.huc8.isna().any() or result.geometry.isna().any()
            or result.geometry.is_empty.any() or not result.geometry.is_valid.all()
            or not result.geom_type.isin(['Polygon', 'MultiPolygon']).all()):
        raise ValueError('WBD polygons must have nonmissing HUC8 codes and valid polygon geometries.')
    return result


def assign_huc8_to_sites(sites: pd.DataFrame, boundaries: gpd.GeoDataFrame) -> pd.DataFrame:
    """Assign intersecting polygons; multiple distinct HUC8 codes require review.

    Intersects includes boundary points. Repeated polygon parts for the same code
    are unambiguous; a shared boundary or overlap between codes remains unassigned.
    Original columns, coordinate text, row order, and index are retained.
    """
    additions = {'huc8', 'huc8_status', 'huc8_candidates', 'table3_match', *PARAMETERS}
    if overlap := additions & set(sites.columns):
        raise ValueError(f'Enrichment columns already exist: {sorted(overlap)}')
    boundaries = _prepare_boundaries(boundaries)
    result = sites.copy()
    lon = pd.to_numeric(sites['longitude'], errors='coerce').reset_index(drop=True)
    lat = pd.to_numeric(sites['latitude'], errors='coerce').reset_index(drop=True)
    valid = lon.between(-180, 180) & lat.between(-90, 90)
    codes = pd.Series(pd.NA, index=range(len(sites)), dtype='string')
    candidates = codes.copy()
    status = pd.Series('invalid_coordinates', index=codes.index, dtype='string')
    status.loc[valid] = 'no_polygon_match'
    points = gpd.GeoDataFrame(geometry=gpd.points_from_xy(lon[valid], lat[valid]),
                              index=lon[valid].index, crs='EPSG:4326')
    if len(points):
        joined = gpd.sjoin(points.to_crs(boundaries.crs), boundaries,
                          how='left', predicate='intersects')
        for position, matches in joined.groupby(level=0):
            unique = sorted(matches.huc8.dropna().unique())
            if unique:
                candidates.loc[position] = ';'.join(unique)
                if len(unique) == 1:
                    codes.loc[position] = unique[0]
                    status.loc[position] = 'assigned'
                else:
                    status.loc[position] = 'ambiguous_watershed'
    result['huc8'] = codes.array
    result['huc8_status'] = status.array
    result['huc8_candidates'] = candidates.array
    return result


def merge_table3(sites: pd.DataFrame, table3: pd.DataFrame) -> pd.DataFrame:
    """Left join unique normalized Table 3 keys; fail before any row multiplication."""
    table = table3[['HUC8', *PARAMETERS]].copy()
    table['huc8'] = normalize_huc8(table.pop('HUC8'))
    duplicates = table.loc[table.huc8.notna() & table.huc8.duplicated(False), 'huc8']
    if len(duplicates):
        raise ValueError(f'Duplicate HUC8 values in Table 3: {sorted(duplicates.unique())}')
    result = sites.copy()
    result['huc8'] = normalize_huc8(result.huc8)
    original_index = result.index
    result = result.merge(table.dropna(subset=['huc8']), on='huc8', how='left',
                          sort=False, validate='many_to_one', indicator='_table3_merge')
    result['table3_match'] = result.pop('_table3_merge').eq('both')
    result.index = original_index
    return result


def validate_huc8_merge(original: pd.DataFrame, enriched: pd.DataFrame,
                        table3: pd.DataFrame) -> dict:
    """Verify preservation and report coverage separately from parameter missingness."""
    assert_frame_equal(original, enriched[original.columns])
    if 'site_id' in original and original.site_id.is_unique and not enriched.site_id.is_unique:
        raise ValueError('Site IDs lost uniqueness')
    codes = enriched.huc8.dropna()
    if not codes.str.fullmatch(r'[0-9]{8}').all():
        raise ValueError('Enriched HUC8 must contain exactly eight digits')
    keys = normalize_huc8(table3.HUC8).dropna()
    return {
        'total_master_site_rows': len(original),
        'rows_with_valid_coordinates': int(enriched.huc8_status.ne('invalid_coordinates').sum()),
        'rows_assigned_huc8': int(enriched.huc8.notna().sum()),
        'rows_without_huc8': int(enriched.huc8.isna().sum()),
        'unique_huc8_watersheds': int(enriched.huc8.nunique()),
        'rows_matched_table3': int(enriched.table3_match.sum()),
        'rows_huc8_without_table3': int((enriched.huc8.notna() & ~enriched.table3_match).sum()),
        'duplicate_table3_huc8_values': sorted(keys[keys.duplicated(False)].unique().tolist()),
        'unmatched_table3_huc8_values': sorted(enriched.loc[
            enriched.huc8.notna() & ~enriched.table3_match, 'huc8'].unique().tolist()),
        'missing_parameters': {c: int(enriched[c].isna().sum()) for c in PARAMETERS},
        'huc8_status_counts': {str(k): int(v) for k, v in enriched.huc8_status.value_counts().items()},
    }


def main() -> None:
    """Write separate enriched, summary, and site-review outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boundaries', type=Path, required=True)
    parser.add_argument('--layer', help='HUC8 layer name, e.g. WBDHU8')
    parser.add_argument('--master', type=Path, default=ROOT / 'data/processed/master_sites.csv')
    parser.add_argument('--table3', type=Path, default=ROOT / 'data/processed/table3.csv')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/processed/master_sites_with_huc8.csv')
    args = parser.parse_args()
    report_path = args.output.with_name(args.output.stem + '_report.json')
    review_path = args.output.with_name(args.output.stem + '_review.csv')
    inputs = {p.resolve() for p in [args.master, args.table3, args.boundaries]}
    if any(p.resolve() in inputs for p in [args.output, report_path, review_path]):
        parser.error('Output paths must not overwrite input files.')
    boundaries = load_huc8_boundaries(args.boundaries, args.layer)
    # Strings preserve source identifiers, leading zeros, and coordinate text.
    sites = pd.read_csv(args.master, dtype='string')
    table = pd.read_csv(args.table3, dtype={'HUC8': 'string'})
    enriched = merge_table3(assign_huc8_to_sites(sites, boundaries), table)
    report = validate_huc8_merge(sites, enriched, table)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(args.output, index=False)
    review = enriched.loc[enriched.huc8.isna() | ~enriched.table3_match]
    review.to_csv(review_path, index=False)
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
