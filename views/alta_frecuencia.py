"""Pestaña de Alta Frecuencia (Diario): Dólares, Brecha, Riesgo País, Reservas, Tasas, UVA e ITCRM."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import html

from indicators import build_high_freq_kpis
from pipeline import MacroData
from ui.components import card, chart_card, empty_state, kpi_grid
from ui.format import fmt_day, fmt_num, fmt_pct, fmt_quote_time
from ui.theme import COLORS, SERIES


def _window_daily(df: pd.DataFrame, years: int | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Fecha"])
    if not years:
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


def fx_board(fx_quotes: list[dict], may_ref: float | None = None) -> html.Div:
    """Pizarrón de cotizaciones cambiarias en vivo (DolarAPI)."""
    if not fx_quotes:
        return html.Div()

    labels = {
        "oficial": "Dólar Oficial",
        "mayorista": "Dólar Mayorista",
        "blue": "Dólar Blue",
        "bolsa": "Dólar MEP (Bolsa)",
        "contadoconliqui": "Contado con Liquidación (CCL)",
        "cripto": "Dólar Cripto",
        "tarjeta": "Dólar Tarjeta",
    }
    base_may = next(
        (float(q["venta"]) for q in fx_quotes if q.get("casa") == "mayorista" and q.get("venta")),
        may_ref,
    )
    items = []
    for q in fx_quotes:
        casa = q.get("casa", "")
        nombre = labels.get(casa, q.get("nombre", casa))
        compra = q.get("compra")
        venta = q.get("venta")
        brecha = ((float(venta) / base_may - 1) * 100) if (venta and base_may and casa != "mayorista") else None
        items.append(
            html.Div(
                [
                    html.Div(nombre, className="kpi-title"),
                    html.Div(f"$ {fmt_num(venta, 2)}", className="kpi-value fx-value"),
                    html.Div(
                        [
                            html.Span(f"Compra: $ {fmt_num(compra, 2)}", className="muted"),
                            html.Span(
                                f" · Brecha: {fmt_pct(brecha, 1, signed=True)}" if brecha is not None else " · Referencia",
                                className="kpi-delta--neutral",
                            ),
                        ],
                        className="fx-detail",
                    ),
                    html.Div(f"Cotización: {fmt_quote_time(q.get('fechaActualizacion'))}", className="kpi-date"),
                ],
                className="kpi-card fx-card",
            )
        )
    return html.Div(items, className="kpi-grid")


def fig_dolares_y_brecha(df: pd.DataFrame) -> go.Figure | None:
    d = _trim(df, ["TC_Mayorista", "TC_Minorista", "Dolar_Blue", "Brecha_Cambiaria_Pct"])
    if d.empty:
        return None
    fig = go.Figure()
    if "TC_Mayorista" in d:
        fig.add_scatter(x=d["Fecha"], y=d["TC_Mayorista"], name="Mayorista (A3500)",
                        mode="lines", line=dict(color=SERIES[0], width=2), hovertemplate="$ %{y:,.2f}")
    if "TC_Minorista" in d:
        fig.add_scatter(x=d["Fecha"], y=d["TC_Minorista"], name="Minorista (BCRA)",
                        mode="lines", line=dict(color=SERIES[5], width=1.5, dash="dot"), hovertemplate="$ %{y:,.2f}")
    if "Dolar_Blue" in d:
        fig.add_scatter(x=d["Fecha"], y=d["Dolar_Blue"], name="Dólar Blue",
                        mode="lines", line=dict(color=SERIES[1], width=2), hovertemplate="$ %{y:,.2f}")
    if "Brecha_Cambiaria_Pct" in d and d["Brecha_Cambiaria_Pct"].notna().any():
        fig.add_scatter(
            x=d["Fecha"], y=d["Brecha_Cambiaria_Pct"], name="Brecha Blue/Mayorista (%, eje der.)",
            mode="lines", line=dict(color=SERIES[3], width=1.4),
            fill="tozeroy", fillcolor="rgba(255, 123, 114, 0.08)",
            yaxis="y2", hovertemplate="%{y:.1f}%",
        )
    fig.update_layout(
        yaxis=dict(title=dict(text="ARS por USD")),
        yaxis2=dict(
            title=dict(text="Brecha (%)", font=dict(color=COLORS["muted"], size=11)),
            overlaying="y", side="right", showgrid=False, ticksuffix="%",
            tickfont=dict(color=COLORS["muted"]),
        ),
    )
    fig.update_xaxes(hoverformat="%d %b %Y")
    return fig


def fig_riesgo_y_reservas_diario(df: pd.DataFrame) -> go.Figure | None:
    d = _trim(df, ["Riesgo_Pais", "Reservas_BCRA"])
    if d.empty:
        return None
    fig = go.Figure()
    if "Reservas_BCRA" in d:
        fig.add_scatter(x=d["Fecha"], y=d["Reservas_BCRA"], name="Reservas Brutas (USD M)",
                        mode="lines", line=dict(color=SERIES[2], width=2), hovertemplate="US$ %{y:,.0f} M")
    if "Riesgo_Pais" in d:
        fig.add_scatter(
            x=d["Fecha"], y=d["Riesgo_Pais"], name="Riesgo País EMBI+ (pb, eje der.)",
            mode="lines", line=dict(color=SERIES[3], width=1.8),
            yaxis="y2", hovertemplate="%{y:,.0f} pb",
        )
    fig.update_layout(
        yaxis=dict(title=dict(text="Reservas (USD M)")),
        yaxis2=dict(
            title=dict(text="Riesgo País (pb)", font=dict(color=COLORS["muted"], size=11)),
            overlaying="y", side="right", showgrid=False, tickfont=dict(color=COLORS["muted"]),
        ),
    )
    fig.update_xaxes(hoverformat="%d %b %Y")
    return fig


def fig_tasas_diarias(df: pd.DataFrame) -> go.Figure | None:
    cols = {
        "Tasa_BADLAR": "BADLAR Bancos Privados",
        "Tasa_TAMAR": "TAMAR Mayorista",
        "Tasa_Adelantos": "Activa Adelantos CC",
        "Tasa_Personales": "Activa Préstamos Personales",
    }
    d = _trim(df, list(cols))
    if d.empty:
        return None
    fig = go.Figure()
    for i, (c, label) in enumerate(cols.items()):
        if c in d and d[c].notna().any():
            fig.add_scatter(x=d["Fecha"], y=d[c], name=label, mode="lines",
                            line=dict(color=SERIES[i % len(SERIES)], width=1.9), hovertemplate="%{y:.2f}% TNA")
    fig.update_yaxes(title_text="TNA (%)", ticksuffix="%")
    fig.update_xaxes(hoverformat="%d %b %Y")
    return fig


def fig_indexadores_e_itcrm_diario(df: pd.DataFrame) -> go.Figure | None:
    cols = {
        "UVA": "UVA (Créditos/Plazo Fijo)",
        "UVI": "UVI (Construcción)",
        "CER": "CER (Bonos indexados)",
        "TC_Mayorista": "Dólar Mayorista (A3500)",
    }
    present = {c: lbl for c, lbl in cols.items() if c in df and df[c].notna().any()}
    if not present:
        return None
    d = _trim(df, list(present)).copy()
    d_ff = d.ffill()
    base_date = max(d_ff.loc[d_ff[c].notna(), "Fecha"].min() for c in present)
    d_ff = d_ff[d_ff["Fecha"] >= base_date]
    if d_ff.empty:
        return None
    fig = go.Figure()
    for i, (c, lbl) in enumerate(present.items()):
        base_val = d_ff[c].dropna().iloc[0]
        if base_val:
            fig.add_scatter(
                x=d_ff["Fecha"], y=d_ff[c] / base_val * 100, name=lbl,
                mode="lines", line=dict(color=SERIES[i % len(SERIES)], width=2),
                hovertemplate="%{y:.1f}",
            )
    fig.add_hline(y=100, line=dict(color=COLORS["border"], width=1, dash="dot"))
    fig.update_yaxes(title_text=f"Índice ({fmt_day(base_date)} = 100)")
    fig.update_xaxes(hoverformat="%d %b %Y")
    return fig


def _chart_or_empty(fig, title, subtitle=None, footer=None, height=330, className=""):
    if fig is None:
        return card(empty_state("Sin datos diarios disponibles para el período seleccionado."), title, subtitle,
                    className=className)
    return chart_card(fig, title, subtitle, footer, height, className)


def layout(data: MacroData, years: int | None) -> html.Div:
    daily_df = data.daily_df
    win = _window_daily(daily_df, years)

    f_fx = fig_dolares_y_brecha(win)
    f_rr = fig_riesgo_y_reservas_diario(win)
    f_ts = fig_tasas_diarias(win)
    f_ix = fig_indexadores_e_itcrm_diario(win)

    board = fx_board(data.fx_quotes)

    return html.Div(
        [
            html.Section(
                [html.H2("Monitor de alta frecuencia (ruedas diarias)", className="section-title"),
                 html.Span("Series diarias del BCRA, Bluelytics, DolarAPI, Ámbito y Rava",
                           className="section-hint")],
                className="section-head",
            ),
            kpi_grid(build_high_freq_kpis(daily_df, data.fx_quotes)),
            html.Section(
                [html.H2("Pizarrón cambiario", className="section-title"),
                 html.Span("Última cotización de cada mercado y brecha contra el Dólar Mayorista (DolarAPI). Hora de Argentina.",
                           className="section-hint")],
                className="section-head",
            ) if data.fx_quotes else None,
            board,
            html.Div(
                [
                    _chart_or_empty(
                        f_fx, "Tipos de cambio diarios y brecha cambiaria",
                        "Evolución diaria del Dólar Mayorista (A3500), Minorista y Blue, junto con la brecha (%).",
                        "Fuente: BCRA y Bluelytics."),
                    _chart_or_empty(
                        f_rr, "Reservas internacionales brutas y riesgo país (diario)",
                        "Stock diario de reservas del BCRA (USD M) y sobretasa EMBI+ JP Morgan (puntos básicos).",
                        "Fuente: BCRA, Ámbito Financiero y Rava Bursátil."),
                ],
                className="grid-2",
            ),
            html.Div(
                [
                    _chart_or_empty(
                        f_ts, "Curva de tasas de interés diarias (TNA %)",
                        "Tasas pasivas mayoristas (BADLAR y TAMAR) y tasas activas (Adelantos CC y Personales).",
                        "Fuente: BCRA."),
                    _chart_or_empty(
                        f_ix, "Indexadores diarios y dólar mayorista (base 100)",
                        "Carrera diaria entre UVA (IPC), UVI (Construcción), CER y el tipo de cambio oficial.",
                        "Fuente: BCRA."),
                ],
                className="grid-2",
            ),
        ],
        className="view",
    )
