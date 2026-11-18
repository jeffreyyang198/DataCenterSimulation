"""Launch with python3 -m src.dashboard.app in the existing environment."""
import os
from pathlib import Path
from dash import Dash, dcc, html

from .callbacks import INITIAL, register_callbacks
from .data import load_data
from .formatting import METRICS, TEMPORAL


def create_app(data=None, *, presentation=False):
    data = data or load_data()
    app = Dash(__name__, serve_locally=True, assets_folder=str(Path(__file__).parent / 'assets'),
               title='U.S. Data Center Resource Explorer', update_title='Updating view…')
    if presentation:
        app.enable_dev_tools(debug=False, dev_tools_hot_reload=False)
    app.server.add_url_rule('/health', 'health', lambda: {'status': 'ok'})
    quick_states = list(dict.fromkeys(state for state, _ in data.demo_examples.values()))
    quick_states += [s for s in data.state_counts.sort_values(ascending=False).index if s not in quick_states]
    quick_states = quick_states[:5]
    state_options = [{'label': f'Quick select · {data.state_names[s]} ({s})', 'value': s} for s in quick_states]
    state_options += [{'label': f'{name} ({s})', 'value': s}
                      for s, name in sorted(data.state_names.items(), key=lambda item: item[1]) if s not in quick_states]
    app.layout = html.Main(id='shell', className='dashboard presentation' if presentation else 'dashboard', children=[
        dcc.Store(id='selection', data=INITIAL),
        html.Header([
            html.Div([html.Div('DATA CENTER COMMUNITY IMPACT', className='eyebrow'),
                      html.H1('U.S. Data Center Community & Resource Pressure Explorer'),
                      html.P('Scenario-based screening of energy, emissions, water, watershed stress, climate context, and nearby population through 2030', className='subtitle')]),
            dcc.Checklist(id='presentation', options=[{'label': ' Presentation Mode', 'value': 'on'}],
                          value=['on'] if presentation else [], className='presentation-control'),
        ]),
        html.Section(className='controls', children=[
            html.Div([html.Label('SCREENING SCENARIO', htmlFor='scenario'), dcc.Dropdown(id='scenario', options=[
                {'label': 'Lower pressure', 'value': 'lower_pressure'}, {'label': 'Central', 'value': 'central'},
                        {'label': 'Higher pressure', 'value': 'higher_pressure'}], value='central', clearable=False)]),
            html.Div([html.Label('WATERSHED MAP METRIC', htmlFor='metric'), dcc.Dropdown(id='metric',
                options=[{'label': label, 'value': key} for key, (label, _) in METRICS.items()], value='crpi_equal', clearable=False)]),
            html.Div(className='year-control', children=[html.Label([html.Span('SELECTED YEAR'), html.Strong('2030', id='year-indicator')], htmlFor='year'),
                dcc.Slider(id='year', min=2023, max=2030, step=1, value=2030, marks={y: str(y) for y in range(2023, 2031)})]),
        ]),
        html.P('Paired screening scenarios: low + optimistic / moderate + business as usual / higher + pessimistic. These are not formally coupled climate-economic pathways. NASA remains SSP2-4.5.', className='scenario-note'),
        html.Section(id='national-cards', className='cards'),
        html.Nav(className='navigation', children=[html.Div(id='breadcrumb'),
            html.Div([html.Button('Clear selected site', id='clear-site', n_clicks=0),
                      html.Button('Back to state', id='back', n_clicks=0), html.Button('Reset to U.S.', id='reset', n_clicks=0)])]),
        html.Section(className='selectors', children=[
            html.Div([html.Label('STATE', htmlFor='state-select'), dcc.Dropdown(id='state-select',
                options=state_options, placeholder='Click a state or choose here')]),
            html.Div([html.Label('FULL HUC8 WATERSHED', htmlFor='huc-select'), dcc.Dropdown(id='huc-select', options=[], placeholder='Choose a state first')]),
            html.Div([html.Label('MODELED SITE', htmlFor='site-select'), dcc.Dropdown(id='site-select', options=[], placeholder='Select a site on the map or here')]),
            html.Div([html.Label('DEMO EXAMPLES', htmlFor='demo'), dcc.Dropdown(id='demo',
                options=[{'label': label, 'value': huc} for huc, (_, label) in data.demo_examples.items()],
                placeholder='Jump to a watershed')]),
        ]),
        html.Div(className='filter-line', children=[dcc.Checklist(id='lower-filter', options=[{'label': ' Show comparatively lower-pressure watersheds', 'value': 'lower'}], value=[]),
            html.Span('Central-2030 screening criteria; not development recommendations.', className='note')]),
        html.Section(className='main-grid', children=[
            html.Div(className='map-panel', children=[html.Div(id='map-note', className='map-note'),
                dcc.Loading(dcc.Graph(id='map', className='main-map', config={'displaylogo': False, 'scrollZoom': True,
                    'modeBarButtonsToRemove': ['select2d', 'lasso2d'], 'toImageButtonOptions': {'format': 'png', 'filename': 'watershed_view', 'scale': 2}}), type='dot')]),
            html.Aside(id='summary', className='detail-panel'),
        ]),
        html.Section(className='temporal-panel', children=[html.Div(className='chart-controls', children=[
            html.H2('2023–2030 trajectory'), dcc.Dropdown(id='temporal-metric', options=[{'label': label, 'value': key} for key, (label, _) in TEMPORAL.items()],
                value='projected_energy_mwh', clearable=False)]), dcc.Graph(id='temporal', config={'displaylogo': False})]),
        html.Footer([
            html.P('Scenario-based screening estimates. Population measures proximity only. Watersheds retain their full boundaries across state lines.'),
            html.P('NASA SSP2-4.5 provides external projected climate context. Intermediate Aqueduct years are interpolated screening values.'),
            html.P('Cumulative direct water adds annual modeled demand. Permanent depletion is a separate hydrologic outcome.'),
            html.P('CRPI is an analyst-defined 0–100 screening score. Gray polygons indicate unavailable data.', className='technical'),
            html.P('Site colors show water stress: blue <10%, green 10–20%, amber 20–40%, orange 40–80%, red ≥80%; gray = unavailable.', className='technical'),
        ]),
    ])
    register_callbacks(app, data)
    return app


def main():
    app = create_app()
    port = int(os.environ.get('PORT', '8050'))
    print(f'Local dashboard: http://127.0.0.1:{port}', flush=True)
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
