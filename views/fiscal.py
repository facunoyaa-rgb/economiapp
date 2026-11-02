"""Pestaña Fiscal: Resultado del SPNF Base Caja, Ingresos vs. Gasto Real y Recaudación Tributaria (ARCA/AFIP)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import html

from indicators import build_fiscal_kpis
from pipeline import MacroData
from ui.components import card, chart_card, empty_state, kpi_grid
from ui.theme import COLORS, SERIES


def _window(df: pd.DataFrame, years: int | None) -> pd.DataFrame:
    if not years or df.empty:
        return df
    start = df["Fecha"].max() - pd.DateOffset(years=years)
    return df[df["Fecha"] > start]


def _trim(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    present = [c for c in cols if c in df]
    if not present or df.empty:
        return df.iloc[0:0]
    mask = df[present].notna().any(axis=1)
    if not mask.any():
        return df.iloc[0:0]
    return df.loc[mask.idxmax(): mask[::-1].idxmax()]


def fig_ingresos_vs_gasto_real(df: pd.DataFrame) -> go.Figure | None:
    cols = [
        ("Ingresos_Publicos_Totales_Real", "Ingresos Totales SPNF (Real)", SERIES[2], "solid", 2.3),
        ("Gasto_Publico_Primario_Real", "Gasto Primario SPNF (Real)", SERIES[0], "solid", 2.1),
        ("Gasto_Publico_Total_Real", "Gasto Total c/ Intereses (Real)", SERIES[3], "dot", 1.8),
    ]
    d = _trim(df, [c[0] for c in cols])
    if d.empty:
        return None
    fig = go.Figure()
    for col, label, color, dash, w in cols:
        if col in d and d[col].notna().any():
            fig.add_scatter(
                x=d["Fecha"], y=d[col], name=label, mode="lines",
                line=dict(color=color, width=w, dash=dash), hovertemplate="$ %{y:,.0f} M",
            )
    fig.update_yaxes(title_text="Millones de ARS constantes")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_resultado_fiscal_mensual_real(df: pd.DataFrame) -> go.Figure | None:
    d = _trim(df, ["Resultado_Primario_Base_Caja_Real", "Resultado_Financiero_Base_Caja_Real"])
    if d.empty:
        return None
    fig = go.Figure()
    if "Resultado_Primario_Base_Caja_Real" in d and d["Resultado_Primario_Base_Caja_Real"].notna().any():
        colors = [COLORS["good"] if (v or 0) >= 0 else COLORS["bad"] for v in d["Resultado_Primario_Base_Caja_Real"]]
        fig.add_bar(
            x=d["Fecha"], y=d["Resultado_Primario_Base_Caja_Real"],
            name="Resultado Primario Real (mensual)", marker_color=colors, marker_opacity=0.78,
            hovertemplate="$ %{y:,.0f} M",
        )
    if "Resultado_Financiero_Base_Caja_Real" in d and d["Resultado_Financiero_Base_Caja_Real"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["Resultado_Financiero_Base_Caja_Real"],
            name="Resultado Financiero Real (mensual)", mode="lines",
            line=dict(color=SERIES[1], width=2.0), hovertemplate="$ %{y:,.0f} M",
        )
    fig.add_hline(y=0, line=dict(color=COLORS["border"], width=1))
    fig.update_yaxes(title_text="Millones de ARS constantes")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_resultado_fiscal_12m_real(df: pd.DataFrame) -> go.Figure | None:
    d = _trim(df, ["Resultado_Primario_Real_12m", "Resultado_Financiero_Real_12m"])
    if d.empty:
        return None
    fig = go.Figure()
    if "Resultado_Primario_Real_12m" in d and d["Resultado_Primario_Real_12m"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["Resultado_Primario_Real_12m"],
            name="Resultado Primario Real (acum. 12m)", mode="lines",
            line=dict(color=SERIES[2], width=2.4),
            fill="tozeroy", fillcolor="rgba(63, 185, 80, 0.12)",
            hovertemplate="$ %{y:,.0f} M",
        )
    if "Resultado_Financiero_Real_12m" in d and d["Resultado_Financiero_Real_12m"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["Resultado_Financiero_Real_12m"],
            name="Resultado Financiero Real (acum. 12m)", mode="lines",
            line=dict(color=SERIES[3], width=2.0, dash="dash"),
            hovertemplate="$ %{y:,.0f} M",
        )
    fig.add_hline(y=0, line=dict(color=COLORS["border"], width=1))
    fig.update_yaxes(title_text="Millones de ARS constantes (12m)")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_recaudacion_tributaria_real(df: pd.DataFrame) -> go.Figure | None:
    cols = [
        ("Recaudacion_DGI_Real", "DGI (Impuestos Internos)", SERIES[0]),
        ("Recaudacion_DGA_Real", "DGA (Comercio Exterior / Aduana)", SERIES[1]),
        ("Recaudacion_Seg_Social_Real", "Seguridad Social", SERIES[2]),
    ]
    d = _trim(df, [c[0] for c in cols] + ["Recaudacion_Total_Real"])
    if d.empty:
        return None
    fig = go.Figure()
    for col, label, color in cols:
        if col in d and d[col].notna().any():
            fig.add_bar(
                x=d["Fecha"], y=d[col], name=label,
                marker_color=color, marker_opacity=0.82, hovertemplate="$ %{y:,.0f} M",
            )
    if "Recaudacion_Total_Real" in d and d["Recaudacion_Total_Real"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["Recaudacion_Total_Real"], name="Recaudación Total Real",
            mode="lines", line=dict(color="#ffffff", width=2.1), hovertemplate="$ %{y:,.0f} M",
        )
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title_text="Millones de ARS constantes")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def _chart_or_empty(fig, title, subtitle=None, footer=None, height=330, className=""):
    if fig is None:
        return card(empty_state("Sin datos disponibles para el período seleccionado."), title, subtitle,
                    className=className)
    return chart_card(fig, title, subtitle, footer, height, className)


def layout(data: MacroData, years: int | None) -> html.Div:
    df = data.df
    win = _window(df, years)

    f_ig = fig_ingresos_vs_gasto_real(win)
    f_rm = fig_resultado_fiscal_mensual_real(win)
    f_r12 = fig_resultado_fiscal_12m_real(win)
    f_rec = fig_recaudacion_tributaria_real(win)

    return html.Div(
        [
            html.Section(
                [html.H2("Sector Público Nacional No Financiero (SPNF) y Recaudación", className="section-title"),
                 html.Span("Ejecución base caja e ingresos tributarios deflactados a precios constantes del último IPC",
                           className="section-hint")],
                className="section-head",
            ),
            kpi_grid(build_fiscal_kpis(df)),
            html.Div(
                [
                    _chart_or_empty(
                        f_ig, "Ingresos Totales vs. Gasto Primario y Total a precios constantes",
                        "Dinámica real de recursos y erogaciones del Sector Público Nacional No Financiero.",
                        "Fuente: Secretaría de Hacienda (IMIG) e INDEC (IPC)."),
                    _chart_or_empty(
                        f_rm, "Resultado Primario y Financiero Mensual Real (Base Caja)",
                        "Superávit (verde) o déficit (rojo) primario mensual y resultado financiero luego de intereses.",
                        "Fuente: Secretaría de Hacienda (IMIG) e INDEC (IPC)."),
                ],
                className="grid-2",
            ),
            html.Div(
                [
                    _chart_or_empty(
                        f_r12, "Resultado Fiscal Acumulado de 12 Meses a precios constantes",
                        "Suma móvil de 12 meses del resultado primario y financiero real para suavizar estacionalidad.",
                        "Fuente: Elaboración propia sobre Secretaría de Hacienda e INDEC."),
                    _chart_or_empty(
                        f_rec, "Recaudación Tributaria Nacional Real por origen (DGI, Aduana y Seg. Social)",
                        "Componentes de recursos tributarios deflactados por IPC y recaudación total.",
                        "Fuente: ARCA/AFIP, DNIAF - Ministerio de Economía e INDEC."),
                ],
                className="grid-2",
            ),
        ],
        className="view",
    )
