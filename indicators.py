"""
Cálculo de indicadores clave (KPIs) y lectura automática del Resumen.

Este módulo no depende de Dash: recibe el DataFrame del pipeline y devuelve
estructuras de datos simples, lo que permite testearlo de forma aislada.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from ui.format import (
    fmt_ars,
    fmt_ars_millions,
    fmt_month,
    fmt_num,
    fmt_pct,
    fmt_pp,
    fmt_usd_millions,
)

Sentiment = Literal["good", "bad", "neutral"]
Direction = Literal["up", "down", "neutral"]

SPARK_MONTHS = 24


@dataclass
class Delta:
    text: str
    sentiment: Sentiment = "neutral"


@dataclass
class KPI:
    key: str
    title: str
    value: str
    date: str = ""
    deltas: list[Delta] = field(default_factory=list)
    spark: list[float] = field(default_factory=list)
    spark_kind: Literal["line", "bar"] = "line"
    help: str = ""
    available: bool = True


# --------------------------------------------------------------------------- #
# Utilidades de series
# --------------------------------------------------------------------------- #
def _series(df: pd.DataFrame, col: str) -> pd.Series:
    """Serie indexada por Fecha (mensual continua), sin nulos finales."""
    if col not in df:
        return pd.Series(dtype=float)
    return df.set_index("Fecha")[col]


def last_obs(df: pd.DataFrame, col: str) -> tuple[pd.Timestamp, float] | None:
    s = _series(df, col).dropna()
    if s.empty:
        return None
    return s.index[-1], float(s.iloc[-1])


def value_at(df: pd.DataFrame, col: str, date: pd.Timestamp) -> float | None:
    s = _series(df, col)
    if date not in s.index or pd.isna(s.loc[date]):
        return None
    return float(s.loc[date])


def change_pct(df: pd.DataFrame, col: str, months: int, at: pd.Timestamp | None = None) -> float | None:
    """Variación % del último dato (o de `at`) contra `months` meses antes."""
    lo = last_obs(df, col)
    if lo is None:
        return None
    date = at if at is not None else lo[0]
    cur = value_at(df, col, date)
    prev = value_at(df, col, date - pd.DateOffset(months=months))
    if cur is None or prev in (None, 0):
        return None
    return (cur / prev - 1) * 100


def change_pp(df: pd.DataFrame, col: str, months: int = 1) -> float | None:
    """Diferencia absoluta (pp) del último dato contra `months` meses antes."""
    lo = last_obs(df, col)
    if lo is None:
        return None
    prev = value_at(df, col, lo[0] - pd.DateOffset(months=months))
    return None if prev is None else lo[1] - prev


def sentiment(delta: float | None, direction: Direction, tol: float = 1e-9) -> Sentiment:
    """Bueno/malo según el sentido deseado de la variable (p. ej. inflación: 'down')."""
    if delta is None or direction == "neutral" or abs(delta) < tol:
        return "neutral"
    good = delta > 0 if direction == "up" else delta < 0
    return "good" if good else "bad"


def sign_sentiment(x: float | None) -> Sentiment:
    if x is None or x == 0:
        return "neutral"
    return "good" if x > 0 else "bad"


def spark(df: pd.DataFrame, col: str, months: int = SPARK_MONTHS) -> list[float]:
    s = _series(df, col).dropna()
    return [float(v) for v in s.iloc[-months:]]


def _pct_delta(label: str, value: float | None, direction: Direction) -> Delta:
    return Delta(f"{fmt_pct(value, 1, signed=True)} {label}", sentiment(value, direction))


def _missing_kpi(key: str, title: str, help_: str = "") -> KPI:
    return KPI(key, title, "Sin datos", deltas=[Delta("Fuente no disponible")], help=help_, available=False)


# --------------------------------------------------------------------------- #
# KPIs del Resumen
# --------------------------------------------------------------------------- #
def kpi_actividad(df: pd.DataFrame) -> KPI:
    title, help_ = "Actividad económica (EMAE)", "Índice desestacionalizado, base 2004=100. Var. interanual sobre serie original."
    lo = last_obs(df, "EMAE_Desestacionalizado")
    if lo is None:
        return _missing_kpi("emae", title, help_)
    yoy = change_pct(df, "EMAE_Original", 12, at=lo[0])
    mom = change_pct(df, "EMAE_Desestacionalizado", 1)
    value = f"{fmt_pct(yoy, 1, signed=True)} i.a." if yoy is not None else fmt_num(lo[1], 1)
    return KPI(
        "emae", title, value, fmt_month(lo[0]),
        [_pct_delta("vs. mes anterior (desest.)", mom, "up"), Delta(f"Índice: {fmt_num(lo[1], 1)}")],
        spark(df, "EMAE_Desestacionalizado"), help=help_,
    )


def kpi_inflacion(df: pd.DataFrame) -> KPI:
    title, help_ = "Inflación mensual (IPC)", "Variación mensual del IPC Nacional (INDEC)."
    lo = last_obs(df, "Inflacion_Mensual_Pct")
    if lo is None:
        return _missing_kpi("ipc", title, help_)
    d = change_pp(df, "Inflacion_Mensual_Pct")
    yoy = value_at(df, "Inflacion_Interanual_Pct", lo[0])
    deltas = [Delta(f"{fmt_pp(d)} vs. mes anterior", sentiment(d, "down"))]
    if yoy is not None:
        deltas.append(Delta(f"Interanual: {fmt_pct(yoy, 1)}"))
    return KPI("ipc", title, fmt_pct(lo[1], 2), fmt_month(lo[0]), deltas,
               spark(df, "Inflacion_Mensual_Pct"), "bar", help_)


def kpi_tasa_nominal(df: pd.DataFrame) -> KPI:
    title, help_ = "Tasa plazo fijo (TNA)", "Plazo fijo 30-59 días, promedio mensual (BCRA). TEM = TNA/12."
    lo = last_obs(df, "Tasa_Interes_Nominal")
    if lo is None:
        return _missing_kpi("tna", title, help_)
    d = change_pp(df, "Tasa_Interes_Nominal")
    tem = value_at(df, "Tasa_Nominal_Mensual_Pct", lo[0])
    return KPI("tna", title, fmt_pct(lo[1], 1), fmt_month(lo[0]),
               [Delta(f"{fmt_pp(d)} vs. mes anterior"), Delta(f"Mensual (TEM): {fmt_pct(tem, 2)}")],
               spark(df, "Tasa_Interes_Nominal"), help=help_)


def kpi_tasa_real(df: pd.DataFrame) -> KPI:
    title, help_ = "Tasa real plazo fijo", "Fisher exacta: (1+TEM)/(1+inflación mensual) − 1. Anualizada por capitalización."
    lo = last_obs(df, "Tasa_Interes_Real_Mensual_Exacta")
    if lo is None:
        return _missing_kpi("treal", title, help_)
    anual = value_at(df, "Tasa_Real_Anualizada_Pct", lo[0])
    d = change_pp(df, "Tasa_Interes_Real_Mensual_Exacta")
    return KPI("treal", title, f"{fmt_pct(lo[1], 2, signed=True)} mensual", fmt_month(lo[0]),
               [Delta(f"Anualizada: {fmt_pct(anual, 1, signed=True)}", sign_sentiment(anual)),
                Delta(f"{fmt_pp(d)} vs. mes anterior", sentiment(d, "up"))],
               spark(df, "Tasa_Interes_Real_Mensual_Exacta"), "bar", help_)


def kpi_salario_real(df: pd.DataFrame) -> KPI:
    title, help_ = "Salario real (RIPTE)", "RIPTE deflactado por IPC, en pesos del último mes con IPC publicado."
    lo = last_obs(df, "Salarios_Real")
    if lo is None:
        return _missing_kpi("salario", title, help_)
    return KPI("salario", title, fmt_ars(lo[1], 2), fmt_month(lo[0]),
               [_pct_delta("interanual real", change_pct(df, "Salarios_Real", 12), "up"),
                _pct_delta("vs. mes anterior", change_pct(df, "Salarios_Real", 1), "up")],
               spark(df, "Salarios_Real"), help=help_)


def kpi_credito_real(df: pd.DataFrame) -> KPI:
    title, help_ = "Crédito al sector privado (real)", "Préstamos en pesos al sector privado (BCRA), deflactados por IPC."
    lo = last_obs(df, "Credito_Interno_Real")
    if lo is None:
        return _missing_kpi("credito", title, help_)
    return KPI("credito", title, fmt_ars_millions(lo[1]), fmt_month(lo[0]),
               [_pct_delta("interanual real", change_pct(df, "Credito_Interno_Real", 12), "up"),
                _pct_delta("vs. mes anterior", change_pct(df, "Credito_Interno_Real", 1), "up")],
               spark(df, "Credito_Interno_Real"), help=help_)


def kpi_gasto_real(df: pd.DataFrame) -> KPI:
    title, help_ = "Gasto primario nacional (real)", "Gasto primario base caja (Hacienda), deflactado por IPC. Se compara interanual por estacionalidad."
    lo = last_obs(df, "Gasto_Publico_Primario_Real")
    if lo is None:
        return _missing_kpi("gasto", title, help_)
    yoy = change_pct(df, "Gasto_Publico_Primario_Real", 12)
    return KPI("gasto", title, fmt_ars_millions(lo[1]), fmt_month(lo[0]),
               [_pct_delta("interanual real", yoy, "neutral")],
               spark(df, "Gasto_Publico_Primario_Real"), "bar", help_)


def kpi_saldo_comercial(df: pd.DataFrame) -> KPI:
    title, help_ = "Saldo comercial", "Exportaciones FOB − Importaciones CIF (INDEC, ICA), millones de USD."
    lo = last_obs(df, "Saldo_Comercial")
    if lo is None:
        return _missing_kpi("saldo", title, help_)
    expo = change_pct(df, "Exportaciones_FOB", 12, at=lo[0])
    impo = change_pct(df, "Importaciones_CIF", 12, at=lo[0])
    return KPI("saldo", title, fmt_usd_millions(lo[1]), fmt_month(lo[0]),
               [Delta(f"{'Superávit' if lo[1] >= 0 else 'Déficit'}", sign_sentiment(lo[1])),
                Delta(f"Expo {fmt_pct(expo, 1, signed=True)} · Impo {fmt_pct(impo, 1, signed=True)} i.a.")],
               spark(df, "Saldo_Comercial"), "bar", help_)


KPI_BUILDERS = [
    kpi_actividad, kpi_inflacion, kpi_tasa_nominal, kpi_tasa_real,
    kpi_salario_real, kpi_credito_real, kpi_gasto_real, kpi_saldo_comercial,
]


def build_kpis(df: pd.DataFrame) -> list[KPI]:
    return [b(df) for b in KPI_BUILDERS]


# --------------------------------------------------------------------------- #
# Lectura rápida
# --------------------------------------------------------------------------- #
def build_insights(df: pd.DataFrame) -> list[Delta]:
    """Frases automáticas que resumen la coyuntura, cada una con su connotación."""
    out: list[Delta] = []

    lo = last_obs(df, "Inflacion_Mensual_Pct")
    if lo:
        d = change_pp(df, "Inflacion_Mensual_Pct")
        yoy = value_at(df, "Inflacion_Interanual_Pct", lo[0])
        trend = "bajó" if (d or 0) < 0 else "subió" if (d or 0) > 0 else "se mantuvo"
        txt = f"La inflación de {fmt_month(lo[0])} fue {fmt_pct(lo[1], 1)} y {trend} {fmt_pp(abs(d) if d else 0).lstrip('+')} frente al mes previo"
        if yoy is not None:
            txt += f"; la interanual se ubica en {fmt_pct(yoy, 1)}"
        out.append(Delta(txt + ".", sentiment(d, "down")))

    lo = last_obs(df, "Tasa_Interes_Real_Mensual_Exacta")
    if lo:
        signo = "positiva" if lo[1] > 0 else "negativa"
        out.append(Delta(
            f"La tasa de plazo fijo fue {signo} en términos reales en {fmt_month(lo[0])} "
            f"({fmt_pct(lo[1], 2, signed=True)} mensual).", sign_sentiment(lo[1])))

    lo = last_obs(df, "EMAE_Original")
    if lo:
        yoy = change_pct(df, "EMAE_Original", 12)
        if yoy is not None:
            verbo = "creció" if yoy > 0 else "cayó"
            out.append(Delta(f"La actividad {verbo} {fmt_pct(abs(yoy), 1)} interanual en {fmt_month(lo[0])}.",
                             sign_sentiment(yoy)))

    lo = last_obs(df, "Salarios_Real")
    if lo:
        yoy = change_pct(df, "Salarios_Real", 12)
        if yoy is not None:
            verbo = "ganó" if yoy > 0 else "perdió"
            out.append(Delta(f"El salario registrado (RIPTE) {verbo} {fmt_pct(abs(yoy), 1)} de poder adquisitivo "
                             f"en el último año ({fmt_month(lo[0])}).", sign_sentiment(yoy)))

    s = _series(df, "Saldo_Comercial").dropna()
    if len(s) >= 12:
        acum = s.iloc[-12:].sum()
        out.append(Delta(f"El saldo comercial de los últimos 12 meses acumula {fmt_usd_millions(acum)}.",
                         sign_sentiment(acum)))
    return out
