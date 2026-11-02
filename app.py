"""
Dashboard Macroeconómico de Argentina (Dash).

Ejecutar:  .venv/bin/python app.py   ->  http://127.0.0.1:8050
"""
from __future__ import annotations

import logging
import os

from dash import Dash, Input, Output, callback, ctx, dcc, html, no_update
from werkzeug.middleware.proxy_fix import ProxyFix

import ui.theme  # noqa: F401  (registra el template de Plotly)
from pipeline import CSV_FALLBACK, ERROR, FROM_CACHE, MacroData, get_macro_data
from ui.format import fmt_ago, fmt_day, fmt_month
from views import actividad, alta_frecuencia, datos, dinero, externo, fiscal, precios, resumen

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = Dash(
    __name__,
    title="Macro Argentina",
    update_title=None,
    external_stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
    ],
    external_scripts=["https://cdn.plot.ly/plotly-locale-es-latest.js"],
    suppress_callback_exceptions=True,
)
server = app.server
server.wsgi_app = ProxyFix(server.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

RANGE_OPTIONS = [
    {"label": "1A", "value": 1},
    {"label": "3A", "value": 3},
    {"label": "5A", "value": 5},
    {"label": "10A", "value": 10},
    {"label": "Máx", "value": 0},
]

TABS = [
    ("resumen", "Resumen", False),
    ("alta_frecuencia", "Alta frecuencia (diario)", False),
    ("actividad", "Actividad", False),
    ("precios", "Precios y tasas", False),
    ("externo", "Sector externo", False),
    ("fiscal", "Fiscal", False),
    ("dinero", "Dinero, crédito y salarios", False),
    ("datos", "Datos y metodología", False),
]

STATUS_LABEL = {
    "ok": "OK",
    CSV_FALLBACK: "Respaldo CSV",
    FROM_CACHE: "Desde caché",
    ERROR: "Error",
}


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
def header() -> html.Header:
    return html.Header(
        [
            html.Div(
                [
                    html.Div([html.Span(), html.Span(), html.Span()], className="flag", **{"aria-hidden": "true"}),
                    html.Div(
                        [html.H1("Macro Argentina", className="brand-title"),
                         html.Span("Tablero de coyuntura · APIs Oficiales (datos.gob.ar, BCRA v4), XLS y Scraping",
                                   className="brand-sub")],
                    ),
                ],
                className="brand",
            ),
            html.Div(
                [
                    html.Div(
                        [html.Span("Período", className="control-label"),
                         dcc.RadioItems(id="range", options=RANGE_OPTIONS, value=5, inline=True,
                                        className="segmented", persistence=True, persistence_type="local")],
                        className="control",
                    ),
                    html.Div(id="data-status", className="status"),
                    html.Button("↻ Actualizar", id="refresh", n_clicks=0, className="btn",
                                title="Forzar descarga desde las fuentes remotas"),
                ],
                className="toolbar",
            ),
        ],
        className="topbar",
    )


app.layout = html.Div(
    [
        header(),
        html.Div(id="banner"),
        html.Main(
            [
                dcc.Tabs(
                    id="tabs", value="resumen", className="tabs", parent_className="tabs-wrap",
                    children=[
                        dcc.Tab(label=label + (" · pronto" if disabled else ""), value=value, disabled=disabled,
                                className="tab", selected_className="tab--selected",
                                disabled_className="tab--disabled")
                        for value, label, disabled in TABS
                    ],
                ),
                dcc.Loading(html.Div(id="tab-content"), type="dot", color="#6ea8fe", delay_show=300),
            ],
            className="main",
        ),
        html.Footer(
            ["Fuentes: INDEC, BCRA (API v4.0 + ITCRM XLSX), Secretaría de Hacienda, Secretaría de Trabajo, ",
             html.A("apis.datos.gob.ar", href="https://apis.datos.gob.ar/series/api/docs/", target="_blank"),
             ", Bluelytics, DolarAPI y Ámbito/Rava. Los valores reales se expresan a precios del último IPC publicado."],
            className="footer",
        ),
    ],
    className="app",
)


# --------------------------------------------------------------------------- #
# Estado de los datos
# --------------------------------------------------------------------------- #
def status_view(data: MacroData) -> html.Details:
    n_ok, n_tot = data.n_ok, data.n_total
    degraded = any(s["estado"] != "ok" for s in data.series_status.values())
    level = "bad" if data.source == "cache_desactualizada" or n_ok < n_tot else ("warn" if degraded else "good")
    last = max(
        (s.get("ultimo_dato") or "" for s in data.series_status.values() if s.get("frequency", "M") == "M"),
        default="",
    )
    rows = [
        html.Tr([
            html.Td(col.replace("_", " ")),
            html.Td(STATUS_LABEL.get(s["estado"], s["estado"]), className=f"st st--{s['estado']}"),
            html.Td(
                (fmt_day(s.get("ultimo_dato")) if s.get("frequency") == "D" else fmt_month(s.get("ultimo_dato")))
                if s.get("ultimo_dato") else "—"
            ),
        ], title=s.get("detalle") or s.get("descripcion", ""))
        for col, s in data.series_status.items()
    ]
    return html.Details(
        [
            html.Summary(
                [html.Span(className=f"dot dot--{level}"),
                 html.Span(f"{n_ok}/{n_tot} series"),
                 html.Span(f" · descarga {fmt_ago(data.fetched_at)}", className="muted")],
            ),
            html.Div(
                [
                    html.Div([html.Strong("Origen: "),
                              {"api": "Fuentes en vivo (recién descargado)", "cache": "Caché local",
                               "cache_desactualizada": "Caché local (sin conexión remota)"}[data.source]]),
                    html.Div([html.Strong("Último período mensual: "), fmt_month(last) if last else "—"]),
                    html.Table([html.Thead(html.Tr([html.Th("Serie"), html.Th("Estado"), html.Th("Último dato")])),
                                html.Tbody(rows)], className="status-table"),
                ],
                className="status-pop",
            ),
        ],
        className="status-details",
    )


def banner_view(data: MacroData):
    if data.source == "cache_desactualizada":
        return html.Div(
            f"No se pudo conectar con las fuentes remotas. Se muestran datos guardados {fmt_ago(data.fetched_at)}.",
            className="banner banner--warn",
        )
    failed = [c for c, s in data.series_status.items() if s["estado"] == ERROR]
    if failed:
        return html.Div(f"Series sin datos: {', '.join(failed)}.", className="banner banner--bad")
    return None


# --------------------------------------------------------------------------- #
# Callbacks
# --------------------------------------------------------------------------- #
VIEW_MAP = {
    "resumen": resumen.layout,
    "alta_frecuencia": alta_frecuencia.layout,
    "actividad": actividad.layout,
    "precios": precios.layout,
    "externo": externo.layout,
    "fiscal": fiscal.layout,
    "dinero": dinero.layout,
    "datos": datos.layout,
}


@callback(
    Output("tab-content", "children"),
    Output("data-status", "children"),
    Output("banner", "children"),
    Input("tabs", "value"),
    Input("range", "value"),
    Input("refresh", "n_clicks"),
)
def render(tab: str, years: int, _clicks: int):
    try:
        force = ctx.triggered_id == "refresh"
    except Exception:  # noqa: BLE001
        force = False
    try:
        data = get_macro_data(force=force)
    except Exception as e:  # noqa: BLE001
        logging.exception("No hay datos disponibles")
        msg = html.Div(f"No se pudieron obtener datos y no hay caché local: {e}", className="banner banner--bad")
        return html.Div(), no_update, msg

    view_fn = VIEW_MAP.get(tab, resumen.layout)
    content = view_fn(data, years or None)
    return content, status_view(data), banner_view(data)


@callback(
    Output("download-monthly-csv", "data"),
    Input("btn-download-monthly", "n_clicks"),
    prevent_initial_call=True,
)
def download_monthly_csv(n_clicks: int):
    if not n_clicks:
        return no_update
    data = get_macro_data(force=False)
    return dcc.send_data_frame(data.df.to_csv, "macro_argentina_mensual.csv", index=False)


@callback(
    Output("download-daily-csv", "data"),
    Input("btn-download-daily", "n_clicks"),
    prevent_initial_call=True,
)
def download_daily_csv(n_clicks: int):
    if not n_clicks:
        return no_update
    data = get_macro_data(force=False)
    return dcc.send_data_frame(data.daily_df.to_csv, "macro_argentina_diario.csv", index=False)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("DASH_HOST", "127.0.0.1"),
        port=int(os.environ.get("DASH_PORT", "8050")),
        debug=os.environ.get("DASH_DEBUG", "0") == "1",
    )
