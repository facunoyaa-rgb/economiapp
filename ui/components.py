"""Componentes reutilizables de la interfaz (Dash)."""
from __future__ import annotations

import math
from urllib.parse import quote

from dash import dcc, html

from indicators import KPI
from ui.theme import COLORS, GRAPH_CONFIG

SENTIMENT_COLOR = {"good": COLORS["good"], "bad": COLORS["bad"], "neutral": COLORS["muted"]}
ARROW = {"good": "▲", "bad": "▼", "neutral": "•"}


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
            [html.Span(ARROW[d.sentiment], className="kpi-arrow") if d.sentiment != "neutral" else None,
             html.Span(d.text)],
            className=f"kpi-delta kpi-delta--{d.sentiment}",
        )
        for d in k.deltas
    ]
    card_id = f"kpi-{k.key}"
    return html.Div(
        [
            html.Div(
                [html.Span(k.title, className="kpi-title"),
                 html.Span("ⓘ", className="kpi-help", title=k.help) if k.help else None],
                className="kpi-head",
            ),
            html.Div(
                [html.Div(k.value, className="kpi-value"),
                 html.Img(src=spark_src, className="kpi-spark", alt="") if spark_src else None],
                className="kpi-body",
            ),
            html.Div(deltas, className="kpi-deltas"),
            html.Div(k.date and f"Último dato: {k.date}", className="kpi-date"),
        ],
        className="kpi-card" + ("" if k.available else " kpi-card--missing"),
        id=card_id,
    )


def kpi_grid(kpis: list[KPI]) -> html.Div:
    return html.Div([kpi_card(k) for k in kpis], className="kpi-grid")


# --------------------------------------------------------------------------- #
# Contenedores
# --------------------------------------------------------------------------- #
def card(children, title: str | None = None, subtitle: str | None = None, footer: str | None = None,
         className: str = "") -> html.Div:
    head = None
    if title or subtitle:
        head = html.Div(
            [html.H3(title, className="card-title") if title else None,
             html.P(subtitle, className="card-subtitle") if subtitle else None],
            className="card-head",
        )
    return html.Div(
        [head, html.Div(children, className="card-content"),
         html.Div(footer, className="card-footer") if footer else None],
        className=f"card {className}".strip(),
    )


def chart_card(fig, title: str, subtitle: str | None = None, footer: str | None = None,
               height: int = 320, className: str = "") -> html.Div:
    fig.update_layout(height=height)
    return card(dcc.Graph(figure=fig, config=GRAPH_CONFIG, style={"height": f"{height}px"}),
                title, subtitle, footer, className)


def insight_list(items) -> html.Ul:
    return html.Ul(
        [html.Li([html.Span(className=f"dot dot--{d.sentiment}"), html.Span(d.text)], className="insight")
         for d in items],
        className="insights",
    )


def empty_state(text: str) -> html.Div:
    return html.Div(text, className="empty-state")
