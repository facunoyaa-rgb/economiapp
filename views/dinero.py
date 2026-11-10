"""Pestaña Dinero, Crédito y Salarios: Agregados Monetarios, Liquidez Bancaria, Carrera Salarial y Mercado Laboral."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import html

from indicators import build_dinero_kpis, real_base_month
from pipeline import MacroData
from ui.charts import chart_or_empty, trim, window
from ui.components import kpi_grid
from ui.theme import COLORS, SERIES


def fig_agregados_monetarios_reales(df: pd.DataFrame) -> go.Figure | None:
    cols = [
        ("Base_Monetaria_Real", "Base Monetaria Real", SERIES[0], 2.2),
        ("Circulacion_Monetaria_Real", "Circulación Monetaria Real", SERIES[1], 1.9),
        ("Depositos_Plazo_Fijo_Real", "Plazos Fijos Sector Privado Real", SERIES[2], 2.0),
    ]
    d = trim(df, [c[0] for c in cols])
    if d.empty:
        return None
    fig = go.Figure()
    for col, label, color, w in cols:
        if col in d and d[col].notna().any():
            fig.add_scatter(
                x=d["Fecha"], y=d[col], name=label, mode="lines",
                line=dict(color=color, width=w), hovertemplate="$ %{y:,.0f} M",
            )
    fig.update_yaxes(title_text=f"Millones de $ de {real_base_month(df)}")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_credito_vs_depositos_reales(df: pd.DataFrame) -> go.Figure | None:
    d = trim(df, ["Credito_Interno_Real", "Depositos_Privados_Pesos_Real", "Ratio_Prestamos_Depositos_Pct"])
    if d.empty:
        return None
    fig = go.Figure()
    if "Depositos_Privados_Pesos_Real" in d and d["Depositos_Privados_Pesos_Real"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["Depositos_Privados_Pesos_Real"], name="Depósitos Privados en ARS (Real)",
            mode="lines", line=dict(color=SERIES[0], width=2.1), hovertemplate="$ %{y:,.0f} M",
        )
    if "Credito_Interno_Real" in d and d["Credito_Interno_Real"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["Credito_Interno_Real"], name="Préstamos al Sector Privado en ARS (Real)",
            mode="lines", line=dict(color=SERIES[2], width=2.3), hovertemplate="$ %{y:,.0f} M",
        )
    if "Ratio_Prestamos_Depositos_Pct" in d and d["Ratio_Prestamos_Depositos_Pct"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["Ratio_Prestamos_Depositos_Pct"], name="Ratio Préstamos / Depósitos (%, eje der.)",
            mode="lines", line=dict(color=SERIES[1], width=1.8, dash="dot"), yaxis="y2",
            hovertemplate="%{y:.1f}%",
        )
    fig.update_layout(
        yaxis=dict(title=dict(text=f"Millones de $ de {real_base_month(df)}")),
        yaxis2=dict(
            title=dict(text="Préstamos / Depósitos (%)", font=dict(color=COLORS["muted"], size=11)),
            overlaying="y", side="right", showgrid=False, ticksuffix="%",
            tickfont=dict(color=COLORS["muted"]),
        ),
    )
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_carrera_salarial_real(df: pd.DataFrame) -> go.Figure | None:
    cols = [
        ("Salarios_Real", "RIPTE Real", SERIES[0], 2.4, "solid"),
        ("Indice_Salarios_Privado_Reg_Real", "Sector Privado Registrado (INDEC)", SERIES[2], 2.0, "solid"),
        ("Indice_Salarios_Publico_Real", "Sector Público (INDEC)", SERIES[1], 1.9, "dash"),
        ("Indice_Salarios_No_Reg_Real", "Sector Privado No Registrado (INDEC)", SERIES[3], 1.9, "dot"),
    ]
    d = trim(df, [c[0] for c in cols])
    if d.empty:
        return None
    fig = go.Figure()
    for col, label, color, w, dash in cols:
        if col in d and d[col].notna().any():
            s = d[col].dropna()
            b = s / s.iloc[0] * 100.0
            fig.add_scatter(
                x=d.loc[b.index, "Fecha"], y=b, name=label, mode="lines",
                line=dict(color=color, width=w, dash=dash), hovertemplate="%{y:.1f}",
            )
    fig.add_hline(y=100, line=dict(color=COLORS["border"], width=1, dash="dot"))
    fig.update_yaxes(title_text="Índice Real (inicio ventana = 100)")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_mercado_laboral_y_pobreza(df: pd.DataFrame) -> go.Figure | None:
    cols = [
        ("Tasa_Desocupacion", "Tasa de Desocupación (EPH, %)", SERIES[3], "lines+markers"),
        ("Pobreza_Personas", "Incidencia Pobreza Personas (%)", SERIES[1], "lines+markers"),
        ("Pobreza_Hogares", "Incidencia Pobreza Hogares (%)", SERIES[4], "lines+markers"),
    ]
    d = trim(df, [c[0] for c in cols] + ["Ratio_Salario_CBT"])
    if d.empty:
        return None
    fig = go.Figure()
    for col, label, color, mode in cols:
        if col in d and d[col].notna().any():
            sub = d.dropna(subset=[col])
            fig.add_scatter(
                x=sub["Fecha"], y=sub[col] * 100.0 if sub[col].max() <= 1.0 else sub[col],
                name=label, mode=mode, line=dict(color=color, width=2.0),
                hovertemplate="%{y:.1f}%",
            )
    if "Ratio_Salario_CBT" in d and d["Ratio_Salario_CBT"].notna().any():
        sub_cbt = d.dropna(subset=["Ratio_Salario_CBT"])
        fig.add_scatter(
            x=sub_cbt["Fecha"], y=sub_cbt["Ratio_Salario_CBT"],
            name="Cobertura RIPTE / Canasta Básica Total (eje der.)",
            mode="lines", line=dict(color=SERIES[2], width=2.1, dash="dot"), yaxis="y2",
            hovertemplate="%{y:.2f} CBT",
        )
    fig.update_layout(
        yaxis=dict(title=dict(text="Porcentaje (%)"), ticksuffix="%"),
        yaxis2=dict(
            title=dict(text="Canastas Básicas por RIPTE", font=dict(color=COLORS["muted"], size=11)),
            overlaying="y", side="right", showgrid=False,
            tickfont=dict(color=COLORS["muted"]),
        ),
    )
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def layout(data: MacroData, years: int | None) -> html.Div:
    df = data.df
    win = window(df, years)

    f_mon = fig_agregados_monetarios_reales(win)
    f_cre = fig_credito_vs_depositos_reales(win)
    f_sal = fig_carrera_salarial_real(win)
    f_lab = fig_mercado_laboral_y_pobreza(win)

    return html.Div(
        [
            html.Section(
                [html.H2("Dinero, crédito, salarios e indicadores sociales", className="section-title"),
                 html.Span("Agregados monetarios reales, intermediación financiera, poder adquisitivo y mercado laboral",
                           className="section-hint")],
                className="section-head",
            ),
            kpi_grid(build_dinero_kpis(df)),
            html.Div(
                [
                    chart_or_empty(
                        f_mon, "Agregados monetarios reales (base, circulación y plazos fijos)",
                        "Saldos nominales deflactados a pesos constantes del último IPC publicado.",
                        "Fuente: BCRA e INDEC (IPC)."),
                    chart_or_empty(
                        f_cre, "Intermediación financiera: crédito y depósitos reales en pesos",
                        "Stock de préstamos y depósitos privados en ARS constantes y ratio Préstamos/Depósitos.",
                        "Fuente: BCRA e INDEC."),
                ],
                className="grid-2",
            ),
            html.Div(
                [
                    chart_or_empty(
                        f_sal, "Salario real por sector (base 100 = inicio del período)",
                        "Poder adquisitivo comparado entre RIPTE, Privado Registrado, Público e Informal.",
                        "Fuente: Secretaría de Trabajo (RIPTE) e INDEC (Índice de Salarios e IPC)."),
                    chart_or_empty(
                        f_lab, "Desocupación, pobreza (EPH) y cobertura de la canasta básica",
                        "Tasas socioeconómicas (eje izq.) y cantidad de CBT individuales cubiertas por un RIPTE (eje der.).",
                        "Fuente: INDEC (EPH, Valorización de Canastas) y Secretaría de Trabajo."),
                ],
                className="grid-2",
            ),
        ],
        className="view",
    )
