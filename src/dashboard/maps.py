"""Plotly maps use local GeoJSON and a tile-free background (no API token)."""
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .data import full_watersheds
from .formatting import HOTSPOTS, METRICS, TEMPORAL, effective_metric, number

CLUSTER_COLORS = ['#226b7a', '#db9246', '#71678e']
HOTSPOT_COLORS = {'persistent_hotspot': '#226b7a', 'emerging_hotspot': '#cc7335',
                  'rising_watchlist': '#71a5b4', 'existing_constrained': '#7c6998',
                  'lower_pressure': '#d5dfe1', 'not_assessable': '#a5a7a7'}


def feature_collection(features):
    return {'type': 'FeatureCollection', 'features': features}


def outlines(geometry):
    lon, lat = [], []
    for shape in geometry:
        polys = [shape] if shape.geom_type == 'Polygon' else list(shape.geoms)
        for poly in polys:
            x, y = poly.exterior.xy
            lon.extend([*x, None]); lat.extend([*y, None])
    return lon, lat


def viewport(bounds):
    west, south, east, north = bounds
    # Mercator span accommodates the entire selected state AND full associated HUC8s.
    span = max(east - west, (north - south) / max(.2, math.cos(math.radians((north + south) / 2))) * 1.5, .1)
    return {'lon': (west + east) / 2, 'lat': (south + north) / 2}, max(1, min(10, math.log2(360 / span) + .55))


def map_figure(data, selection):
    state, huc, site = (selection.get(k) for k in ['selected_state', 'selected_huc8', 'selected_site'])
    year, scenario = int(selection['selected_year']), selection['selected_scenario']
    metric = effective_metric(selection['selected_metric'], year)
    fig = go.Figure()
    states = data.states
    counts = states.state_abbr.map(data.state_counts).fillna(0)
    fig.add_trace(go.Choroplethmap(
        geojson=data.state_geojson, featureidkey='properties.state_abbr', locations=states.state_abbr.tolist(),
        z=counts.tolist() if not state else [0] * len(states),
        colorscale='Teal' if not state else [[0, '#edf1ed'], [1, '#edf1ed']],
        zmin=0, zmax=max(1, counts.max()), showscale=not bool(state),
        marker={'line': {'color': '#a9b8b9', 'width': .7}, 'opacity': 1},
        customdata=[['state', r.state_abbr, r.state_name, int(counts.iloc[i])] for i, r in enumerate(states.itertuples())],
        hovertemplate='<b>%{customdata[2]}</b><br>%{customdata[3]} mapped site records<extra>Click to explore</extra>',
        colorbar={'title': 'Mapped sites', 'thickness': 13, 'len': .65}, name='States', showlegend=False,
    ))
    center, zoom = {'lon': -99, 'lat': 38}, 2.65
    if state:
        geometry = full_watersheds(data.geometry, data.cross, state, data.lower_ids if selection.get('lower_only') else None)
        current = data.watershed_values(year, scenario).reindex(geometry.huc8)
        ids = geometry.huc8.tolist()
        geojson = feature_collection([data.huc_geojson[h] for h in ids])
        categorical = metric in ['cluster_id', 'hotspot_category', 'scenario_robust']
        if categorical:
            if metric == 'cluster_id':
                groups = [(i, f'C{i}', CLUSTER_COLORS[i]) for i in range(3)]
                current['category'] = current.cluster_id
            elif metric == 'hotspot_category':
                groups = [(v, HOTSPOTS[v], c) for v, c in HOTSPOT_COLORS.items()]
                current['category'] = current.hotspot_category
            else:
                groups = [(True, 'WSF top quartile in all pairs', '#226b7a'), (False, 'Other assessable watersheds', '#c3d4d8')]
                current['category'] = current.scenario_robust
            groups.append((None, 'Not available / unassessed', '#acb5b5'))
            for value, label, color in groups:
                mask = current.category.isna() if value is None else current.category.eq(value)
                subset = current.loc[mask]
                if subset.empty:
                    continue
                fig.add_trace(go.Choroplethmap(geojson=geojson, featureidkey='properties.huc8', locations=subset.index.tolist(),
                    z=[1] * len(subset), colorscale=[[0, color], [1, color]], showscale=False,
                    marker={'line': {'width': 1, 'color': 'white'}, 'opacity': .9}, name=label, showlegend=True,
                    customdata=[['huc8', h, label] for h in subset.index],
                    hovertemplate='<b>HUC8 %{customdata[1]}</b><br>%{customdata[2]}<extra>Click watershed</extra>'))
        else:
            values = current[metric].copy()
            if metric == 'median_aqueduct_water_stress' and year not in [2023, 2030]:
                # Saved interpolation of WRI's open-ended sentinel is not a numerical ratio.
                values = values.mask(values.ge(100))
                current = current.copy()
                current[metric] = values
            missing = values.isna()
            if missing.any():
                fig.add_trace(go.Choroplethmap(geojson=geojson, featureidkey='properties.huc8', locations=current.index[missing].tolist(),
                    z=[0] * int(missing.sum()), colorscale=[[0, '#abb6b5'], [1, '#abb6b5']], showscale=False,
                    customdata=[['huc8', h] for h in current.index[missing]],
                    hovertemplate='HUC8 %{customdata[1]}<br>Not available<extra>Click watershed</extra>',
                    marker={'line': {'color': 'white', 'width': 1}}, name='Not available', showlegend=True))
            valid = current.loc[~missing]
            raw = valid[metric]
            # Display-only logarithmic color scale preserves numeric raw values in hover.
            log_color = metric in ['projected_energy_mwh', 'annual_co2_metric_tonnes',
                                   'annual_water_footprint_m3', 'annual_water_scarcity_footprint_m3_eq', 'unique_population_within_5km']
            if metric == 'median_aqueduct_water_stress':
                z = pd.cut(raw, [-np.inf, .1, .2, .4, .8, np.inf], labels=False, right=False)
                ticks, ticktext = [0, 1, 2, 3, 4], ['<10%', '10–20%', '20–40%', '40–80%', '≥80%']
                color_title = 'Water stress'
            elif log_color:
                z = np.log10(1 + raw)
                ticks = np.linspace(z.min(), z.max(), 4).tolist() if len(z) else []
                ticktext = [number(10 ** t - 1, METRICS[metric][1]) for t in ticks]
                color_title = 'Log color scale'
            else:
                z, ticks, ticktext, color_title = raw, None, None, 'CRPI / 100'
            if len(valid):
                fig.add_trace(go.Choroplethmap(geojson=geojson, featureidkey='properties.huc8', locations=valid.index.tolist(),
                    z=z.tolist(), colorscale='Teal', zmin=0 if metric in ['crpi_equal', 'median_aqueduct_water_stress'] else None,
                    zmax=100 if metric == 'crpi_equal' else (4 if metric == 'median_aqueduct_water_stress' else None),
                    marker={'line': {'color': 'white', 'width': 1}, 'opacity': .9},
                    customdata=[['huc8', h, number(v, METRICS[metric][1])] for h, v in raw.items()],
                    hovertemplate='<b>HUC8 %{customdata[1]}</b><br>%{customdata[2]}<extra>Click watershed</extra>',
                    colorbar={'title': color_title, 'thickness': 13, 'len': .65, 'tickvals': ticks, 'ticktext': ticktext},
                    name=METRICS[metric][0], showlegend=False))
        selected_state = states.loc[states.state_abbr.eq(state)]
        lon, lat = outlines(selected_state.geometry)
        fig.add_trace(go.Scattermap(lon=lon, lat=lat, mode='lines', line={'color': '#132f3c', 'width': 3},
                                   hoverinfo='skip', showlegend=False, name='Selected state outline'))
        if huc and huc in ids:
            lon, lat = outlines(geometry.loc[geometry.huc8.eq(huc)].geometry)
            fig.add_trace(go.Scattermap(lon=lon, lat=lat, mode='lines', line={'color': '#ec9139', 'width': 4},
                                       hoverinfo='skip', showlegend=False, name='Selected whole watershed'))
        site_frame = data.site_values(year, scenario, state=state, huc8=huc)
        if selection.get('lower_only'):
            site_frame = site_frame.loc[site_frame.huc8.isin(ids)]
        known = site_frame.dropna(subset=['longitude', 'latitude'])
        stress = pd.cut(known.aqueduct_water_stress, [-np.inf, .1, .2, .4, .8, np.inf], labels=False, right=False)
        if year not in [2023, 2030]:
            stress = stress.mask(known.aqueduct_water_stress.ge(100))
        colors = stress.map({0: '#4389a7', 1: '#64a790', 2: '#d4ad55', 3: '#d87b3c', 4: '#af4541'}).fillna('#808b8b')
        fig.add_trace(go.Scattermap(lon=known.longitude.tolist(), lat=known.latitude.tolist(), mode='markers',
            marker={'size': [15 if s == site else (10 if huc else 7) for s in known.site_id], 'color': colors.tolist(), 'opacity': .9},
            customdata=[['site', r.site_id, r.state_abbr, number(r.projected_energy_mwh, 'MWh'),
                         number(r.aqueduct_water_stress, 'ratio')] for r in known.itertuples()],
            text=known.site_id.tolist(), hovertemplate='<b>%{text}</b> · %{customdata[2]}<br>%{customdata[3]}<br>Water stress %{customdata[4]}<extra>Click site</extra>',
            name='Modeled sites · color = water stress', showlegend=True))
        if not selected_state.empty:
            bounds = selected_state.total_bounds.copy()
            if not geometry.empty:
                b = geometry.total_bounds
                bounds = [min(bounds[0], b[0]), min(bounds[1], b[1]), max(bounds[2], b[2]), max(bounds[3], b[3])]
            center, zoom = viewport(bounds)
    fig.update_layout(map={'style': 'white-bg', 'center': center, 'zoom': zoom},
                      margin={'l': 0, 'r': 0, 't': 0, 'b': 0}, paper_bgcolor='#fafbf8',
                      font={'family': 'Arial, sans-serif', 'color': '#203a43', 'size': 13},
                      legend={'orientation': 'h', 'y': -.02, 'x': 0, 'font': {'size': 11}},
                      uirevision=f'{state}-{huc}-{selection.get("lower_only")}', clickmode='event+select')
    return fig


def temporal_figure(data, selection, metric):
    if metric not in TEMPORAL:
        raise ValueError('Unsupported temporal metric')
    state, huc = selection.get('selected_state'), selection.get('selected_huc8')
    rows = []
    for year in range(2023, 2031):
        scenario = selection['selected_scenario']
        values = data.huc_lookup[(year, scenario)].loc[huc] if huc else data.aggregate_lookup[(state, year, scenario)]
        rows.append(values.get(metric, np.nan))
    # Open-ended Aqueduct sentinel is not plotted as a quantitative 9999 ratio.
    if metric == 'median_aqueduct_water_stress':
        rows = [np.nan if pd.notna(v) and v >= 100 else v for v in rows]
    label, unit = TEMPORAL[metric]
    scale = 1e6 if metric == 'projected_energy_mwh' else 1
    axis_unit = 'TWh' if scale > 1 else unit
    fig = go.Figure(go.Scatter(x=list(range(2023, 2031)), y=[v / scale for v in rows], mode='lines+markers',
                              line={'color': '#226b7a', 'width': 3}, marker={'size': 8}, connectgaps=False,
                              customdata=[number(v, unit) for v in rows], hovertemplate='%{x}: %{customdata}<extra></extra>'))
    fig.add_vline(x=int(selection['selected_year']), line_dash='dot', line_color='#cc7335')
    scope = f'HUC8 {huc}' if huc else (state or 'United States')
    fig.update_layout(title=f'{scope} · {label}', template='plotly_white', height=290,
                      margin={'l': 55, 'r': 25, 't': 45, 'b': 35}, yaxis_title=axis_unit,
                      xaxis={'dtick': 1}, font={'family': 'Arial, sans-serif', 'color': '#203a43'},
                      paper_bgcolor='#fff', uirevision=f'{state}-{huc}-{metric}')
    return fig
