"""Pestaña Explorador: hasta 4 series a elección, con transformaciones, eje derecho, escala log y rango.

El estado completo queda en la URL (`?s=EMAE_Desestacionalizado,d.TC_Mayorista&t=ia&der=...#explorador`),
así que un análisis se puede guardar en marcadores o compartir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qs

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback, clientside_callback, dcc, html, no_update

from indicators import real_base_month
from pipeline import MacroData, get_macro_data
from series_meta import GROUP_ORDER, HIDDEN, REAL, meta
from ui.charts import chart_or_empty
from ui.components import card
from ui.format import fmt_day, fmt_month, fmt_num
from ui.theme import SERIES, color, set_theme

MAX_SERIES = 4
DAILY_PREFIX = "d."
DEFAULT_SERIES = ["EMAE_Desestacionalizado", "IPI_Desestacionalizado", "ISAC_Desestacionalizado"]

TRANSFORMS = [
    ("nivel", "Nivel"),
    ("mm", "Var. % mensual"),
    ("ia", "Var. % interanual"),
    ("s12", "Suma 12 meses"),
    ("b100", "Base 100"),
]
TRANSFORM_KEYS = {k for k, _ in TRANSFORMS}
TRANSFORM_HELP = (
    "Nivel: la serie tal como se publica. Var. % mensual e interanual: contra el mismo día del mes o del año "
    "anterior; en series que ya son tasas o porcentajes, la diferencia en puntos porcentuales. Suma 12 meses: "
    "acumulado móvil, solo para flujos mensuales (comercio exterior, fiscal). Base 100: cada serie dividida por "
    "su valor en la fecha base (si no se elige, el inicio del rango)."
)


# --------------------------------------------------------------------------- #
# Estado <-> URL
# --------------------------------------------------------------------------- #
@dataclass
class ExplorerState:
    series: list[str] = field(default_factory=lambda: list(DEFAULT_SERIES))
    transform: str = "nivel"
    log: bool = False
    right: list[str] = field(default_factory=list)
    base: str | None = None
    start: str | None = None
    end: str | None = None


def _valid_date(v: str | None) -> str | None:
    if not v:
        return None
    try:
        return pd.Timestamp(v).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def parse_state(search: str | None, valid_keys: set[str] | None = None) -> ExplorerState:
    """Lee el estado del Explorador de la query string. Lo que no se reconoce se descarta."""
    q = parse_qs((search or "").lstrip("?"), keep_blank_values=True)

    def one(k):
        return (q.get(k) or [None])[0]

    def keys(k):
        raw = one(k)
        out = [s for s in (raw.split(",") if raw else []) if s]
        if valid_keys is not None:
            out = [s for s in out if s in valid_keys]
        return list(dict.fromkeys(out))  # sin duplicados, en orden

    st = ExplorerState()
    if one("s") is not None:
        st.series = keys("s")[:MAX_SERIES]
    elif valid_keys is not None:
        st.series = [s for s in st.series if s in valid_keys]
    st.transform = one("t") if one("t") in TRANSFORM_KEYS else "nivel"
    st.log = one("log") == "1"
    st.right = [s for s in keys("der") if s in st.series]
    st.base = _valid_date(one("base"))
    st.start = _valid_date(one("desde"))
    st.end = _valid_date(one("hasta"))
    return st


# --------------------------------------------------------------------------- #
# Series y transformaciones
# --------------------------------------------------------------------------- #
def series_key(col: str, daily: bool) -> str:
    return f"{DAILY_PREFIX}{col}" if daily else col


def split_key(key: str) -> tuple[str, bool]:
    return (key[len(DAILY_PREFIX):], True) if key.startswith(DAILY_PREFIX) else (key, False)


def series_options(data: MacroData) -> list[dict]:
    """Opciones del buscador: todas las columnas mensuales y diarias, ordenadas por grupo."""
    opts = []
    for df, daily in ((data.df, False), (data.daily_df, True)):
        if df is None or df.empty:
            continue
        for col in df.columns:
            if col == "Fecha" or col in HIDDEN or not df[col].notna().any():
                continue
            m = meta(col)
            freq = "diaria" if daily else "mensual"
            opts.append({
                "label": f"{m.label} · {freq}",
                "value": series_key(col, daily),
                "search": f"{m.label} {m.group} {freq} {col}",
                "_order": (GROUP_ORDER.index(m.group) if m.group in GROUP_ORDER else 99, daily, m.label),
            })
    opts.sort(key=lambda o: o.pop("_order"))
    return opts


def get_series(data: MacroData, key: str) -> pd.Series | None:
    col, daily = split_key(key)
    df = data.daily_df if daily else data.df
    if df is None or col not in df:
        return None
    s = df.set_index("Fecha")[col].dropna().astype(float).sort_index()
    return s if not s.empty else None


def _lagged(s: pd.Series, months: int, daily: bool) -> pd.Series:
    """Valor de la serie `months` meses antes de cada fecha.

    Mensual: el mes exacto (si falta, queda vacío). Diaria: el último dato hasta 7 días antes de esa fecha,
    para cubrir fines de semana y feriados.
    """
    target = pd.DataFrame({"Fecha": s.index - pd.DateOffset(months=months)})
    src = pd.DataFrame({"Fecha": s.index, "prev": s.to_numpy()})
    tol = pd.Timedelta(days=7) if daily else pd.Timedelta(0)
    merged = pd.merge_asof(target, src, on="Fecha", direction="backward", tolerance=tol)
    return pd.Series(merged["prev"].to_numpy(), index=s.index)


def transform_series(s: pd.Series, kind: str, how: str, daily: bool,
                     base_date: pd.Timestamp | None = None) -> tuple[pd.Series | None, str | None]:
    """Aplica la transformación. Devuelve (serie, nota). Si no corresponde, la serie es None y la nota explica por qué."""
    if how == "nivel":
        return s, None
    if how in ("mm", "ia"):
        prev = _lagged(s, 1 if how == "mm" else 12, daily)
        if kind == "rate":
            return (s - prev).dropna(), None
        valid = prev > 0
        out = (s / prev.where(valid) - 1) * 100
        note = "la variación % no está definida cuando el valor anterior es negativo o cero" \
            if (~valid & prev.notna()).any() else None
        return out.dropna(), note
    if how == "s12":
        if daily or kind != "flow":
            return None, "la suma de 12 meses solo se aplica a flujos mensuales"
        grid = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="MS"))
        return grid.rolling(12, min_periods=12).sum().dropna(), None
    if how == "b100":
        if kind == "rate":
            return None, "una tasa o un porcentaje no se lleva a base 100"
        ref = s[s.index >= base_date] if base_date is not None else s
        if ref.empty or ref.iloc[0] == 0 or pd.isna(ref.iloc[0]):
            return None, "no hay dato en la fecha base"
        return s / ref.iloc[0] * 100, None
    return s, None


def _axis_unit(key: str, how: str, data: MacroData, base_label: str) -> str:
    col, _ = split_key(key)
    m = meta(col)
    unit = f"Millones de $ de {real_base_month(data.df)}" if m.unit == REAL else m.unit
    if how == "nivel":
        return unit
    if how in ("mm", "ia"):
        word = "mensual" if how == "mm" else "interanual"
        return f"Diferencia {word} (p.p.)" if m.kind == "rate" else f"Var. % {word}"
    if how == "s12":
        return f"{unit}, suma 12 meses"
    return f"Base 100 = {base_label}"


def _hover(how: str, kind: str, values: np.ndarray) -> str:
    if how in ("mm", "ia"):
        return "%{y:,.2f} p.p." if kind == "rate" else "%{y:,.2f}%"
    med = float(np.nanmedian(np.abs(values))) if len(values) else 0
    dec = 0 if med >= 1000 else (1 if med >= 100 else 2)
    return f"%{{y:,.{dec}f}}"


@dataclass
class ExplorerResult:
    fig: go.Figure | None
    notes: list[str]
    stats: list[dict]
    title: str


def build(data: MacroData, st: ExplorerState, years: int | None) -> ExplorerResult:
    notes: list[str] = []
    raw = {k: s for k in st.series[:MAX_SERIES] if (s := get_series(data, k)) is not None}
    for k in st.series:
        if k not in raw:
            notes.append(f"{meta(split_key(k)[0]).label}: sin datos.")
    if not raw:
        return ExplorerResult(None, notes, [], "Explorador")

    last = max(s.index.max() for s in raw.values())
    end = pd.Timestamp(st.end) if st.end else last
    if st.start:
        start = pd.Timestamp(st.start)
    elif years:
        start = end - pd.DateOffset(years=years)
    else:
        start = min(s.index.min() for s in raw.values())
    base_date = pd.Timestamp(st.base) if st.base else start

    fig = go.Figure()
    stats = []
    units = {"y": set(), "y2": set()}
    for i, (key, s) in enumerate(raw.items()):
        col, daily = split_key(key)
        m = meta(col)
        t, note = transform_series(s, m.kind, st.transform, daily, base_date)
        if note:
            notes.append(f"{m.label}: {note}.")
        if t is None:
            continue
        w = t[(t.index >= start) & (t.index <= end)]
        if w.empty:
            notes.append(f"{m.label}: sin datos en el rango elegido.")
            continue
        axis = "y2" if key in st.right else "y"
        actual_base = s[s.index >= base_date].index.min() if st.transform == "b100" else None
        base_label = "" if actual_base is None else (fmt_day(actual_base) if daily else fmt_month(actual_base))
        units[axis].add(_axis_unit(key, st.transform, data, base_label))
        name = m.label + (" · diaria" if daily else "") + (" · eje der." if axis == "y2" else "")
        fig.add_scatter(
            x=w.index, y=w.to_numpy(), name=name, mode="lines",
            line=dict(color=SERIES[i % len(SERIES)], width=1.6 if daily else 2.1),
            yaxis=axis, hovertemplate=_hover(st.transform, m.kind, w.to_numpy()),
        )
        fmt_date = fmt_day if daily else fmt_month
        imin, imax = w.idxmin(), w.idxmax()
        pp = st.transform in ("mm", "ia") and m.kind == "rate"
        pct_t = st.transform in ("mm", "ia") and not pp
        chg = None
        if len(w) > 1:
            if m.kind == "rate" or st.transform in ("mm", "ia"):
                chg = f"{fmt_num(w.iloc[-1] - w.iloc[0], 2, signed=True)} p.p."
            elif w.iloc[0] > 0:
                chg = f"{fmt_num((w.iloc[-1] / w.iloc[0] - 1) * 100, 1, signed=True)}%"
        dec = 2 if (pp or pct_t or abs(w.median()) < 100) else (1 if abs(w.median()) < 1000 else 0)
        sfx = " p.p." if pp else ("%" if pct_t else "")
        stats.append({
            "color": SERIES[i % len(SERIES)],
            "serie": m.label + (" · diaria" if daily else ""),
            "ultimo": f"{fmt_num(w.iloc[-1], dec)}{sfx}", "ultimo_fecha": fmt_date(w.index[-1]),
            "cambio": chg or "—", "desde": fmt_date(w.index[0]),
            "min": f"{fmt_num(w.min(), dec)}{sfx}", "min_fecha": fmt_date(imin),
            "max": f"{fmt_num(w.max(), dec)}{sfx}", "max_fecha": fmt_date(imax),
            "prom": f"{fmt_num(w.mean(), dec)}{sfx}",
        })

    if not fig.data:
        return ExplorerResult(None, notes, [], "Explorador")

    def axis_title(axis):
        u = units[axis]
        return " / ".join(sorted(u)) if len(u) <= 2 else ""

    y_type = "log" if st.log else "linear"
    fig.update_layout(yaxis=dict(title=dict(text=axis_title("y")), type=y_type))
    if units["y2"]:
        fig.update_layout(yaxis2=dict(title=dict(text=axis_title("y2")), overlaying="y", side="right",
                                      type=y_type, showgrid=False, zeroline=False))
    if st.log and any((tr.y <= 0).any() for tr in fig.data):
        notes.append("En escala logarítmica no se muestran los valores negativos o cero.")
    if st.transform in ("mm", "ia"):
        fig.add_hline(y=0, line=dict(color="#8b94a5", width=1, dash="dot"))
    fig.update_xaxes(range=[start, end], hoverformat="%d %b %Y" if any(
        split_key(k)[1] for k in raw) else "%b %Y")

    t_label = dict(TRANSFORMS)[st.transform]
    title = ", ".join(s["serie"] for s in stats[:2]) + (f" y {len(stats) - 2} más" if len(stats) > 2 else "")
    if st.transform != "nivel":
        title += f" · {t_label.lower()}"
    return ExplorerResult(fig, notes, stats, title)


# --------------------------------------------------------------------------- #
# Vista
# --------------------------------------------------------------------------- #
def _stats_table(stats: list[dict]) -> html.Div | None:
    if not stats:
        return None
    head = ["Serie", "Último dato", "Cambio en el rango", "Mínimo", "Máximo", "Promedio"]
    rows = [
        html.Tr([
            html.Td([html.Span(className="swatch", style={"background": color(s["color"])}), s["serie"]]),
            html.Td([s["ultimo"], html.Span(s["ultimo_fecha"], className="cell-sub")], className="num"),
            html.Td([s["cambio"], html.Span(f"desde {s['desde']}", className="cell-sub")], className="num"),
            html.Td([s["min"], html.Span(s["min_fecha"], className="cell-sub")], className="num"),
            html.Td([s["max"], html.Span(s["max_fecha"], className="cell-sub")], className="num"),
            html.Td(s["prom"], className="num"),
        ])
        for s in stats
    ]
    return html.Div(
        html.Table([html.Thead(html.Tr([html.Th(h) for h in head])), html.Tbody(rows)],
                   className="status-table explorer-stats"),
        className="table-scroll",
    )


def _result_children(data: MacroData, st: ExplorerState, years: int | None) -> list:
    res = build(data, st, years)
    subtitle = ("Elegí hasta 4 series en el buscador." if not st.series else
                "Zoom: arrastrar sobre el gráfico · doble clic para volver al rango elegido.")
    chart = chart_or_empty(res.fig, res.title, subtitle,
                           footer="Fuentes: INDEC, BCRA, Secretaría de Hacienda, Secretaría de Trabajo y "
                                  "proveedores de mercado (ver Datos y metodología).",
                           height=460, className="explorer-chart",
                           empty_text="Elegí al menos una serie con datos para armar el gráfico.")
    notes = html.Ul([html.Li(n) for n in res.notes], className="explorer-notes") if res.notes else None
    table = _stats_table(res.stats)
    stats = card(table, "Resumen del rango", "Valores de la serie transformada entre la primera y la última fecha "
                 "visibles.") if table else None
    return [chart, notes, stats]


def _control(label: str, child, label_id: str, modifier: str = "") -> html.Div:
    return html.Div([html.Span(label, className="control-label", id=label_id), child],
                    className="explorer-control" + (f" explorer-control--{modifier}" if modifier else ""),
                    role="group", **{"aria-labelledby": label_id})


def layout(data: MacroData, years: int | None = None, search: str | None = None) -> html.Div:
    options = series_options(data)
    valid = {o["value"] for o in options}
    st = parse_state(search, valid)
    labels = {o["value"]: o["label"] for o in options}
    first = min(data.df["Fecha"].min(), data.daily_df["Fecha"].min()) if not data.daily_df.empty \
        else data.df["Fecha"].min()

    controls = html.Div(
        [
            _control("Series (hasta 4)", dcc.Dropdown(
                id="ex-series", options=options, value=st.series, multi=True, searchable=True,
                placeholder="Buscar por nombre, grupo o frecuencia…", maxHeight=360, persistence=False,
                labels={"search": "Buscar", "clear_search": "Borrar búsqueda", "clear_selection": "Quitar todas",
                        "no_options_found": "No hay series con ese nombre", "select_all": "Elegir todas",
                        "deselect_all": "Quitar todas", "selected_count": "{num_selected} elegidas"},
            ), "ex-series-label", "wide"),
            _control("Transformación", dcc.RadioItems(
                id="ex-transform", options=[{"label": l, "value": k} for k, l in TRANSFORMS],
                value=st.transform, inline=True, className="segmented",
            ), "ex-transform-label", "transform"),
            _control("Eje derecho", dcc.Dropdown(
                id="ex-right", options=[{"label": labels.get(k, k), "value": k} for k in st.series],
                value=st.right, multi=True, placeholder="Ninguna", searchable=False,
            ), "ex-right-label"),
            _control("Rango de fechas", dcc.DatePickerRange(
                id="ex-dates", start_date=st.start, end_date=st.end, clearable=True,
                display_format="DD/MM/YYYY", first_day_of_week=1, min_date_allowed=first,
                start_date_placeholder_text="Según período", end_date_placeholder_text="Último dato",
            ), "ex-dates-label"),
            _control("Fecha base (base 100)", dcc.DatePickerSingle(
                id="ex-base", date=st.base, clearable=True, display_format="DD/MM/YYYY", first_day_of_week=1,
                min_date_allowed=first, placeholder="Inicio del rango",
            ), "ex-base-label"),
            _control("Escala", dcc.Checklist(
                id="ex-log", options=[{"label": "Logarítmica", "value": "log"}],
                value=["log"] if st.log else [], className="checklist",
            ), "ex-log-label"),
        ],
        className="explorer-controls",
    )

    return html.Div(
        [
            html.Section(
                [html.H2("Explorador de series", className="section-title"),
                 html.Span("Combiná series, transformalas y guardá el análisis: queda en la dirección de la página.",
                           className="section-hint")],
                className="section-head",
            ),
            card([controls, html.P(TRANSFORM_HELP, className="explorer-help")], className="explorer-card"),
            dcc.Loading(html.Div(_result_children(data, st, years), id="ex-result"), type="dot",
                        color="#6ea8fe", delay_show=300),
        ],
        className="view",
    )


# --------------------------------------------------------------------------- #
# Callbacks
# --------------------------------------------------------------------------- #
@callback(
    Output("ex-series", "value"),
    Output("ex-right", "options"),
    Output("ex-right", "value"),
    Input("ex-series", "value"),
    State("ex-right", "value"),
    State("ex-series", "options"),
    prevent_initial_call=True,
)
def limit_series(series, right, options):
    series = list(series or [])
    trimmed = series[:MAX_SERIES]
    labels = {o["value"]: o["label"] for o in options or []}
    right_opts = [{"label": labels.get(k, k), "value": k} for k in trimmed]
    right_val = [k for k in (right or []) if k in trimmed]
    return (trimmed if trimmed != series else no_update), right_opts, \
        (right_val if right_val != (right or []) else no_update)


@callback(
    Output("ex-result", "children"),
    Input("ex-series", "value"),
    Input("ex-transform", "value"),
    Input("ex-right", "value"),
    Input("ex-dates", "start_date"),
    Input("ex-dates", "end_date"),
    Input("ex-base", "date"),
    Input("ex-log", "value"),
    State("range", "value"),
    State("theme", "data"),
    prevent_initial_call=True,
)
def update_result(series, how, right, start, end, base, log, years, theme):
    set_theme(theme)
    st = ExplorerState(series=list(series or [])[:MAX_SERIES], transform=how if how in TRANSFORM_KEYS else "nivel",
                       log="log" in (log or []), right=list(right or []), base=_valid_date(base),
                       start=_valid_date(start), end=_valid_date(end))
    return _result_children(get_macro_data(force=False), st, years or None)


# El estado se escribe en la URL sin ir al servidor; `p` (período) y el resto de los parámetros se conservan.
clientside_callback(
    """
    function(series, how, right, start, end, base, log, search) {
        var params = new URLSearchParams(search || "");
        function put(k, v) { if (v && v.length) { params.set(k, v); } else { params.delete(k); } }
        params.set("s", (series || []).join(","));  // vacío también: "sin series" no es lo mismo que "por defecto"
        put("t", how && how !== "nivel" ? how : "");
        put("der", (right || []).join(","));
        put("desde", start ? String(start).slice(0, 10) : "");
        put("hasta", end ? String(end).slice(0, 10) : "");
        put("base", base ? String(base).slice(0, 10) : "");
        put("log", (log || []).indexOf("log") !== -1 ? "1" : "");
        var out = "?" + params.toString().replace(/%2C/g, ",");
        return out === (search || "") ? window.dash_clientside.no_update : out;
    }
    """,
    Output("url", "search", allow_duplicate=True),
    Input("ex-series", "value"),
    Input("ex-transform", "value"),
    Input("ex-right", "value"),
    Input("ex-dates", "start_date"),
    Input("ex-dates", "end_date"),
    Input("ex-base", "date"),
    Input("ex-log", "value"),
    State("url", "search"),
    prevent_initial_call=True,
)
