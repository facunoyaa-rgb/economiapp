"""Utilidades compartidas por las vistas para recortar datos y armar tarjetas de gráficos."""
from __future__ import annotations

import pandas as pd
from dash import html

from ui.components import card, chart_card, empty_state

EMPTY_TEXT = "Sin datos disponibles para el período seleccionado."


def window(df: pd.DataFrame | None, years: int | None) -> pd.DataFrame:
    """Últimos `years` años respecto de la fecha máxima del panel (None o 0 = todo el historial)."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["Fecha"])
    if not years:
        return df
    start = df["Fecha"].max() - pd.DateOffset(years=years)
    return df[df["Fecha"] > start]


def trim(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Recorta filas iniciales y finales donde todas las columnas pedidas son nulas."""
    present = [c for c in cols if c in df]
    if not present or df.empty:
        return df.iloc[0:0]
    mask = df[present].notna().any(axis=1)
    if not mask.any():
        return df.iloc[0:0]
    return df.loc[mask.idxmax(): mask[::-1].idxmax()]


def chart_or_empty(fig, title: str, subtitle: str | None = None, footer: str | None = None,
                   height: int = 330, className: str = "", empty_text: str = EMPTY_TEXT) -> html.Div:
    """Tarjeta con el gráfico, o con un estado vacío si la figura no tiene datos."""
    if fig is None:
        return card(empty_state(empty_text), title, subtitle, className=className)
    return chart_card(fig, title, subtitle, footer, height, className)
