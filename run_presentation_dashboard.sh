#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
python="/Users/yeritmaryrodriguezdelgado/.venvs/data-center-impact/bin/python3"
if [ ! -x "$python" ]; then
    printf 'PRESENTATION PREFLIGHT FAILED\nPython environment missing: %s\n' "$python" >&2
    exit 1
fi
exec "$python" -m src.dashboard.presentation "$@"
