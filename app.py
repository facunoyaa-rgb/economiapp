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
                         html.Span("Coyuntura macroeconómica argentina · 77 series oficiales y de mercado",
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
            ["Fuentes: INDEC, BCRA, Secretaría de Hacienda, Secretaría de Trabajo, ",
             html.A("apis.datos.gob.ar", href="https://apis.datos.gob.ar/series/api/docs/", target="_blank", rel="noopener"),
             ", Bluelytics, DolarAPI, Ámbito y Rava. Los valores reales se expresan en pesos del último mes con IPC publicado."],
            className="footer",
        ),
    ],
    className="app",
)


# --------------------------------------------------------------------------- #
# Estado de los datos
# --------------------------------------------------------------------------- #
def _last_period_text(data: MacroData) -> str:
    """Último dato del IPC (marca el mes de cierre del panel mensual) y última rueda diaria.

    No se usa la fecha máxima del panel mensual: incluye promedios de series diarias del mes en curso.
    """
    df, daily = data.df, data.daily_df
    parts = []
    if "IPC_Nivel_General" in df and df["IPC_Nivel_General"].notna().any():
        parts.append(f"IPC {fmt_month(df.loc[df['IPC_Nivel_General'].notna(), 'Fecha'].max())}")
    if daily is not None and not daily.empty and "Fecha" in daily:
        # UVA, UVI, CER e ICL se publican por adelantado: no cuentan como "última rueda"
        market = [c for c in daily.columns if c not in {"Fecha", "UVA", "UVI", "CER", "ICL"}]
        mask = daily[market].notna().any(axis=1) if market else daily["Fecha"].notna()
        if mask.any():
            parts.append(f"diarias {fmt_day(daily.loc[mask, 'Fecha'].max())}")
    return " · ".join(parts) or "—"


def status_view(data: MacroData) -> html.Details:
    n_ok, n_tot = data.n_ok, data.n_total
    not_ok = {c: s for c, s in data.series_status.items() if s["estado"] != "ok"}
    level = "bad" if data.source == "cache_desactualizada" or n_ok < n_tot else ("warn" if not_ok else "good")
    by_state: dict[str, int] = {}
    for s in not_ok.values():
        by_state[s["estado"]] = by_state.get(s["estado"], 0) + 1
    state_phrase = {CSV_FALLBACK: "desde el respaldo CSV", FROM_CACHE: "desde la caché anterior", ERROR: "con error"}
    state_txt = ", ".join(
        f"{n} {'serie' if n == 1 else 'series'} {state_phrase.get(e, e)}" for e, n in by_state.items()
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
        # primero las series con problemas
        for col, s in sorted(data.series_status.items(), key=lambda kv: kv[1]["estado"] == "ok")
    ]
    return html.Details(
        [
            html.Summary(
                [html.Span(className=f"dot dot--{level}", **{"aria-hidden": "true"}),
                 html.Span(f"{n_ok}/{n_tot} series"),
                 html.Span(f" · descarga {fmt_ago(data.fetched_at)}", className="muted")],
                title=state_txt or "Todas las series se descargaron correctamente",
            ),
            html.Div(
                [
                    html.Div([html.Strong("Origen: "),
                              {"api": "Fuentes en vivo (recién descargado)", "cache": "Caché local",
                               "cache_desactualizada": "Caché local (sin conexión remota)"}[data.source]]),
                    html.Div([html.Strong("Últimos datos: "), _last_period_text(data)]),
                    html.Div([html.Strong("Atención: "), state_txt]) if state_txt else None,
                    html.Table([html.Thead(html.Tr([html.Th("Serie"), html.Th("Estado"), html.Th("Último dato")])),
                                html.Tbody(rows)], className="status-table"),
                ],
                className="status-pop",
            ),
        ],
        className="status-details",
        id="status-details",
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
