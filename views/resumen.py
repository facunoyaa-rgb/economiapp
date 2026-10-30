"""Pestaña Resumen: KPIs, lectura rápida y gráficos de coyuntura."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import html

from indicators import build_insights, build_kpis
from pipeline import MacroData
from ui.components import card, chart_card, empty_state, insight_list, kpi_grid
from ui.format import fmt_month
from ui.theme import COLORS, SERIES

HOVER_PCT = "%{y:.2f}%"


def _window(df: pd.DataFrame, years: int | None) -> pd.DataFrame:
    if not years:
        return df
    start = df["Fecha"].max() - pd.DateOffset(years=years)
    return df[df["Fecha"] > start]


def _trim(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Recorta filas iniciales/finales donde todas las columnas son nulas."""
    mask = df[cols].notna().any(axis=1)
    if not mask.any():
        return df.iloc[0:0]
    return df.loc[mask.idxmax(): mask[::-1].idxmax()]


# --------------------------------------------------------------------------- #
# Figuras
# --------------------------------------------------------------------------- #
def fig_inflacion_vs_tasa(df: pd.DataFrame) -> go.Figure | None:
    d = _trim(df, ["Inflacion_Mensual_Pct", "Tasa_Nominal_Mensual_Pct"])
    if d.empty:
        return None
    fig = go.Figure()
    fig.add_bar(x=d["Fecha"], y=d["Inflacion_Mensual_Pct"], name="Inflación mensual",
                marker_color=COLORS["bad"], marker_opacity=0.75, hovertemplate=HOVER_PCT)
    fig.add_scatter(x=d["Fecha"], y=d["Tasa_Nominal_Mensual_Pct"], name="Tasa plazo fijo mensual (TNA/12)",
                    mode="lines", line=dict(color=SERIES[0], width=2.2), hovertemplate=HOVER_PCT)
    fig.update_yaxes(ticksuffix="%", title_text="% mensual")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_base100(df: pd.DataFrame) -> tuple[go.Figure | None, pd.Timestamp | None]:
    cols = {
        "EMAE_Desestacionalizado": "Actividad (EMAE desest.)",
        "Salarios_Real": "Salario real (RIPTE)",
        "Credito_Interno_Real": "Crédito real al sector privado",
    }
    cols = {c: n for c, n in cols.items() if c in df and df[c].notna().any()}
    if not cols:
        return None, None
    # Base común: primer mes en que todas las series tienen dato dentro de la ventana
    base_date = max(df.loc[df[c].notna(), "Fecha"].min() for c in cols)
    d = df[df["Fecha"] >= base_date]
    fig = go.Figure()
    for i, (c, name) in enumerate(cols.items()):
        base = d.loc[d["Fecha"] == base_date, c].iloc[0]
        s = d[c] / base * 100
        fig.add_scatter(x=d["Fecha"], y=s, name=name, mode="lines",
                        line=dict(color=SERIES[[0, 2, 1][i]], width=2), hovertemplate="%{y:.1f}", connectgaps=False)
    fig.add_hline(y=100, line=dict(color=COLORS["border"], width=1, dash="dot"))
    fig.update_yaxes(title_text=f"Índice ({fmt_month(base_date)} = 100)", zeroline=False)
    fig.update_xaxes(hoverformat="%b %Y")
    return fig, base_date


def fig_saldo_comercial(df: pd.DataFrame) -> go.Figure | None:
    d = _trim(df, ["Saldo_Comercial"])
    if d.empty:
        return None
    colors = [COLORS["good"] if v >= 0 else COLORS["bad"] for v in d["Saldo_Comercial"].fillna(0)]
    fig = go.Figure()
    fig.add_bar(x=d["Fecha"], y=d["Saldo_Comercial"], name="Saldo", marker_color=colors, marker_opacity=0.8,
                hovertemplate="US$ %{y:,.0f} M")
    fig.add_scatter(x=d["Fecha"], y=d["Exportaciones_FOB"], name="Exportaciones", mode="lines",
                    line=dict(color=SERIES[0], width=1.6), hovertemplate="US$ %{y:,.0f} M")
    fig.add_scatter(x=d["Fecha"], y=d["Importaciones_CIF"], name="Importaciones", mode="lines",
                    line=dict(color=SERIES[1], width=1.6), hovertemplate="US$ %{y:,.0f} M")
    fig.update_yaxes(title_text="Millones de USD")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
def _chart_or_empty(fig, title, subtitle=None, footer=None, height=320, className=""):
    if fig is None:
        return card(empty_state("Sin datos disponibles para el período seleccionado."), title, subtitle,
                    className=className)
    return chart_card(fig, title, subtitle, footer, height, className)


def layout(data: MacroData, years: int | None) -> html.Div:
    df = data.df
    win = _window(df, years)

    f_infl = fig_inflacion_vs_tasa(win)
    f_b100, base_date = fig_base100(win)
    f_saldo = fig_saldo_comercial(win)

    b100_note = None
    if base_date is not None and win["Fecha"].min() < base_date:
        b100_note = (f"Las series reales comienzan en {fmt_month(base_date)} "
                     "(primer mes con IPC Nacional publicado).")

    return html.Div(
        [
            html.Section(
                [html.H2("Indicadores clave", className="section-title"),
                 html.Span("Último dato publicado de cada serie", className="section-hint")],
                className="section-head",
            ),
            kpi_grid(build_kpis(df)),
            html.Div(
                [
                    card(insight_list(build_insights(df)), "Lectura rápida",
                         "Generada automáticamente a partir de los últimos datos.", className="span-1"),
                    _chart_or_empty(
                        f_infl, "Inflación vs. tasa de plazo fijo",
                        "Ambas en % mensual. Si la línea supera a las barras, la tasa real es positiva.",
                        "Fuente: INDEC (IPC) y BCRA (plazo fijo 30-59 días).", className="span-2"),
                ],
                className="grid-3",
            ),
            html.Div(
                [
                    _chart_or_empty(
                        f_b100, "Actividad, salario real y crédito real",
                        "Evolución relativa sobre una base común (= 100).",
                        b100_note or "Fuente: INDEC, Secretaría de Trabajo (RIPTE) y BCRA. Deflactado por IPC."),
                    _chart_or_empty(
                        f_saldo, "Comercio exterior",
                        "Exportaciones, importaciones y saldo mensual.",
                        "Fuente: INDEC, Intercambio Comercial Argentino (ICA)."),
                ],
                className="grid-2",
            ),
        ],
        className="view",
    )
