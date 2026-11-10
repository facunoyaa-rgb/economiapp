"""Pestaña Sector Externo y FX: Comercio Exterior (ICA + Balanza Energética), Reservas, ITCRM y Riesgo País."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import html

from indicators import build_externo_kpis, real_base_month
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


def fig_exportaciones_rubros_y_energia(df: pd.DataFrame) -> go.Figure | None:
    cols = [
        ("Expo_Productos_Primarios", "Productos Primarios (PP)", SERIES[1]),
        ("Expo_MOA", "Manuf. Origen Agropecuario (MOA)", SERIES[2]),
        ("Expo_MOI", "Manuf. Origen Industrial (MOI)", SERIES[0]),
        ("Expo_Combustibles_Energia", "Combustibles y Energía (CyE)", SERIES[4]),
    ]
    d = _trim(df, [c[0] for c in cols] + ["Balanza_Energetica"])
    if d.empty:
        return None
    fig = go.Figure()
    for col, label, color in cols:
        if col in d and d[col].notna().any():
            fig.add_bar(
                x=d["Fecha"], y=d[col], name=label,
                marker_color=color, marker_opacity=0.82, hovertemplate="US$ %{y:,.0f} M",
            )
    if "Balanza_Energetica" in d and d["Balanza_Energetica"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["Balanza_Energetica"], name="Saldo Comercial Energético",
            mode="lines", line=dict(color="#ffffff", width=2.3), hovertemplate="US$ %{y:,.0f} M",
        )
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title_text="Millones de USD")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_importaciones_usos(df: pd.DataFrame) -> go.Figure | None:
    cols = [
        ("Impo_Bienes_Intermedios", "Bienes Intermedios", SERIES[0]),
        ("Impo_Bienes_Capital", "Bienes de Capital", SERIES[2]),
        ("Impo_Bienes_Consumo", "Bienes de Consumo", SERIES[1]),
        ("Impo_Combustibles", "Combustibles y Lubricantes", SERIES[3]),
    ]
    d = _trim(df, [c[0] for c in cols])
    if d.empty:
        return None
    fig = go.Figure()
    for col, label, color in cols:
        if col in d and d[col].notna().any():
            fig.add_scatter(
                x=d["Fecha"], y=d[col], name=label, mode="lines",
                stackgroup="one", line=dict(color=color, width=1.5), hovertemplate="US$ %{y:,.0f} M",
            )
    fig.update_yaxes(title_text="Millones de USD")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_itcrm_competitividad(df: pd.DataFrame) -> go.Figure | None:
    cols = [
        ("ITCRM", "ITCRM Multilateral", SERIES[0], 2.4, "solid"),
        ("ITCRB_Brasil", "ITCRB Bilateral Brasil", SERIES[2], 1.8, "dot"),
        ("ITCRB_EEUU", "ITCRB Bilateral EE.UU.", SERIES[1], 1.8, "dash"),
    ]
    d = _trim(df, [c[0] for c in cols])
    if d.empty:
        return None
    fig = go.Figure()
    for col, label, color, w, dash in cols:
        if col in d and d[col].notna().any():
            fig.add_scatter(
                x=d["Fecha"], y=d[col], name=label, mode="lines",
                line=dict(color=color, width=w, dash=dash), hovertemplate="%{y:.1f}",
            )
    if "ITCRM" in d and d["ITCRM"].notna().any():
        avg = float(d["ITCRM"].dropna().mean())
        fig.add_hline(
            y=avg, line=dict(color=COLORS["muted"], width=1.2, dash="dot"),
            annotation_text=f"Promedio ITCRM: {avg:.1f}", annotation_position="bottom right",
        )
    fig.update_yaxes(title_text="Índice (17/12/2015 = 100)")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_tc_real_y_brecha(df: pd.DataFrame) -> go.Figure | None:
    d = _trim(df, ["TC_Mayorista_Real", "Dolar_Blue_Real", "Brecha_Cambiaria_Pct"])
    if d.empty:
        return None
    fig = go.Figure()
    if "TC_Mayorista_Real" in d and d["TC_Mayorista_Real"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["TC_Mayorista_Real"], name="Dólar Mayorista Real (precios de hoy)",
            mode="lines", line=dict(color=SERIES[0], width=2.1), hovertemplate="$ %{y:,.0f}",
        )
    if "Dolar_Blue_Real" in d and d["Dolar_Blue_Real"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["Dolar_Blue_Real"], name="Dólar Blue Real (precios de hoy)",
            mode="lines", line=dict(color=SERIES[1], width=2.0), hovertemplate="$ %{y:,.0f}",
        )
    if "Brecha_Cambiaria_Pct" in d and d["Brecha_Cambiaria_Pct"].notna().any():
        fig.add_bar(
            x=d["Fecha"], y=d["Brecha_Cambiaria_Pct"], name="Brecha Cambiaria (%, eje der.)",
            marker_color=SERIES[3], marker_opacity=0.35, yaxis="y2", hovertemplate="%{y:.1f}%",
        )
    fig.update_layout(
        yaxis=dict(title=dict(text=f"$ de {real_base_month(df)} por USD")),
        yaxis2=dict(
            title=dict(text="Brecha (%)", font=dict(color=COLORS["muted"], size=11)),
            overlaying="y", side="right", showgrid=False, ticksuffix="%",
            tickfont=dict(color=COLORS["muted"]),
        ),
    )
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

    f_exp = fig_exportaciones_rubros_y_energia(win)
    f_imp = fig_importaciones_usos(win)
    f_itc = fig_itcrm_competitividad(win)
    f_tcr = fig_tc_real_y_brecha(win)

    return html.Div(
        [
            html.Section(
                [html.H2("Sector externo, tipo de cambio y competitividad", className="section-title"),
                 html.Span("Intercambio comercial por rubros (ICA), Balanza Energética, Reservas, ITCRM y Brecha",
                           className="section-hint")],
                className="section-head",
            ),
            kpi_grid(build_externo_kpis(df)),
            html.Div(
                [
                    _chart_or_empty(
                        f_exp, "Exportaciones por grandes rubros y balanza energética",
                        "Barras apiladas: PP, MOA, MOI y Combustibles. Línea blanca: Saldo comercial energético.",
                        "Fuente: INDEC, Intercambio Comercial Argentino (ICA)."),
                    _chart_or_empty(
                        f_imp, "Importaciones por uso económico (CIF)",
                        "Evolución mensual de compras externas de bienes intermedios, de capital, consumo y energía.",
                        "Fuente: INDEC, Intercambio Comercial Argentino (ICA)."),
                ],
                className="grid-2",
            ),
            html.Div(
                [
                    _chart_or_empty(
                        f_itc, "Competitividad cambiaria: ITCRM multilateral y bilaterales",
                        "Índice de Tipo de Cambio Real Multilateral y bilaterales con Brasil y EE.UU. (17/12/2015 = 100).",
                        "Fuente: BCRA (Planilla oficial ITCRMSerie.xlsx)."),
                    _chart_or_empty(
                        f_tcr, "Dólar oficial y libre a precios constantes (IPC) y brecha cambiaria",
                        "Cotizaciones históricas expresadas en pesos de poder adquisitivo actual y brecha porcentual.",
                        "Fuente: BCRA, Bluelytics e INDEC (IPC)."),
                ],
                className="grid-2",
            ),
        ],
        className="view",
    )
