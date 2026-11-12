"""Launch with python3 -m src.dashboard.app in the existing environment."""
import os
from pathlib import Path
from dash import Dash, dcc, html

from .callbacks import INITIAL, register_callbacks
from .data import load_data
from .formatting import METRICS, TEMPORAL


def create_app(data=None):
    data = data or load_data()
    app = Dash(__name__, assets_folder=str(Path(__file__).parent / 'assets'),
               title='U.S. Data Center Resource Explorer', update_title='Updating view…')
    app.layout = html.Main(id='shell', className='dashboard', children=[
        dcc.Store(id='selection', data=INITIAL, storage_type='session'),
        html.Header([
            html.Div([html.Div('DATA CENTER COMMUNITY IMPACT', className='eyebrow'),
                      html.H1('U.S. Data Center Community & Resource Pressure Explorer'),
                      html.P('Scenario-based screening of energy, emissions, water, watershed stress, climate context, and nearby population through 2030', className='subtitle')]),
            dcc.Checklist(id='presentation', options=[{'label': ' Presentation Mode', 'value': 'on'}], value=[], className='presentation-control'),
        ]),
        html.Section(className='controls', children=[
            html.Div([html.Label('SCREENING SCENARIO', htmlFor='scenario'), dcc.Dropdown(id='scenario', options=[
                {'label': 'Lower pressure', 'value': 'lower_pressure'}, {'label': 'Central', 'value': 'central'},
                {'label': 'Higher pressure', 'value': 'higher_pressure'}], value='central', clearable=False, persistence=True, persistence_type='session')]),
            html.Div([html.Label('WATERSHED MAP METRIC', htmlFor='metric'), dcc.Dropdown(id='metric',
                options=[{'label': label, 'value': key} for key, (label, _) in METRICS.items()], value='crpi_equal', clearable=False, persistence=True, persistence_type='session')]),
            html.Div(className='year-control', children=[html.Label('SELECTED YEAR', htmlFor='year'),
                dcc.Slider(id='year', min=2023, max=2030, step=1, value=2030, marks={y: str(y) for y in range(2023, 2031)}, tooltip={'placement': 'bottom', 'always_visible': False}, persistence=True, persistence_type='session')]),
        ]),
        html.P('Paired screening scenarios: low + optimistic / moderate + business as usual / higher + pessimistic. These are not formally coupled climate-economic pathways. NASA remains SSP2-4.5.', className='scenario-note'),
        html.Section(id='national-cards', className='cards'),
        html.Nav(className='navigation', children=[html.Div(id='breadcrumb'),
            html.Div([html.Button('Back to state', id='back', n_clicks=0), html.Button('Reset to U.S.', id='reset', n_clicks=0)])]),
        html.Section(className='selectors', children=[
            html.Div([html.Label('STATE', htmlFor='state-select'), dcc.Dropdown(id='state-select',
                options=[{'label': f'{r.state_name} ({r.state_abbr})', 'value': r.state_abbr} for r in data.states.sort_values('state_name').itertuples()], placeholder='Click a state or choose here')]),
            html.Div([html.Label('FULL HUC8 WATERSHED', htmlFor='huc-select'), dcc.Dropdown(id='huc-select', options=[], placeholder='Choose a state first')]),
            html.Div([html.Label('MODELED SITE', htmlFor='site-select'), dcc.Dropdown(id='site-select', options=[], placeholder='Select a site on the map or here')]),
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
            html.P('Scenario-based screening estimates; not measured facility consumption. Population indicates proximity, not exposure. Watersheds may cross state boundaries.'),
            html.P('NASA SSP2-4.5 represents projected background climate conditions. Intermediate Aqueduct years are interpolated for screening visualization, not official annual WRI forecasts.'),
            html.P('CRPI is an analyst-defined 0–100 screening index, not a probability of harm. Population stays static at ACS 2023. Gray polygons indicate missing data; they are not zero pressure.'),
            html.P('Open-ended Aqueduct values and interpolations involving their sentinel are censored in numeric displays and charts. Site colors: blue <10%, green 10–20%, amber 20–40%, orange 40–80%, red ≥80% water stress; gray = unavailable.'),
        ]),
    ])
    register_callbacks(app, data)
    return app


def main():
    app = create_app()
    port = int(os.environ.get('PORT', '8050'))
    print(f'Local dashboard: http://127.0.0.1:{port}', flush=True)
    app.run(host='127.0.0.1', port=port, debug=False)


if __name__ == '__main__':
    main()
