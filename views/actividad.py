"""Pestaña Actividad Económica: EMAE general y sectorial, Industria (IPI + UCI XLS), Construcción y Consumo."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import html

from indicators import build_actividad_kpis, change_pct, last_obs
from pipeline import MacroData
from ui.charts import chart_or_empty, trim, window
from ui.components import kpi_grid
from ui.format import fmt_month
from ui.theme import COLORS, SERIES


def fig_emae_series(df: pd.DataFrame) -> go.Figure | None:
    cols = ["EMAE_Original", "EMAE_Desestacionalizado", "EMAE_Tendencia_Ciclo"]
    d = trim(df, cols)
    if d.empty:
        return None
    fig = go.Figure()
    if "EMAE_Original" in d:
        fig.add_scatter(x=d["Fecha"], y=d["EMAE_Original"], name="Serie Original",
                        mode="lines", line=dict(color=COLORS["muted"], width=1.4, dash="dot"),
                        hovertemplate="%{y:.1f}")
    if "EMAE_Desestacionalizado" in d:
        fig.add_scatter(x=d["Fecha"], y=d["EMAE_Desestacionalizado"], name="Desestacionalizada",
                        mode="lines", line=dict(color=SERIES[0], width=2.3), hovertemplate="%{y:.1f}")
    if "EMAE_Tendencia_Ciclo" in d and d["EMAE_Tendencia_Ciclo"].notna().any():
        fig.add_scatter(x=d["Fecha"], y=d["EMAE_Tendencia_Ciclo"], name="Tendencia-Ciclo",
                        mode="lines", line=dict(color=SERIES[1], width=2.0), hovertemplate="%{y:.1f}")
    fig.update_yaxes(title_text="Índice (Base 2004 = 100)")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def fig_semaforo_sectorial(df: pd.DataFrame) -> go.Figure | None:
    sectores = [
        ("EMAE_Agro", "Agropecuario"),
        ("EMAE_Minas_Canteras", "Energía y Minería"),
        ("EMAE_Industria", "Industria Manufacturera"),
        ("EMAE_Construccion", "Construcción"),
        ("EMAE_Comercio", "Comercio"),
        ("EMAE_Financiero", "Intermediación Financiera"),
        ("EMAE_Original", "Nivel General (EMAE)"),
    ]
    rows = []
    for col, label in sectores:
        yoy = change_pct(df, col, 12)
        lo = last_obs(df, col)
        if yoy is not None and lo is not None:
            rows.append((label, yoy, fmt_month(lo[0])))
    if not rows:
        return None
    rows.sort(key=lambda r: r[1])
    labels = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    colors = [COLORS["good"] if v >= 0 else COLORS["bad"] for v in vals]

    fig = go.Figure(
        go.Bar(
            x=vals,
            y=labels,
            orientation="h",
            name="Variación % i.a.",
            marker_color=colors,
            marker_opacity=0.85,
            texttemplate="%{x:+.1f}%",  # respeta separators (coma decimal)
            textposition="outside",
            cliponaxis=False,
            customdata=[r[2] for r in rows],
            hovertemplate="%{y}: %{x:+.2f}% i.a. (%{customdata})<extra></extra>",
        )
    )
    # Margen a ambos lados para que las etiquetas "outside" no se corten
    span = max(abs(v) for v in vals) or 1.0
    lo_x = min(min(vals), 0) - span * 0.18
    hi_x = max(max(vals), 0) + span * 0.18
    fig.update_xaxes(ticksuffix="%", zeroline=True, zerolinecolor=COLORS["border"], range=[lo_x, hi_x],
                     showgrid=True, gridcolor=COLORS["grid"])
    fig.update_yaxes(title_text="", ticks="", showgrid=False)
    return fig


def fig_industria_construccion_consumo(df: pd.DataFrame) -> tuple[go.Figure | None, pd.Timestamp | None]:
    cols = {
        "IPI_Desestacionalizado": "Industria (IPI desest.)",
        "ISAC_Desestacionalizado": "Construcción (ISAC desest.)",
        "Supermercados_Constantes": "Ventas Supermercados (constantes)",
    }
    present = {c: lbl for c, lbl in cols.items() if c in df and df[c].notna().any()}
    if not present:
        return None, None
    base_date = max(df.loc[df[c].notna(), "Fecha"].min() for c in present)
    d = df[df["Fecha"] >= base_date]
    if d.empty:
        return None, None
    fig = go.Figure()
    for i, (c, lbl) in enumerate(present.items()):
        base = d.loc[d["Fecha"] == base_date, c].iloc[0]
        if base:
            fig.add_scatter(x=d["Fecha"], y=d[c] / base * 100, name=lbl, mode="lines",
                            line=dict(color=SERIES[i % len(SERIES)], width=2), hovertemplate="%{y:.1f}")
    fig.add_hline(y=100, line=dict(color=COLORS["border"], width=1, dash="dot"))
    fig.update_yaxes(title_text=f"Índice ({fmt_month(base_date)} = 100)")
    fig.update_xaxes(hoverformat="%b %Y")
    return fig, base_date


def fig_uci_industria(df: pd.DataFrame) -> go.Figure | None:
    d = trim(df, ["UCI_Industria"])
    if d.empty:
        return None
    avg = float(d["UCI_Industria"].dropna().mean())
    fig = go.Figure()
    fig.add_bar(
        x=d["Fecha"], y=d["UCI_Industria"], name="Capacidad Instalada (UCI %)",
        marker_color=SERIES[0], marker_opacity=0.75, hovertemplate="%{y:.1f}%",
    )
    fig.add_hline(
        y=avg, line=dict(color=SERIES[1], width=1.6, dash="dash"),
        annotation_text=f"Promedio del período: {avg:.1f}%", annotation_position="top left",
    )
    fig.update_yaxes(title_text="% de capacidad instalada", ticksuffix="%", range=[30, 85])
    fig.update_xaxes(hoverformat="%b %Y")
    return fig


def layout(data: MacroData, years: int | None) -> html.Div:
    df = data.df
    win = window(df, years)

    f_emae = fig_emae_series(win)
    f_sec = fig_semaforo_sectorial(df)
    f_icc, base_dt = fig_industria_construccion_consumo(win)
    f_uci = fig_uci_industria(win)

    return html.Div(
        [
            html.Section(
                [html.H2("Actividad económica y sectores productivos", className="section-title"),
                 html.Span("EMAE general y sectorial, Industria (IPI y UCI), Construcción (ISAC) y Consumo",
                           className="section-hint")],
                className="section-head",
            ),
            kpi_grid(build_actividad_kpis(df)),
            html.Div(
                [
                    chart_or_empty(
                        f_emae, "Evolución del EMAE (nivel general)",
                        "Comparación entre la serie original, desestacionalizada y tendencia-ciclo.",
                        "Fuente: INDEC (API Series de Tiempo datos.gob.ar)."),
                    chart_or_empty(
                        f_sec, "Semáforo sectorial de actividad (variación % interanual)",
                        "Desempeño interanual de los principales bloques productivos en el último mes publicado.",
                        "Fuente: INDEC (EMAE apertura por sectores, base 2004=100)."),
                ],
                className="grid-2",
            ),
            html.Div(
                [
                    chart_or_empty(
                        f_icc, "Industria, construcción y consumo masivo (base 100)",
                        f"Series desestacionalizadas reexpresadas a base {fmt_month(base_dt) if base_dt else 'común'} = 100.",
                        "Fuente: INDEC (IPI Manufacturero, ISAC Construcción y Encuesta de Supermercados)."),
                    chart_or_empty(
                        f_uci, "Utilización de la capacidad instalada en la industria (UCI)",
                        "Porcentaje de utilización del parque industrial nacional y promedio del período.",
                        "Fuente: INDEC (Planilla oficial sh_capacidad.xls + serie histórica SSPM)."),
                ],
                className="grid-2",
            ),
        ],
        className="view",
    )
