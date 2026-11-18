#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
. ./scripts/dashboard_python.sh
"$dashboard_python" -m scripts.smoke_test_dashboard
"$dashboard_python" -m pytest tests -q
printf '\nLIVE PRESENTATION DASHBOARD READY\nLaunch: ./run_presentation_dashboard.sh\nURL: http://127.0.0.1:8050\n'
