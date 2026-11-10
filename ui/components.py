"""Componentes reutilizables de la interfaz (Dash)."""
from __future__ import annotations

import math
from urllib.parse import quote

import numpy as np
from dash import dcc, html

from indicators import KPI
from ui.theme import COLORS, GRAPH_CONFIG

SENTIMENT_COLOR = {"good": COLORS["good"], "bad": COLORS["bad"], "neutral": COLORS["muted"]}


def trend_arrow(trend: float | None, tol: float = 1e-9) -> str:
    """Flecha según el signo de la variación (dirección), independiente de si es buena o mala."""
    if trend is None or (isinstance(trend, float) and math.isnan(trend)) or abs(trend) < tol:
        return ""
    return "▲" if trend > 0 else "▼"


# --------------------------------------------------------------------------- #
# Sparkline (SVG inline: liviano, sin overhead de Plotly)
# --------------------------------------------------------------------------- #
def sparkline_svg(values: list[float], kind: str = "line", width: int = 120, height: int = 36) -> str:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    if kind == "bar":
        lo, hi = min(lo, 0), max(hi, 0)
    span = (hi - lo) or 1.0
    pad = 2
    h = height - 2 * pad

    def y(v: float) -> float:
        return pad + h - (v - lo) / span * h

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
    if kind == "bar":
        n = len(vals)
        bw = width / n
        y0 = y(0)
        for i, v in enumerate(vals):
            yv = y(v)
            color = COLORS["good"] if v >= 0 else COLORS["bad"]
            opacity = 1 if i == n - 1 else 0.55  # resalta el último dato
            parts.append(
                f'<rect x="{i * bw + bw * 0.15:.1f}" y="{min(yv, y0):.1f}" width="{bw * 0.7:.1f}" '
                f'height="{max(abs(y0 - yv), 0.8):.1f}" fill="{color}" fill-opacity="{opacity}"/>'
            )
    else:
        step = width / (len(vals) - 1)
        pts = " ".join(f"{i * step:.1f},{y(v):.1f}" for i, v in enumerate(vals))
        area = f"0,{height} {pts} {width},{height}"
        parts.append(f'<polygon points="{area}" fill="{COLORS["accent"]}" fill-opacity="0.12"/>')
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{COLORS["accent"]}" stroke-width="1.6" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
        parts.append(f'<circle cx="{width - 0.5:.1f}" cy="{y(vals[-1]):.1f}" r="2.4" fill="{COLORS["accent"]}"/>')
    parts.append("</svg>")
    return "data:image/svg+xml;utf8," + quote("".join(parts))


# --------------------------------------------------------------------------- #
# Tarjeta KPI
# --------------------------------------------------------------------------- #
def kpi_card(k: KPI) -> html.Div:
    spark_src = sparkline_svg(k.spark, k.spark_kind) if k.available else ""
    deltas = [
        html.Div(
            [html.Span(trend_arrow(d.trend), className="kpi-arrow", **{"aria-hidden": "true"})
             if trend_arrow(d.trend) else None,
             html.Span(d.text)],
            className=f"kpi-delta kpi-delta--{d.sentiment}",
        )
        for d in k.deltas if d.text
    ]
    card_id = f"kpi-{k.key}"
    return html.Div(
        [
            html.Div(
                [html.Span(k.title, className="kpi-title"),
                 help_tip(k.help) if k.help else None],
                className="kpi-head",
            ),
            html.Div(
                [html.Div(k.value, className="kpi-value"),
                 html.Img(src=spark_src, className="kpi-spark", alt="") if spark_src else None],
                className="kpi-body",
            ),
            html.Div(deltas, className="kpi-deltas"),
            html.Div(" · ".join(p for p in [k.date and f"Último dato: {k.date}", k.note] if p), className="kpi-date"),
        ],
        className="kpi-card" + ("" if k.available else " kpi-card--missing"),
        id=card_id,
    )


def help_tip(text: str) -> html.Button:
    """Botón "ⓘ" con un globo de ayuda que aparece al pasar el mouse o al enfocarlo con el teclado."""
    return html.Button("ⓘ", type="button", className="kpi-help", **{"aria-label": f"Ayuda: {text}", "data-tip": text})


def kpi_grid(kpis: list[KPI]) -> html.Div:
    return html.Div([kpi_card(k) for k in kpis], className="kpi-grid")


# --------------------------------------------------------------------------- #
# Contenedores
# --------------------------------------------------------------------------- #
def card(children, title: str | None = None, subtitle: str | None = None, footer: str | None = None,
         className: str = "", actions=None) -> html.Div:
    head = None
    if title or subtitle or actions:
        text = html.Div(
            [html.H3(title, className="card-title") if title else None,
             html.P(subtitle, className="card-subtitle") if subtitle else None],
            className="card-head-text",
        )
        head = html.Div([text, html.Div(actions, className="card-actions") if actions else None],
                        className="card-head")
    return html.Div(
        [head, html.Div(children, className="card-content"),
         html.Div(footer, className="card-footer") if footer else None],
        className=f"card {className}".strip(),
    )


def chart_actions() -> list[html.Button]:
    """Exportación del gráfico. La resuelve assets/ui.js en el navegador con los datos ya cargados."""
    return [
        html.Button("CSV", type="button", className="chart-action", **{
            "data-action": "csv", "title": "Descargar los datos de este gráfico (CSV)",
            "aria-label": "Descargar los datos de este gráfico en CSV"}),
        html.Button("PNG", type="button", className="chart-action", **{
            "data-action": "png", "title": "Descargar el gráfico como imagen con fondo claro, para informes",
            "aria-label": "Descargar el gráfico como imagen PNG con fondo claro"}),
    ]


FLOAT32_MIN_POINTS = 400


def compact_figure(fig) -> None:
    """Achica el JSON de la figura que viaja al navegador.

    - Fechas como 'AAAA-MM-DD' en lugar de '2021-11-20T00:00:00.000000' (series diarias o mensuales).
    - En series largas (diarias), valores en float32: 7 dígitos significativos alcanzan para
      tipos de cambio, tasas, reservas e índices, y ocupan la mitad.
    En la pestaña diaria con 5 años, la respuesta baja de ~1 MB a ~0,5 MB.
    """
    for tr in fig.data:
        for axis in ("x", "y"):
            vals = getattr(tr, axis, None)
            if vals is None or len(vals) == 0:
                continue
            arr = np.asarray(vals)
            if np.issubdtype(arr.dtype, np.datetime64):
                setattr(tr, axis, np.datetime_as_string(arr.astype("datetime64[D]"), unit="D"))
            elif arr.dtype == np.float64 and len(arr) > FLOAT32_MIN_POINTS:
                setattr(tr, axis, arr.astype(np.float32))


def chart_card(fig, title: str, subtitle: str | None = None, footer: str | None = None,
               height: int = 320, className: str = "") -> html.Div:
    fig.update_layout(height=height)
    compact_figure(fig)
    graph = dcc.Graph(figure=fig, config=GRAPH_CONFIG, style={"height": f"{height}px"})
    return card(graph, title, subtitle, footer, f"chart-card {className}".strip(), actions=chart_actions())


def insight_list(items) -> html.Ul:
    return html.Ul(
        [html.Li([html.Span(className=f"dot dot--{d.sentiment}"), html.Span(d.text)], className="insight")
         for d in items],
        className="insights",
    )


def empty_state(text: str) -> html.Div:
    return html.Div(text, className="empty-state")
