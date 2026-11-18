"""Run a browser-free rehearsal of the local presentation dashboard."""
from time import perf_counter

from src.dashboard.presentation import BACKUPS, ROOT, failure, preflight, summary
from src.dashboard.validate import run


def main():
    start = perf_counter()
    try:
        data = preflight(backups=True)
        preload_seconds = perf_counter() - start
        results = run(data, presentation=True, save_report=False)
    except (OSError, ValueError, KeyError, AssertionError) as error:
        failure(error)
        return 1
    print(summary(data))
    for path in BACKUPS:
        print(f'Backup verified: {path.relative_to(ROOT)}')
    print(f'Preflight and preload: {preload_seconds:.2f} s')
    print(f"Longest sampled callback: {results['longest_render_seconds']:.3f} s")
    print('PRESENTATION SMOKE TEST PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
