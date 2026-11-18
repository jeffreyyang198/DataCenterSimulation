"""Pure navigation reducer and Dash wiring; selections remain hierarchical."""
import pandas as pd
from dash import Input, Output, State, ctx, html

from .data import PAIRS, full_watersheds
from .formatting import HOTSPOTS, METRICS, TEMPORAL, effective_metric, number
from .maps import map_figure, temporal_figure

INITIAL = {'selected_state': None, 'selected_huc8': None, 'selected_site': None,
           'selected_year': 2030, 'selected_scenario': 'central', 'selected_metric': 'crpi_equal', 'lower_only': False}


def navigate(previous, kind, identifier, data=None):
    """A new state clears HUC8/site; a new HUC8 clears site. Controls persist."""
    state = {**INITIAL, **(previous or {})}
    if kind == 'reset':
        state.update(selected_state=None, selected_huc8=None, selected_site=None)
    elif kind == 'back':
        state.update(selected_huc8=None, selected_site=None)
    elif kind == 'demo' and identifier in data.demo_examples:
        state.update(selected_state=data.demo_examples[identifier][0], selected_huc8=identifier,
                     selected_site=None, lower_only=False)
    elif kind == 'state':
        if data is None or identifier is None or identifier in set(data.states.state_abbr):
            state.update(selected_state=identifier, selected_huc8=None, selected_site=None)
    elif kind == 'huc8':
        allowed = data.state_hucs.get(state['selected_state'], set()) if data else None
        if identifier is None or allowed is None or identifier in allowed:
            state.update(selected_huc8=identifier, selected_site=None)
    elif kind == 'site':
        if identifier is None:
            state['selected_site'] = None
        elif data is None:
            state['selected_site'] = identifier
        else:
            sites = getattr(data, 'site_identity', None)
            if sites is None:
                sites = data.sites.set_index('site_id')
            if identifier in sites.index:
                site = sites.loc[identifier]
                # A selected watershed intentionally permits its cross-state records.
                allowed = (pd.notna(site.huc8) and site.huc8 == state['selected_huc8']
                           if state['selected_huc8'] else site.state_abbr == state['selected_state'])
                if allowed:
                    state['selected_site'] = identifier
                    state['selected_huc8'] = None if pd.isna(site.huc8) else site.huc8
    return state


def normalize_selection(previous, data):
    state = {**INITIAL, **(previous if isinstance(previous, dict) else {})}
    if state['selected_state'] not in data.state_names:
        state = navigate(state, 'reset', None)
    if state['selected_huc8'] not in data.state_hucs.get(state['selected_state'], set()):
        state['selected_huc8'] = None
    allowed_sites = (data.huc_sites.get(state['selected_huc8'], set()) if state['selected_huc8']
                     else data.state_sites.get(state['selected_state'], set()))
    if state['selected_site'] not in allowed_sites:
        state['selected_site'] = None
    for key, valid in [('selected_year', range(2023, 2031)), ('selected_scenario', PAIRS), ('selected_metric', METRICS)]:
        if state[key] not in valid:
            state[key] = INITIAL[key]
    return state


def metric_rows(values, fields):
    children = []
    for field, label, unit in fields:
        if field in values:
            formatted = number(values[field], unit)
            children.extend([html.Dt(label), html.Dd('Data unavailable' if formatted == 'Not available' else formatted)])
    return html.Dl(children, className='metrics-list')


MAIN_FIELDS = [
    ('projected_energy_mwh', 'Electricity demand', 'MWh'),
    ('annual_co2_metric_tonnes', 'Annual CO₂', 'tonnes CO₂'),
    ('cumulative_co2_metric_tonnes', 'Cumulative CO₂ since 2023', 'tonnes CO₂'),
    ('annual_direct_water_m3', 'Modeled direct water demand', 'm³'),
    ('cumulative_direct_water_m3', 'Cumulative direct water since 2023', 'm³'),
    ('annual_water_footprint_m3', 'Water footprint · direct + indirect', 'm³'),
    ('annual_water_scarcity_footprint_m3_eq', 'Scarcity-weighted water footprint', 'm³-eq'),
]
CONTEXT_FIELDS = [
    ('median_aqueduct_water_stress', 'Aqueduct median water stress', 'ratio'),
    ('max_aqueduct_water_stress', 'Aqueduct maximum water stress', 'ratio'),
    ('median_aqueduct_water_depletion', 'Aqueduct median depletion', 'ratio'),
    ('median_temperature_mean_c', 'NASA SSP2-4.5 mean temperature', '°C'),
    ('median_warmest_day_mean_c', 'NASA warmest-day mean temperature', '°C'),
]


def summary_panel(data, selection):
    state, huc, site = [selection.get(k) for k in ['selected_state', 'selected_huc8', 'selected_site']]
    year, scenario = int(selection['selected_year']), selection['selected_scenario']
    frame = data.site_values(year, scenario, state=state, huc8=huc)
    if site and site in frame.index:
        row = frame.loc[site]
        identity = data.site_identity.loc[site]
        children = [html.Div('MODELED SITE', className='eyebrow'), html.H2(identity.site_name if pd.notna(identity.site_name) else site),
                    html.P(f'{identity.state_abbr} · HUC8 {identity.huc8 if pd.notna(identity.huc8) else "unassigned"}'),
                    html.Div()]
        # Keep identifiers separate from modeled quantities.
        children[-1] = html.Dl([item for label, key in [('Operator', 'operator'), ('Site type', 'site_type')]
                               for item in [html.Dt(label), html.Dd(str(identity[key]) if pd.notna(identity[key]) else 'Not available')]], className='metrics-list')
        children += [html.H3(f'{year} · {scenario.replace("_", " ")}'), metric_rows(row, MAIN_FIELDS),
                     metric_rows(row, [('aqueduct_water_stress', 'Aqueduct water stress', 'ratio'),
                                      ('pop_1km', 'Nearby population · 1 km', 'people'),
                                      ('pop_3km', 'Nearby population · 3 km', 'people'),
                                      ('pop_5km', 'Nearby population · 5 km', 'people'),
                                      ('temperature_mean_c', 'NASA mean temperature', '°C'),
                                      ('warmest_day_mean_c', 'NASA warmest-day mean', '°C')]),
                     html.P('Site values are scenario-based modeled estimates, not measured facility consumption. Population represents proximity, not direct exposure.', className='note')]
        flags = {r: row.get(f'incomplete_pop_{r}km') for r in (1, 3, 5)}
        incomplete = [str(r) for r, flag in flags.items() if pd.notna(flag) and flag]
        if incomplete:
            children += [html.P('Partial population coverage at ' + ', '.join(incomplete) + ' km; estimates may be incomplete.', className='note')]
        return children
    if huc:
        values = data.huc_lookup[(year, scenario)].loc[huc]
        context = data.context_lookup.loc[huc]
        represented = ', '.join(sorted(data.sites.loc[data.sites.huc8.eq(huc), 'state_abbr'].unique()))
        robust = context.scenario_robust
        robust_label = 'Not assessable' if pd.isna(robust) else ('Top WSF quartile in all three pairs' if bool(robust) else 'Outside robust top WSF quartile')
        children = [html.Div('FULL WATERSHED', className='eyebrow'), html.H2(data.huc_names[huc]),
                    html.P(f'HUC8 {huc}', className='technical'),
                    html.P(f'{represented} · {int(values.site_count)} mapped site records'),
                    html.Div(str(context.cluster_label) if pd.notna(context.cluster_label) else 'Insufficient data for clustering', className='profile-label'),
                    html.P(HOTSPOTS.get(context.hotspot_category, 'Not available')),
                    html.P(robust_label, className='note'),
                    html.P('Cluster, trajectory and robustness labels summarize the 2030 / 2023–2030 analysis.', className='note technical')]
        if year == 2030:
            score = data.watershed_values(year, scenario).loc[huc, 'crpi_equal']
            children += [html.P('CRPI · ' + number(score, 'score / 100'), className='profile-label')]
        children += [html.H3(f'{year} · selected scenario'), metric_rows(values, MAIN_FIELDS), metric_rows(values, CONTEXT_FIELDS)]
    else:
        values = data.aggregate_lookup[(state, year, scenario)]
        name = data.state_names.get(state, 'United States')
        n_hucs = len(data.state_hucs.get(state, set())) if state else len(data.geometry)
        children = [html.Div('STATE SUMMARY' if state else 'NATIONAL OVERVIEW', className='eyebrow'), html.H2(name),
                    html.P(f'{int(values["site_count"]):,} mapped site records · {n_hucs} HUC8 watersheds'),
                    html.P('Click a watershed to explore its complete hydrologic unit.' if state else 'Click a state to reveal full watersheds and modeled sites.', className='note'),
                    html.H3(f'{year} · selected scenario'), metric_rows(values, MAIN_FIELDS), metric_rows(values, CONTEXT_FIELDS)]
    population, note = data.proximity(huc, national=not state)
    children += [html.H3('Community proximity'), html.P(number(population, 'people'), className='population-value'), html.P(note, className='note')]
    children += [html.P(f'Available estimates: {frame.projected_energy_mwh.notna().sum():,}/{len(frame):,} electricity; '
                        f'{frame.annual_co2_metric_tonnes.notna().sum():,}/{len(frame):,} CO₂; '
                        f'{frame.annual_water_scarcity_footprint_m3_eq.notna().sum():,}/{len(frame):,} WF/WSF. '
                        'Sums cover available records.', className='note technical')]
    return children


def register_callbacks(app, data):
    @app.callback(Output('selection', 'data'), Output('state-select', 'value'), Output('huc-select', 'value'), Output('site-select', 'value'),
                  Output('demo', 'value'), Output('lower-filter', 'value'),
                  Input('map', 'clickData'), Input('state-select', 'value'), Input('huc-select', 'value'), Input('site-select', 'value'),
                  Input('year', 'value'), Input('scenario', 'value'), Input('metric', 'value'), Input('lower-filter', 'value'),
                  Input('reset', 'n_clicks'), Input('back', 'n_clicks'), Input('clear-site', 'n_clicks'),
                  Input('demo', 'value'), State('selection', 'data'))
    def update_selection(click, state, huc, site, year, scenario, metric, lower, reset, back, clear, demo, previous):
        selection = normalize_selection(previous, data)
        selection.update(selected_year=year, selected_scenario=scenario, selected_metric=metric, lower_only='lower' in (lower or []))
        trigger = ctx.triggered_id
        if trigger == 'map' and click and click.get('points'):
            custom = click['points'][0].get('customdata')
            if custom and len(custom) >= 2:
                selection = navigate(selection, custom[0], custom[1], data)
        elif trigger in ['state-select', 'huc-select', 'site-select']:
            kind, identifier = {'state-select': ('state', state), 'huc-select': ('huc8', huc), 'site-select': ('site', site)}[trigger]
            selection = navigate(selection, kind, identifier, data)
        elif trigger in ['reset', 'back']:
            selection = navigate(selection, trigger, None, data)
        elif trigger == 'clear-site':
            selection = navigate(selection, 'site', None, data)
        elif trigger == 'demo' and demo:
            selection = navigate(selection, 'demo', demo, data)
        selection = normalize_selection(selection, data)
        if selection['lower_only'] and selection.get('selected_huc8') not in data.lower_ids:
            selection.update(selected_huc8=None, selected_site=None)
        return (selection, selection['selected_state'], selection['selected_huc8'], selection['selected_site'],
                None, ['lower'] if selection['lower_only'] else [])

    @app.callback(Output('map', 'figure'), Output('summary', 'children'), Output('national-cards', 'children'),
                  Output('temporal', 'figure'), Output('breadcrumb', 'children'), Output('map-note', 'children'),
                  Output('huc-select', 'options'), Output('site-select', 'options'), Output('shell', 'className'),
                  Output('year-indicator', 'children'), Output('back', 'disabled'), Output('clear-site', 'disabled'),
                  Input('selection', 'data'), Input('temporal-metric', 'value'), Input('presentation', 'value'))
    def render(selection, temporal_metric, presentation):
        selection = normalize_selection(selection, data)
        selection['projector'] = 'on' in (presentation or [])
        if temporal_metric not in TEMPORAL:
            temporal_metric = 'projected_energy_mwh'
        state, huc = selection['selected_state'], selection['selected_huc8']
        year, scenario = selection['selected_year'], selection['selected_scenario']
        national = data.aggregate_lookup[(None, year, scenario)]
        cards = [html.Div([html.Span(label), html.Strong(number(national[key], unit))], className='summary-card') for key, label, unit in [
            ('site_count', 'U.S. mapped sites', ''), ('projected_energy_mwh', 'U.S. electricity', 'MWh'),
            ('annual_co2_metric_tonnes', 'U.S. annual CO₂', 'tonnes CO₂'), ('annual_direct_water_m3', 'U.S. direct water demand', 'm³')]]
        crumb = 'United States' + (f'  /  {state}' if state else '') + (f'  /  HUC8 {huc}' if huc else '') + ('  /  Site' if selection.get('selected_site') else '')
        metric = effective_metric(selection['selected_metric'], year)
        note = ('Mapped site counts · click a state. All 56 state/equivalent areas are available in the state selector; pan to Alaska, Hawaii and territories.' if not state else
                f'{METRICS[metric][0]} · full watersheds retained across state borders. Dark outline = selected state.')
        if selection['selected_metric'] == 'crpi_equal' and year != 2030 and state:
            note += ' CRPI is validated for 2030 only; this year shows WSF.'
        if metric in ['cluster_id', 'hotspot_category', 'scenario_robust'] and state:
            note += ' Saved 2030 / trajectory classification; labels do not change with year.'
        if selection.get('lower_only'):
            note += ' Lower-pressure filter applies to the map. Summary totals cover the full selection.'
        geometry = full_watersheds(data.geometry, data.cross, state, data.lower_ids if selection.get('lower_only') else None) if state else data.geometry.iloc[:0]
        huc_options = [{'label': r.subbasin_name, 'value': r.huc8} for r in geometry.sort_values('subbasin_name').itertuples()]
        sites = data.site_values(year, scenario, state=state, huc8=huc) if state else data.annual.iloc[:0]
        if selection.get('lower_only'):
            sites = sites.loc[sites.huc8.isin(set(geometry.huc8))]
        site_options = [{'label': f'{data.site_identity.loc[r.site_id, "site_name"]} · {r.state_abbr}', 'value': r.site_id}
                        for r in sites.itertuples()]
        return (map_figure(data, selection), summary_panel(data, selection), cards,
                temporal_figure(data, selection, temporal_metric), crumb, note, huc_options, site_options,
                'dashboard presentation' if selection['projector'] else 'dashboard',
                str(year), not bool(state and huc), not bool(selection.get('selected_site')))
