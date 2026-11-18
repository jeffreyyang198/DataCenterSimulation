#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
. ./scripts/dashboard_python.sh
exec "$dashboard_python" -m src.dashboard.presentation "$@"
