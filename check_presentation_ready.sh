#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
python="/Users/yeritmaryrodriguezdelgado/.venvs/data-center-impact/bin/python3"
if [ ! -x "$python" ]; then
    printf 'PRESENTATION PREFLIGHT FAILED\nPython environment missing: %s\n' "$python" >&2
    exit 1
fi
"$python" -m scripts.smoke_test_dashboard
"$python" -m pytest tests -q
printf '\nLIVE PRESENTATION DASHBOARD READY\nLaunch: ./run_presentation_dashboard.sh\nURL: http://127.0.0.1:8050\n'
