"""Cache Census 2023 ACS 5-year tract population; never replace raw responses."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
BULK_URL = ('https://www2.census.gov/programs-surveys/acs/summary_file/2023/'
            'table-based-SF/data/5YRData/acsdt5y2023-b01003.dat')


def write_or_reuse(path, content):
    data = content.encode('utf-8')
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f'Conflicting existing raw output; archive before replacing: {path}')
        return
    path.write_bytes(data)


def main():
    bulk = ROOT / 'data/raw/census/acs2023/acsdt5y2023-b01003.dat'
    if not bulk.exists():
        bulk.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(BULK_URL, timeout=90) as response:
            raw = response.read()
        if not raw.startswith(b'GEO_ID|B01003_E001|'):
            raise ValueError('Unexpected Census summary file response')
        bulk.write_bytes(raw)
    if bulk.exists():
        rows = []
        with bulk.open() as stream:
            for row in csv.DictReader(stream, delimiter='|'):
                geoid = row['GEO_ID']
                if not geoid.startswith('1400000US'):
                    continue
                geoid = geoid.removeprefix('1400000US')
                if len(geoid) != 11 or not geoid.isdigit():
                    raise ValueError('Malformed tract GEOID')
                value = row['B01003_E001']
                rows.append(dict(GEOID=geoid, B01003_001E=value,
                    population=int(value) if value and int(value) >= 0 else None))
        if not rows or len({r['GEOID'] for r in rows}) != len(rows):
            raise ValueError('Empty ACS tract table or duplicate GEOIDs')
        out = bulk.parent
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=['GEOID', 'B01003_001E', 'population'])
        writer.writeheader()
        writer.writerows(rows)
        write_or_reuse(out / 'acs2023_tract_population.csv', stream.getvalue())
        write_or_reuse(out / 'source_metadata.json', json.dumps(dict(
            dataset='2023 ACS 5-Year', period='2019-2023', geography='tract',
            variable='B01003_001E', summary_file_variable='B01003_E001',
            records=len(rows), retrieved_utc=datetime.fromtimestamp(bulk.stat().st_mtime, timezone.utc).isoformat(),
            url=BULK_URL,
            sha256=hashlib.sha256(bulk.read_bytes()).hexdigest(),
            reason='Official table-based summary file used because API requires a key.'
        ), indent=2)+'\n')
        print(f'Wrote {len(rows)} tract population records', flush=True)
        return


if __name__ == '__main__':
    main()
