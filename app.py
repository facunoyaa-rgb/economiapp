"""
Dashboard Macroeconómico de Argentina (Dash).

Ejecutar:  .venv/bin/python app.py   ->  http://127.0.0.1:8050
"""
from __future__ import annotations

import logging
import os

from dash import ALL, Dash, Input, Output, State, callback, clientside_callback, ctx, dcc, html, no_update
from werkzeug.middleware.proxy_fix import ProxyFix

import ui.theme  # noqa: F401  (registra el template de Plotly)
from pipeline import CSV_FALLBACK, ERROR, FROM_CACHE, MacroData, get_macro_data
from ui.format import fmt_ago, fmt_day, fmt_month
from views import actividad, alta_frecuencia, datos, dinero, externo, fiscal, precios, resumen

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

APP_NAME = "EconomiApp"
APP_DESCRIPTION = ("Tablero de coyuntura macroeconómica argentina: actividad, precios, tasas, sector externo, "
                   "fiscal, dinero y salarios, con 77 series oficiales y de mercado.")
PUBLIC_URL = os.environ.get("ECONOMIAPP_PUBLIC_URL", "https://economiapp.noya.com.ar").rstrip("/")
REPO_URL = "https://github.com/facunoyaa-rgb/economiapp"
AUTHOR = os.environ.get("ECONOMIAPP_AUTHOR", "Facundo Octavio Noya, Lic. en Economía")

app = Dash(
    __name__,
    title=APP_NAME,
    update_title=None,
    external_stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
    ],
    external_scripts=["https://cdn.plot.ly/plotly-locale-es-latest.js"],
    suppress_callback_exceptions=True,
    # Carga plotly.js junto con el resto de los scripts, en vez de pedirlo recién después del primer callback.
    eager_loading=True,
)
server = app.server
server.wsgi_app = ProxyFix(server.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.index_string = f"""<!DOCTYPE html>
<html lang="es-AR">
    <head>
        {{%metas%}}
        <title>{{%title%}}</title>
        <meta name="description" content="{APP_DESCRIPTION}">
        <meta name="theme-color" content="#0e1117">
        <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
        <meta property="og:type" content="website">
        <meta property="og:locale" content="es_AR">
        <meta property="og:site_name" content="{APP_NAME}">
        <meta property="og:title" content="{APP_NAME} · Coyuntura macroeconómica argentina">
        <meta property="og:description" content="{APP_DESCRIPTION}">
        <meta property="og:url" content="{PUBLIC_URL}/">
        <meta property="og:image" content="{PUBLIC_URL}/assets/og-image.png">
        <meta property="og:image:width" content="1200">
        <meta property="og:image:height" content="630">
        <meta name="twitter:card" content="summary_large_image">
        {{%favicon%}}
        {{%css%}}
    </head>
    <body>
        {{%app_entry%}}
        <footer>
            {{%config%}}
            {{%scripts%}}
            {{%renderer%}}
        </footer>
    </body>
</html>"""

RANGE_OPTIONS = [
    {"label": "1A", "value": 1},
    {"label": "3A", "value": 3},
    {"label": "5A", "value": 5},
    {"label": "10A", "value": 10},
    {"label": "Máx", "value": 0},
]
RANGE_VALUES = {o["value"] for o in RANGE_OPTIONS}
DEFAULT_RANGE = 5

# (clave interna de la vista, fragmento de la URL, etiqueta)
TABS = [
    ("resumen", "resumen", "Resumen"),
    ("alta_frecuencia", "alta-frecuencia", "Alta frecuencia (diario)"),
    ("actividad", "actividad", "Actividad"),
    ("precios", "precios", "Precios y tasas"),
    ("externo", "externo", "Sector externo"),
    ("fiscal", "fiscal", "Fiscal"),
    ("dinero", "dinero", "Dinero, crédito y salarios"),
    ("datos", "datos", "Datos y metodología"),
]
HASH_TO_VIEW = {slug: key for key, slug, _ in TABS}

STATUS_LABEL = {
    "ok": "OK",
    CSV_FALLBACK: "Respaldo CSV",
    FROM_CACHE: "Desde caché",
    ERROR: "Error",
}


def view_from_hash(hash_: str | None) -> str:
    """'#fiscal' -> 'fiscal'. Un fragmento vacío o desconocido abre el Resumen."""
    return HASH_TO_VIEW.get((hash_ or "").lstrip("#"), "resumen")


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
def header() -> html.Header:
    return html.Header(
        [
            html.A(
                [
                    html.Div([html.Span(), html.Span(), html.Span()], className="flag", **{"aria-hidden": "true"}),
                    html.Div(
                        [html.H1(APP_NAME, className="brand-title"),
                         html.Span("Coyuntura macroeconómica argentina · 77 series oficiales y de mercado",
                                   className="brand-sub")],
                    ),
                ],
                href="#resumen",
                className="brand",
                title="Ir al Resumen",
            ),
            html.Div(
                [
                    html.Div(
                        [html.Span("Período", className="control-label", id="range-label"),
                         dcc.RadioItems(id="range", options=RANGE_OPTIONS, value=DEFAULT_RANGE, inline=True,
                                        className="segmented", persistence=True, persistence_type="local")],
                        className="control",
                        role="radiogroup",
                        **{"aria-labelledby": "range-label"},
                    ),
                    html.Div(id="data-status", className="status"),
                    html.Button("↻ Actualizar", id="refresh", n_clicks=0, className="btn",
                                title="Volver a descargar los datos de las fuentes (como máximo cada 15 min)"),
                ],
                className="toolbar",
            ),
        ],
        className="topbar",
    )


def nav() -> html.Nav:
    return html.Nav(
        [html.A(label, href=f"#{slug}", id={"type": "nav-link", "index": slug}, className="nav-link")
         for _, slug, label in TABS],
        className="nav",
        **{"aria-label": "Secciones del tablero"},
    )


def footer() -> html.Footer:
    about = [html.Strong(APP_NAME), " · "]
    if AUTHOR:
        about += [f"Desarrollada por {AUTHOR}", " · "]
    about += ["Python, Dash, Plotly y pandas · ",
              html.A("Código en GitHub", href=REPO_URL, target="_blank", rel="noopener")]
    return html.Footer(
        [
            html.P(about, className="footer-about"),
            html.P(
                ["Fuentes: INDEC, BCRA, Secretaría de Hacienda, Secretaría de Trabajo (vía ",
                 html.A("apis.datos.gob.ar", href="https://apis.datos.gob.ar/series/api/docs/", target="_blank",
                        rel="noopener"),
                 "), Bluelytics, DolarAPI, Ámbito y Rava. Los valores reales se expresan en pesos del último mes "
                 "con IPC publicado."],
            ),
        ],
        className="footer",
    )


app.layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),
        html.A("Saltar al contenido", href="#contenido", className="skip-link"),
        header(),
        html.Div(id="banner", role="status"),
        html.Main(
            [
                nav(),
                dcc.Loading(html.Div(id="tab-content"), type="dot", color="#6ea8fe", delay_show=300,
                            parent_className="loading-wrap"),
            ],
            className="main",
            id="contenido",
        ),
        footer(),
    ],
    className="app",
)

# Enlace activo de la navegación (en el navegador, sin ida al servidor)
clientside_callback(
    """
    function(hash, ids) {
        var slug = (hash || "").replace(/^#/, "");
        var known = ids.map(function (i) { return i.index; });
        if (known.indexOf(slug) === -1) { slug = "resumen"; }
        return ids.map(function (i) {
            var a = document.getElementById(JSON.stringify({index: i.index, type: "nav-link"}));
            if (a) { if (i.index === slug) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); }
            return i.index === slug ? "nav-link nav-link--active" : "nav-link";
        });
    }
    """,
    Output({"type": "nav-link", "index": ALL}, "className"),
    Input("url", "hash"),
    State({"type": "nav-link", "index": ALL}, "id"),
)

# Período <-> ?p= en la URL. Es un solo callback para que la dependencia circular sea válida.
clientside_callback(
    """
    function(search, value) {
        var NU = window.dash_clientside.no_update;
        var allowed = %s;
        var trig = (dash_clientside.callback_context.triggered || []).map(function (t) { return t.prop_id; });
        var m = /[?&]p=(\\d+)/.exec(search || "");
        var fromUrl = m ? parseInt(m[1], 10) : null;
        if (fromUrl !== null && allowed.indexOf(fromUrl) === -1) { fromUrl = null; }
        var rangeChanged = trig.indexOf("range.value") !== -1;
        var urlChanged = trig.indexOf("url.search") !== -1;
        if (rangeChanged && !urlChanged) {
            return [NU, fromUrl === value ? NU : "?p=" + value];
        }
        if (fromUrl !== null) {
            return [fromUrl === value ? NU : fromUrl, NU];
        }
        return [NU, "?p=" + value];
    }
    """ % sorted(RANGE_VALUES),
    Output("range", "value"),
    Output("url", "search"),
    Input("url", "search"),
    Input("range", "value"),
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
    if data.refresh_skipped:
        return html.Div(
            f"Los datos ya están al día: se descargaron {fmt_ago(data.fetched_at)}. Para no saturar a las fuentes, "
            f"se vuelven a pedir como máximo cada {data.min_refresh_minutes} minutos.",
            className="banner banner--info",
        )
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
    Input("url", "hash"),
    Input("range", "value"),
    Input("refresh", "n_clicks"),
    running=[
        (Output("refresh", "disabled"), True, False),
        (Output("refresh", "children"), "Actualizando…", "↻ Actualizar"),
    ],
)
def render(hash_: str | None, years: int, _clicks: int):
    tab = view_from_hash(hash_)
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
