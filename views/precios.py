"""Pestaña Precios y Tasas: IPC por categorías, IPIM Mayorista, Expectativas REM/UTDT y Tasas de Interés."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import html

from indicators import build_precios_kpis
from pipeline import MacroData
from ui.components import card, chart_card, empty_state, kpi_grid
from ui.format import fmt_month
from ui.theme import COLORS, SERIES

HOVER_PCT = "%{y:.2f}%"


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


def fig_ipc_categorias(df: pd.DataFrame) -> go.Figure | None:
    cols = [
        ("Inflacion_Mensual_Pct", "Nivel General", SERIES[0], 2.4, "solid"),
        ("IPC_Nucleo_Mensual_Pct", "IPC Núcleo (Subyacente)", SERIES[1], 2.2, "solid"),
        ("IPC_Regulados_Mensual_Pct", "IPC Regulados (Tarifas)", SERIES[3], 1.7, "dot"),
        ("IPC_Estacionales_Mensual_Pct", "IPC Estacionales", SERIES[2], 1.5, "dash"),
    ]
    d = _trim(df, [c[0] for c in cols])
    if d.empty:
        return None
    fig = go.Figure()
    for col, label, color, w, dash in cols:
        if col in d and d[col].notna().any():
            fig.add_scatter(
                x=d["Fecha"], y=d[col], name=label, mode="lines",
                line=dict(color=color, width=w, dash=dash), hovertemplate=HOVER_PCT,
            )
    fig.update_yaxes(title_text="Variación % mensual", ticksuffix="%")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_minorista_mayorista_rem(df: pd.DataFrame) -> go.Figure | None:
    cols = [
        ("Inflacion_Interanual_Pct", "IPC Nivel General (i.a.)", SERIES[0]),
        ("IPC_Nucleo_Interanual_Pct", "IPC Núcleo (i.a.)", SERIES[1]),
        ("IPIM_Interanual_Pct", "Precios Mayoristas IPIM (i.a.)", SERIES[3]),
        ("REM_Inflacion_12m", "Inflación esperada próx. 12m (REM BCRA)", SERIES[2]),
    ]
    d = _trim(df, [c[0] for c in cols])
    if d.empty:
        return None
    fig = go.Figure()
    for col, label, color in cols:
        if col in d and d[col].notna().any():
            fig.add_scatter(x=d["Fecha"], y=d[col], name=label, mode="lines",
                            line=dict(color=color, width=2), hovertemplate="%{y:.1f}%")
    fig.update_yaxes(title_text="% interanual", ticksuffix="%")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_estructura_tasas(df: pd.DataFrame) -> go.Figure | None:
    cols = [
        ("Tasa_Interes_Nominal", "Plazo Fijo 30-59d (Minorista)", SERIES[0]),
        ("Tasa_BADLAR", "BADLAR Bancos Privados", SERIES[1]),
        ("Tasa_TAMAR", "TAMAR Mayorista", SERIES[2]),
        ("Tasa_Adelantos", "Activa Adelantos CC (Empresas)", SERIES[3]),
        ("Tasa_Personales", "Activa Préstamos Personales", SERIES[4]),
    ]
    d = _trim(df, [c[0] for c in cols])
    if d.empty:
        return None
    fig = go.Figure()
    for col, label, color in cols:
        if col in d and d[col].notna().any():
            fig.add_scatter(x=d["Fecha"], y=d[col], name=label, mode="lines",
                            line=dict(color=color, width=2), hovertemplate="%{y:.1f}% TNA")
    fig.update_yaxes(title_text="TNA (%)", ticksuffix="%")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_tasas_reales(df: pd.DataFrame) -> go.Figure | None:
    d = _trim(df, ["Tasa_Interes_Real_Mensual_Exacta", "Tasa_Real_ExAnte_Anual_Pct"])
    if d.empty:
        return None
    fig = go.Figure()
    if "Tasa_Interes_Real_Mensual_Exacta" in d:
        s = d["Tasa_Interes_Real_Mensual_Exacta"]
        colors = [COLORS["good"] if (v or 0) >= 0 else COLORS["bad"] for v in s.fillna(0)]
        fig.add_bar(
            x=d["Fecha"], y=s, name="Tasa Real Mensual Ex-Post (% m/m)",
            marker_color=colors, marker_opacity=0.8, hovertemplate=HOVER_PCT,
        )
    if "Tasa_Real_ExAnte_Anual_Pct" in d and d["Tasa_Real_ExAnte_Anual_Pct"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["Tasa_Real_ExAnte_Anual_Pct"],
            name="Tasa Real Ex-Ante vs. REM 12m (%, eje der.)", mode="lines",
            line=dict(color=SERIES[0], width=2.2), yaxis="y2", hovertemplate="%{y:.1f}%",
        )
    fig.update_layout(
        yaxis=dict(title=dict(text="Tasa Real Ex-Post (% mensual)"), ticksuffix="%"),
        yaxis2=dict(
            title=dict(text="Tasa Real Ex-Ante (% anual)", font=dict(color=COLORS["muted"], size=11)),
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

    f_cat = fig_ipc_categorias(win)
    f_mmr = fig_minorista_mayorista_rem(win)
    f_tas = fig_estructura_tasas(win)
    f_rea = fig_tasas_reales(win)

    return html.Div(
        [
            html.Section(
                [html.H2("Precios, Expectativas y Estructura de Tasas", className="section-title"),
                 html.Span("Aperturas del IPC Nacional, precios mayoristas (IPIM), REM del BCRA y tasas pasivas/activas",
                           className="section-hint")],
                className="section-head",
            ),
            kpi_grid(build_precios_kpis(df)),
            html.Div(
                [
                    _chart_or_empty(
                        f_cat, "Anatomía de la inflación mensual (IPC por categorías)",
                        "Comparación mensual entre Nivel General, IPC Núcleo, Regulados (tarifas) y Estacionales.",
                        "Fuente: INDEC (IPC Nacional base dic-2016 = 100)."),
                    _chart_or_empty(
                        f_mmr, "Inflación minorista, mayorista (IPIM) y expectativas (REM)",
                        "Variación interanual del IPC y del IPIM frente a la inflación esperada a 12 meses del REM.",
                        "Fuente: INDEC (IPC e IPIM) y BCRA (Relevamiento de Expectativas de Mercado, API v4.0)."),
                ],
                className="grid-2",
            ),
            html.Div(
                [
                    _chart_or_empty(
                        f_tas, "Estructura de tasas de interés pasivas y activas (TNA %)",
                        "Tasas de depósitos (Plazo Fijo, BADLAR, TAMAR) vs. costo del crédito (Adelantos y Personales).",
                        "Fuente: BCRA (datos.gob.ar y API Estadísticas v4.0)."),
                    _chart_or_empty(
                        f_rea, "Rendimiento real del peso: Ex-Post (IPC) y Ex-Ante (REM 12m)",
                        "Barras: tasa real mensual observada (Fisher). Línea: tasa anualizada contra inflación esperada REM.",
                        f"Fuente: Elaboración propia sobre datos de INDEC y BCRA (último IPC: {fmt_month(df['Fecha'].max())})."),
                ],
                className="grid-2",
            ),
        ],
        className="view",
    )
