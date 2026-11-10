"""Pestaña Resumen: KPIs, lectura rápida y gráficos de coyuntura."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import html

from indicators import build_insights, build_kpis, real_base_month
from pipeline import MacroData
from ui.charts import chart_or_empty, trim, window
from ui.components import card, insight_list, kpi_grid
from ui.format import fmt_month
from ui.theme import COLORS, SERIES

HOVER_PCT = "%{y:.2f}%"


# --------------------------------------------------------------------------- #
# Figuras
# --------------------------------------------------------------------------- #
def fig_inflacion_vs_tasa(df: pd.DataFrame) -> go.Figure | None:
    d = trim(df, ["Inflacion_Mensual_Pct", "Tasa_Nominal_Mensual_Pct"])
    if d.empty:
        return None
    fig = go.Figure()
    fig.add_bar(x=d["Fecha"], y=d["Inflacion_Mensual_Pct"], name="Inflación mensual",
                marker_color=COLORS["bad"], marker_opacity=0.75, hovertemplate=HOVER_PCT)
    fig.add_scatter(x=d["Fecha"], y=d["Tasa_Nominal_Mensual_Pct"], name="Tasa plazo fijo mensual (TNA/12)",
                    mode="lines", line=dict(color=SERIES[0], width=2.2), hovertemplate=HOVER_PCT)
    if "Crawling_Peg_Mensual_Pct" in d and d["Crawling_Peg_Mensual_Pct"].notna().any():
        fig.add_scatter(x=d["Fecha"], y=d["Crawling_Peg_Mensual_Pct"], name="Devaluación mensual (TC Mayorista)",
                        mode="lines", line=dict(color=SERIES[1], width=1.6, dash="dot"), hovertemplate=HOVER_PCT)
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
    d = trim(df, ["Saldo_Comercial"])
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


def fig_reservas_y_riesgo(df: pd.DataFrame) -> go.Figure | None:
    d = trim(df, ["Reservas_BCRA", "Riesgo_Pais"])
    if d.empty:
        return None
    fig = go.Figure()
    if "Reservas_BCRA" in d and d["Reservas_BCRA"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["Reservas_BCRA"], name="Reservas Brutas BCRA (USD M)",
            mode="lines", line=dict(color=SERIES[2], width=2.2), hovertemplate="US$ %{y:,.0f} M",
        )
    if "Riesgo_Pais" in d and d["Riesgo_Pais"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["Riesgo_Pais"], name="Riesgo País (pb, eje der.)",
            mode="lines", line=dict(color=SERIES[3], width=1.8, dash="dot"),
            yaxis="y2", hovertemplate="%{y:,.0f} pb",
        )
    fig.update_layout(
        yaxis=dict(title=dict(text="Reservas (USD M)")),
        yaxis2=dict(
            title=dict(text="Riesgo País (pb)", font=dict(color=COLORS["muted"], size=11)),
            overlaying="y", side="right", showgrid=False, tickfont=dict(color=COLORS["muted"]),
        ),
    )
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_resultado_fiscal(df: pd.DataFrame) -> go.Figure | None:
    d = trim(df, ["Resultado_Primario_Base_Caja_Real", "Resultado_Financiero_Base_Caja_Real"])
    if d.empty:
        return None
    fig = go.Figure()
    if "Resultado_Primario_Base_Caja_Real" in d:
        s_p = d["Resultado_Primario_Base_Caja_Real"] / 1e6
        colors = [COLORS["good"] if (v or 0) >= 0 else COLORS["bad"] for v in s_p.fillna(0)]
        fig.add_bar(
            x=d["Fecha"], y=s_p, name="Resultado Primario Real",
            marker_color=colors, marker_opacity=0.8, hovertemplate="$ %{y:,.2f} billones",
        )
    if "Resultado_Primario_Real_12m" in d and d["Resultado_Primario_Real_12m"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["Resultado_Primario_Real_12m"] / 1e6,
            name="Acumulado 12 meses (Primario)", mode="lines",
            line=dict(color=SERIES[0], width=2.2), hovertemplate="$ %{y:,.2f} billones",
        )
    fig.update_yaxes(title_text=f"Billones de $ de {real_base_month(df)}")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
def layout(data: MacroData, years: int | None) -> html.Div:
    df = data.df
    win = window(df, years)

    f_infl = fig_inflacion_vs_tasa(win)
    f_b100, base_date = fig_base100(win)
    f_saldo = fig_saldo_comercial(win)
    f_res = fig_reservas_y_riesgo(win)
    f_fis = fig_resultado_fiscal(win)

    b100_note = None
    if base_date is not None and win["Fecha"].min() < base_date:
        b100_note = (f"Las series reales comienzan en {fmt_month(base_date)} "
                     "(primer mes con IPC Nacional publicado).")

    return html.Div(
        [
            html.Section(
                [html.H2("Indicadores clave", className="section-title"),
                 html.Span("Último dato mensual publicado de cada serie", className="section-hint")],
                className="section-head",
            ),
            kpi_grid(build_kpis(df)),
            html.Div(
                [
                    card(insight_list(build_insights(df)), "Lectura rápida",
                         "Generada automáticamente a partir de los últimos datos.", className="span-1"),
                    chart_or_empty(
                        f_infl, "Inflación, tasa de interés y crawling peg",
                        "En % mensual. Si la tasa supera a la inflación, el rendimiento real ex-post es positivo.",
                        "Fuente: INDEC (IPC) y BCRA (plazo fijo 30-59 días y TC Mayorista A3500).", className="span-2"),
                ],
                className="grid-3",
            ),
            html.Div(
                [
                    chart_or_empty(
                        f_b100, "Actividad, salario real y crédito real",
                        "Evolución relativa sobre una base común (= 100).",
                        b100_note or "Fuente: INDEC, Secretaría de Trabajo (RIPTE) y BCRA. Deflactado por IPC."),
                    chart_or_empty(
                        f_saldo, "Comercio exterior",
                        "Exportaciones, importaciones y saldo mensual.",
                        "Fuente: INDEC, Intercambio Comercial Argentino (ICA)."),
                ],
                className="grid-2",
            ),
            html.Div(
                [
                    chart_or_empty(
                        f_res, "Reservas internacionales y riesgo país",
                        "Stock de reservas brutas del BCRA (eje izq.) y sobretasa soberana EMBI+ (eje der.).",
                        "Fuente: BCRA, Ámbito Financiero y Rava Bursátil."),
                    chart_or_empty(
                        f_fis, "Resultado fiscal primario (real)",
                        "Resultado mensual y acumulado de 12 meses a precios del último IPC.",
                        "Fuente: Secretaría de Hacienda (Esquema Ahorro-Inversión-Financiamiento Base Caja)."),
                ],
                className="grid-2",
            ),
        ],
        className="view",
    )
