# Sourced by the dashboard launchers after changing to the repository root.
dashboard_python_works() {
    command -v "$1" >/dev/null 2>&1 &&
        "$1" -c 'import dash, geopandas, pandas, plotly' >/dev/null 2>&1
}

if [ -n "${DASHBOARD_PYTHON:-}" ]; then
    dashboard_python=$DASHBOARD_PYTHON
    if ! dashboard_python_works "$dashboard_python"; then
        printf '%s\n' 'DASHBOARD_PYTHON must point to a Python with the dashboard dependencies installed.' >&2
        exit 1
    fi
else
    dashboard_python=
    for candidate in .venv/bin/python "${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}" "${HOME:+$HOME/.venvs/data-center-impact/bin/python3}" python3; do
        if [ -n "$candidate" ] && dashboard_python_works "$candidate"; then
            dashboard_python=$candidate
            break
        fi
    done
    if [ -z "$dashboard_python" ]; then
        printf '%s\n' 'Dashboard Python environment unavailable. Create .venv with Python 3.14 and install requirements.txt. See Installation in README.md.' >&2
        exit 1
    fi
fi
