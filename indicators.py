"""
Cálculo de indicadores clave (KPIs) y lectura automática para todas las pestañas.

Este módulo no depende de Dash: recibe los DataFrames del pipeline (mensual y diario)
y devuelve estructuras de datos simples (`KPI`, `Delta`), testeables de forma aislada.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from ui.format import (
    fmt_ars,
    fmt_ars_millions,
    fmt_day,
    fmt_month,
    fmt_num,
    fmt_pct,
    fmt_pp,
    fmt_usd_millions,
)

Sentiment = Literal["good", "bad", "neutral"]
Direction = Literal["up", "down", "neutral"]

SPARK_MONTHS = 24
SPARK_DAYS = 45


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
    """Serie indexada por Fecha, sin nulos."""
    if df is None or df.empty or col not in df:
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
    val = s.loc[date]
    if isinstance(val, pd.Series):
        val = val.iloc[-1]
    return float(val)


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


def change_n_obs_pct(df: pd.DataFrame, col: str, n: int = 1) -> float | None:
    """Variación % contra `n` observaciones válidas atrás (útil en series diarias o trimestrales)."""
    s = _series(df, col).dropna()
    if len(s) <= n:
        return None
    cur, prev = float(s.iloc[-1]), float(s.iloc[-1 - n])
    return None if prev == 0 else (cur / prev - 1) * 100


def change_n_obs_pp(df: pd.DataFrame, col: str, n: int = 1) -> float | None:
    """Diferencia absoluta contra `n` observaciones válidas atrás."""
    s = _series(df, col).dropna()
    if len(s) <= n:
        return None
    return float(s.iloc[-1]) - float(s.iloc[-1 - n])


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
# 1. KPIs del Resumen (8 KPIs troncales)
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
# 2. KPIs de Alta Frecuencia (Diario + Cotizaciones en Vivo)
# --------------------------------------------------------------------------- #
def build_high_freq_kpis(daily_df: pd.DataFrame, fx_quotes: list[dict] | None = None) -> list[KPI]:
    out: list[KPI] = []
    quotes_by_casa = {q.get("casa"): q for q in (fx_quotes or []) if isinstance(q, dict)}

    # 1. Dólar Mayorista (BCRA A3500)
    lo = last_obs(daily_df, "TC_Mayorista")
    if lo:
        d1 = change_n_obs_pct(daily_df, "TC_Mayorista", 1)
        d20 = change_n_obs_pct(daily_df, "TC_Mayorista", 20)
        out.append(KPI(
            "hf-mayorista", "Dólar Mayorista (A3500)", f"$ {fmt_num(lo[1], 2)}", fmt_day(lo[0]),
            [_pct_delta("diario", d1, "neutral"), _pct_delta("últ. 20 ruedas", d20, "neutral")],
            spark(daily_df, "TC_Mayorista", SPARK_DAYS),
            help="Tipo de cambio mayorista de referencia Com. A 3500 (BCRA API v4.0).",
        ))
    else:
        out.append(_missing_kpi("hf-mayorista", "Dólar Mayorista (A3500)"))

    # 2. Dólar Blue y Brecha
    lo_b = last_obs(daily_df, "Dolar_Blue")
    lo_br = last_obs(daily_df, "Brecha_Cambiaria_Pct")
    if lo_b:
        d1 = change_n_obs_pct(daily_df, "Dolar_Blue", 1)
        brecha_txt = f"Brecha vs. Mayorista: {fmt_pct(lo_br[1], 1)}" if lo_br else ""
        out.append(KPI(
            "hf-blue", "Dólar Blue (Venta)", f"$ {fmt_num(lo_b[1], 0)}", fmt_day(lo_b[0]),
            [_pct_delta("diario", d1, "down"), Delta(brecha_txt, sentiment(lo_br[1] if lo_br else None, "down"))],
            spark(daily_df, "Dolar_Blue", SPARK_DAYS),
            help="Cotización libre e histórica diaria (Bluelytics API).",
        ))
    else:
        out.append(_missing_kpi("hf-blue", "Dólar Blue (Venta)"))

    # 3. Dólares Financieros en vivo (MEP y CCL desde DolarAPI)
    mep = quotes_by_casa.get("bolsa", {}).get("venta")
    ccl = quotes_by_casa.get("contadoconliqui", {}).get("venta")
    if mep or ccl:
        may_val = lo[1] if lo else None
        br_ccl = ((float(ccl) / may_val - 1) * 100) if (ccl and may_val) else None
        out.append(KPI(
            "hf-mep-ccl", "Dólar MEP / CCL (en vivo)",
            f"$ {fmt_num(mep, 1)} / $ {fmt_num(ccl, 1)}",
            "Cotización de mercado (DolarAPI)",
            [
                Delta(f"MEP (Bolsa): $ {fmt_num(mep, 2)}"),
                Delta(f"Brecha CCL: {fmt_pct(br_ccl, 1)}", sentiment(br_ccl, "down")) if br_ccl is not None else Delta("CCL en vivo"),
            ],
            spark(daily_df, "Dolar_Blue", SPARK_DAYS),
            help="Cotización actual de Dólar Bolsa (MEP) y Contado con Liquidación (DolarAPI).",
        ))
    else:
        out.append(_missing_kpi("hf-mep-ccl", "Dólar MEP / CCL"))

    # 4. Riesgo País (EMBI+ JP Morgan)
    lo_rp = last_obs(daily_df, "Riesgo_Pais")
    if lo_rp:
        d1 = change_n_obs_pp(daily_df, "Riesgo_Pais", 1)
        d20 = change_n_obs_pp(daily_df, "Riesgo_Pais", 20)
        out.append(KPI(
            "hf-riesgo", "Riesgo País (EMBI+)", f"{fmt_num(lo_rp[1], 0)} pb", fmt_day(lo_rp[0]),
            [
                Delta(f"{fmt_num(d1, 0, signed=True)} pb vs. rueda previa", sentiment(d1, "down")),
                Delta(f"{fmt_num(d20, 0, signed=True)} pb últ. 20 ruedas", sentiment(d20, "down")),
            ],
            spark(daily_df, "Riesgo_Pais", SPARK_DAYS),
            help="Sobretasa de bonos soberanos argentinos sobre el Tesoro de EE.UU. (Scraping Ámbito / Rava).",
        ))
    else:
        out.append(_missing_kpi("hf-riesgo", "Riesgo País (EMBI+)"))

    # 5. Reservas Internacionales Brutas (BCRA)
    lo_res = last_obs(daily_df, "Reservas_BCRA")
    if lo_res:
        d1 = change_n_obs_pp(daily_df, "Reservas_BCRA", 1)
        d20 = change_n_obs_pp(daily_df, "Reservas_BCRA", 20)
        out.append(KPI(
            "hf-reservas", "Reservas Brutas BCRA", fmt_usd_millions(lo_res[1]), fmt_day(lo_res[0]),
            [
                Delta(f"US$ {fmt_num(d1, 0, signed=True)} M diario", sentiment(d1, "up")),
                Delta(f"US$ {fmt_num(d20, 0, signed=True)} M últ. 20 ruedas", sentiment(d20, "up")),
            ],
            spark(daily_df, "Reservas_BCRA", SPARK_DAYS),
            help="Stock diario de Reservas Internacionales del BCRA (API BCRA v4.0).",
        ))
    else:
        out.append(_missing_kpi("hf-reservas", "Reservas Brutas BCRA"))

    # 6. Tasa Mayorista TAMAR / BADLAR
    lo_tam = last_obs(daily_df, "Tasa_TAMAR")
    lo_bad = last_obs(daily_df, "Tasa_BADLAR")
    if lo_tam or lo_bad:
        main = lo_tam or lo_bad
        col_main = "Tasa_TAMAR" if lo_tam else "Tasa_BADLAR"
        d20 = change_n_obs_pp(daily_df, col_main, 20)
        bad_txt = f"BADLAR: {fmt_pct(lo_bad[1], 2)} TNA" if lo_bad else ""
        out.append(KPI(
            "hf-tasas", "Tasa TAMAR / BADLAR", fmt_pct(main[1], 2), fmt_day(main[0]),
            [Delta(bad_txt), Delta(f"{fmt_pp(d20)} últ. 20 ruedas")],
            spark(daily_df, col_main, SPARK_DAYS),
            help="Tasas pasivas mayoristas de bancos privados en TNA (API BCRA v4.0).",
        ))
    else:
        out.append(_missing_kpi("hf-tasas", "Tasa TAMAR / BADLAR"))

    # 7. Unidad de Valor Adquisitivo (UVA) y CER
    lo_uva = last_obs(daily_df, "UVA")
    lo_cer = last_obs(daily_df, "CER")
    if lo_uva:
        d30 = change_n_obs_pct(daily_df, "UVA", 30)
        cer_txt = f"CER: {fmt_num(lo_cer[1], 2)}" if lo_cer else ""
        out.append(KPI(
            "hf-uva", "Valor UVA / CER", f"$ {fmt_num(lo_uva[1], 2)}", fmt_day(lo_uva[0]),
            [_pct_delta("últ. 30 días", d30, "neutral"), Delta(cer_txt)],
            spark(daily_df, "UVA", SPARK_DAYS),
            help="Unidad de Valor Adquisitivo y Coeficiente de Estabilización de Referencia (API BCRA v4.0).",
        ))
    else:
        out.append(_missing_kpi("hf-uva", "Valor UVA / CER"))

    # 8. ITCRM Diario (Planilla XLSX BCRA)
    lo_itc = last_obs(daily_df, "ITCRM")
    if lo_itc:
        d20 = change_n_obs_pct(daily_df, "ITCRM", 20)
        lo_br_itc = last_obs(daily_df, "ITCRB_Brasil")
        br_txt = f"ITCRB Brasil: {fmt_num(lo_br_itc[1], 1)}" if lo_br_itc else ""
        out.append(KPI(
            "hf-itcrm", "ITCRM (Competitividad)", fmt_num(lo_itc[1], 1), fmt_day(lo_itc[0]),
            [_pct_delta("últ. 20 ruedas", d20, "neutral"), Delta(br_txt)],
            spark(daily_df, "ITCRM", SPARK_DAYS),
            help="Índice de Tipo de Cambio Real Multilateral diario, base 17/12/2015=100 (Planilla XLSX BCRA).",
        ))
    else:
        out.append(_missing_kpi("hf-itcrm", "ITCRM (Competitividad)"))

    return out


# --------------------------------------------------------------------------- #
# 3. KPIs por Pestaña Mensual
# --------------------------------------------------------------------------- #
def _generic_index_kpi(
    df: pd.DataFrame,
    key: str,
    title: str,
    col_orig: str,
    col_desest: str | None = None,
    help_: str = "",
) -> KPI:
    lo = last_obs(df, col_orig)
    if lo is None:
        return _missing_kpi(key, title, help_)
    yoy = change_pct(df, col_orig, 12)
    mom = change_pct(df, col_desest or col_orig, 1)
    lbl_m = "vs. mes ant. (desest.)" if col_desest else "vs. mes anterior"
    val = f"{fmt_pct(yoy, 1, signed=True)} i.a." if yoy is not None else fmt_num(lo[1], 1)
    return KPI(
        key, title, val, fmt_month(lo[0]),
        [_pct_delta(lbl_m, mom, "up"), Delta(f"Índice: {fmt_num(lo[1], 1)}")],
        spark(df, col_desest or col_orig), help=help_,
    )


def build_actividad_kpis(df: pd.DataFrame) -> list[KPI]:
    k_uci = _missing_kpi("act-uci", "Capacidad instalada (UCI)")
    lo_u = last_obs(df, "UCI_Industria")
    if lo_u:
        d_yoy = change_pp(df, "UCI_Industria", 12)
        d_mom = change_pp(df, "UCI_Industria", 1)
        k_uci = KPI(
            "act-uci", "Capacidad instalada (UCI)", fmt_pct(lo_u[1], 1), fmt_month(lo_u[0]),
            [Delta(f"{fmt_pp(d_yoy, 1)} i.a.", sentiment(d_yoy, "up")),
             Delta(f"{fmt_pp(d_mom, 1)} vs. mes ant.", sentiment(d_mom, "up"))],
            spark(df, "UCI_Industria"),
            help="Utilización de la capacidad instalada en la industria (Planilla XLS INDEC + datos.gob.ar).",
        )

    return [
        kpi_actividad(df),
        _generic_index_kpi(df, "act-ipi", "Industria (IPI Manufacturero)", "IPI_Manufacturero", "IPI_Desestacionalizado",
                           "Índice de Producción Industrial Manufacturero (INDEC)."),
        _generic_index_kpi(df, "act-isac", "Construcción (ISAC)", "ISAC_General", "ISAC_Desestacionalizado",
                           "Indicador Sintético de la Actividad de la Construcción (INDEC)."),
        k_uci,
        _generic_index_kpi(df, "act-super", "Ventas en Supermercados", "Supermercados_Constantes", None,
                           "Ventas a precios constantes desestacionalizadas (INDEC)."),
        _generic_index_kpi(df, "act-agro", "EMAE Agropecuario", "EMAE_Agro", None,
                           "Agricultura, ganadería, caza y silvicultura (INDEC)."),
        _generic_index_kpi(df, "act-minas", "EMAE Energía y Minería", "EMAE_Minas_Canteras", None,
                           "Explotación de minas y canteras (INDEC)."),
        _generic_index_kpi(df, "act-comercio", "EMAE Comercio", "EMAE_Comercio", None,
                           "Comercio mayorista, minorista y reparaciones (INDEC)."),
    ]


def build_precios_kpis(df: pd.DataFrame) -> list[KPI]:
    def _cat_ipc(key: str, title: str, col_m: str, col_ia: str, help_: str) -> KPI:
        lo = last_obs(df, col_m)
        if lo is None:
            return _missing_kpi(key, title, help_)
        d = change_pp(df, col_m, 1)
        ia = value_at(df, col_ia, lo[0])
        return KPI(
            key, title, fmt_pct(lo[1], 2), fmt_month(lo[0]),
            [Delta(f"{fmt_pp(d)} vs. mes ant.", sentiment(d, "down")),
             Delta(f"Interanual: {fmt_pct(ia, 1)}")],
            spark(df, col_m), "bar", help=help_,
        )

    # REM 12m
    lo_rem = last_obs(df, "REM_Inflacion_12m")
    k_rem = _missing_kpi("pre-rem", "Inflación esperada 12m (REM)")
    if lo_rem:
        d_rem = change_pp(df, "REM_Inflacion_12m", 1)
        ex_ante = value_at(df, "Tasa_Real_ExAnte_Anual_Pct", lo_rem[0])
        k_rem = KPI(
            "pre-rem", "Inflación esperada 12m (REM)", fmt_pct(lo_rem[1], 1), fmt_month(lo_rem[0]),
            [Delta(f"{fmt_pp(d_rem, 1)} vs. relev. previo", sentiment(d_rem, "down")),
             Delta(f"Tasa real ex-ante: {fmt_pct(ex_ante, 1, signed=True)}", sign_sentiment(ex_ante))],
            spark(df, "REM_Inflacion_12m"),
            help="Mediana de inflación esperada para los próximos 12 meses según el REM (BCRA API v4.0).",
        )

    # Tasas activas
    lo_ad = last_obs(df, "Tasa_Adelantos")
    lo_pe = last_obs(df, "Tasa_Personales")
    k_act = _missing_kpi("pre-activas", "Tasas activas (Empresas / Familias)")
    if lo_ad:
        d_ad = change_pp(df, "Tasa_Adelantos", 1)
        pe_txt = f"Personales: {fmt_pct(lo_pe[1], 1)} TNA" if lo_pe else ""
        k_act = KPI(
            "pre-activas", "Tasa Adelantos CC (Empresas)", fmt_pct(lo_ad[1], 1), fmt_month(lo_ad[0]),
            [Delta(f"{fmt_pp(d_ad, 1)} vs. mes ant.", sentiment(d_ad, "down")), Delta(pe_txt)],
            spark(df, "Tasa_Adelantos"),
            help="Tasa activa nominal anual por adelantos en cuenta corriente y préstamos personales (BCRA v4.0).",
        )

    return [
        kpi_inflacion(df),
        _cat_ipc("pre-nucleo", "IPC Núcleo (mensual)", "IPC_Nucleo_Mensual_Pct", "IPC_Nucleo_Interanual_Pct",
                 "Inflación subyacente sin precios regulados ni estacionales (INDEC)."),
        _cat_ipc("pre-regulados", "IPC Regulados (mensual)", "IPC_Regulados_Mensual_Pct", "IPC_Regulados_Interanual_Pct",
                 "Tarifas, transporte público, combustibles y precios regulados (INDEC)."),
        _cat_ipc("pre-ipim", "Precios Mayoristas (IPIM)", "IPIM_Mensual_Pct", "IPIM_Interanual_Pct",
                 "Índice de Precios Internos al por Mayor Nivel General (INDEC)."),
        k_rem,
        kpi_tasa_nominal(df),
        kpi_tasa_real(df),
        k_act,
    ]


def build_externo_kpis(df: pd.DataFrame) -> list[KPI]:
    # Reservas BCRA
    lo_res = last_obs(df, "Reservas_BCRA")
    k_res = _missing_kpi("ext-res", "Reservas Internacionales (BCRA)")
    if lo_res:
        d_m = change_pp(df, "Reservas_BCRA", 1)
        d_y = change_pp(df, "Reservas_BCRA", 12)
        k_res = KPI(
            "ext-res", "Reservas Internacionales (BCRA)", fmt_usd_millions(lo_res[1]), fmt_month(lo_res[0]),
            [Delta(f"US$ {fmt_num(d_m, 0, signed=True)} M vs. mes ant.", sentiment(d_m, "up")),
             Delta(f"US$ {fmt_num(d_y, 0, signed=True)} M interanual", sentiment(d_y, "up"))],
            spark(df, "Reservas_BCRA"),
            help="Stock de Reservas Internacionales Brutas al cierre de cada mes (BCRA v4.0).",
        )

    # Balanza energética
    lo_en = last_obs(df, "Balanza_Energetica")
    k_en = _missing_kpi("ext-energia", "Balanza comercial energética")
    if lo_en:
        s_en = _series(df, "Balanza_Energetica").dropna()
        acum12 = s_en.iloc[-12:].sum() if len(s_en) >= 12 else None
        k_en = KPI(
            "ext-energia", "Balanza comercial energética", fmt_usd_millions(lo_en[1]), fmt_month(lo_en[0]),
            [Delta("Superávit energético" if lo_en[1] >= 0 else "Déficit energético", sign_sentiment(lo_en[1])),
             Delta(f"Acum. 12m: {fmt_usd_millions(acum12)}" if acum12 is not None else "")],
            spark(df, "Balanza_Energetica"), "bar",
            help="Exportaciones de Combustibles y Energía − Importaciones de Combustibles y Lubricantes (ICA INDEC).",
        )

    # ITCRM
    lo_itc = last_obs(df, "ITCRM")
    k_itc = _missing_kpi("ext-itcrm", "Tipo de Cambio Real (ITCRM)")
    if lo_itc:
        yoy = change_pct(df, "ITCRM", 12)
        mom = change_pct(df, "ITCRM", 1)
        k_itc = KPI(
            "ext-itcrm", "Tipo de Cambio Real (ITCRM)", fmt_num(lo_itc[1], 1), fmt_month(lo_itc[0]),
            [_pct_delta("vs. mes anterior", mom, "neutral"), _pct_delta("interanual", yoy, "neutral")],
            spark(df, "ITCRM"),
            help="Índice de Tipo de Cambio Real Multilateral promedio mensual, base 17/12/2015=100 (XLSX BCRA).",
        )

    # TC Mayorista y Crawling Peg
    lo_tc = last_obs(df, "TC_Mayorista")
    k_tc = _missing_kpi("ext-tcmay", "Dólar Mayorista (promedio)")
    if lo_tc:
        crawl = value_at(df, "Crawling_Peg_Mensual_Pct", lo_tc[0])
        yoy = change_pct(df, "TC_Mayorista", 12)
        k_tc = KPI(
            "ext-tcmay", "Dólar Mayorista (promedio)", f"$ {fmt_num(lo_tc[1], 1)}", fmt_month(lo_tc[0]),
            [Delta(f"Variación mensual: {fmt_pct(crawl, 2, signed=True)}"),
             Delta(f"Interanual: {fmt_pct(yoy, 1, signed=True)}")],
            spark(df, "TC_Mayorista"),
            help="Tipo de cambio mayorista Com. A 3500 promedio mensual (BCRA v4.0).",
        )

    # Dólar Blue y Brecha
    lo_bl = last_obs(df, "Dolar_Blue")
    lo_br = last_obs(df, "Brecha_Cambiaria_Pct")
    k_bl = _missing_kpi("ext-blue", "Dólar Blue y Brecha")
    if lo_bl:
        mom = change_pct(df, "Dolar_Blue", 1)
        br_val = lo_br[1] if lo_br else None
        k_bl = KPI(
            "ext-blue", "Dólar Blue (promedio)", f"$ {fmt_num(lo_bl[1], 0)}", fmt_month(lo_bl[0]),
            [Delta(f"Brecha: {fmt_pct(br_val, 1)}", sentiment(br_val, "down")),
             _pct_delta("vs. mes anterior", mom, "down")],
            spark(df, "Brecha_Cambiaria_Pct"),
            help="Promedio mensual del Dólar Blue y brecha porcentual contra el Dólar Mayorista (Bluelytics).",
        )

    # Riesgo País
    lo_rp = last_obs(df, "Riesgo_Pais")
    k_rp = _missing_kpi("ext-riesgo", "Riesgo País (EMBI+)")
    if lo_rp:
        d_m = change_pp(df, "Riesgo_Pais", 1)
        d_y = change_pp(df, "Riesgo_Pais", 12)
        k_rp = KPI(
            "ext-riesgo", "Riesgo País (cierre mes)", f"{fmt_num(lo_rp[1], 0)} pb", fmt_month(lo_rp[0]),
            [Delta(f"{fmt_num(d_m, 0, signed=True)} pb vs. mes ant.", sentiment(d_m, "down")),
             Delta(f"{fmt_num(d_y, 0, signed=True)} pb interanual", sentiment(d_y, "down"))],
            spark(df, "Riesgo_Pais"),
            help="Riesgo País EMBI+ JP Morgan al cierre de cada mes (Scraping Ámbito / Rava).",
        )

    # Exportaciones FOB
    lo_ex = last_obs(df, "Exportaciones_FOB")
    k_ex = _missing_kpi("ext-expo", "Exportaciones FOB")
    if lo_ex:
        k_ex = KPI(
            "ext-expo", "Exportaciones FOB", fmt_usd_millions(lo_ex[1]), fmt_month(lo_ex[0]),
            [_pct_delta("interanual", change_pct(df, "Exportaciones_FOB", 12), "up"),
             _pct_delta("vs. mes ant.", change_pct(df, "Exportaciones_FOB", 1), "up")],
            spark(df, "Exportaciones_FOB"),
            help="Exportaciones totales mensuales FOB en millones de USD (ICA INDEC).",
        )

    return [kpi_saldo_comercial(df), k_en, k_res, k_itc, k_tc, k_bl, k_rp, k_ex]


def build_fiscal_kpis(df: pd.DataFrame) -> list[KPI]:
    def _real_ars_kpi(key: str, title: str, col: str, dir_: Direction, kind: Literal["line", "bar"] = "bar", help_: str = "") -> KPI:
        lo = last_obs(df, col)
        if lo is None:
            return _missing_kpi(key, title, help_)
        yoy = change_pct(df, col, 12)
        mom = change_pct(df, col, 1)
        return KPI(
            key, title, fmt_ars_millions(lo[1]), fmt_month(lo[0]),
            [_pct_delta("interanual real", yoy, dir_), _pct_delta("vs. mes ant.", mom, "neutral")],
            spark(df, col), kind, help=help_,
        )

    # Resultado Primario Real
    lo_rp = last_obs(df, "Resultado_Primario_Base_Caja_Real")
    k_rp = _missing_kpi("fis-rprim", "Resultado primario (real)")
    if lo_rp:
        acum12 = value_at(df, "Resultado_Primario_Real_12m", lo_rp[0])
        k_rp = KPI(
            "fis-rprim", "Resultado primario (real)", fmt_ars_millions(lo_rp[1]), fmt_month(lo_rp[0]),
            [Delta("Superávit primario" if lo_rp[1] >= 0 else "Déficit primario", sign_sentiment(lo_rp[1])),
             Delta(f"Acum. 12m: {fmt_ars_millions(acum12)}" if acum12 is not None else "")],
            spark(df, "Resultado_Primario_Base_Caja_Real"), "bar",
            help="Resultado primario de la APN Base Caja expresado a precios del último IPC (Hacienda).",
        )

    # Resultado Financiero Real
    lo_rf = last_obs(df, "Resultado_Financiero_Base_Caja_Real")
    k_rf = _missing_kpi("fis-rfin", "Resultado financiero (real)")
    if lo_rf:
        acum12 = value_at(df, "Resultado_Financiero_Real_12m", lo_rf[0])
        k_rf = KPI(
            "fis-rfin", "Resultado financiero (real)", fmt_ars_millions(lo_rf[1]), fmt_month(lo_rf[0]),
            [Delta("Superávit financiero" if lo_rf[1] >= 0 else "Déficit financiero", sign_sentiment(lo_rf[1])),
             Delta(f"Acum. 12m: {fmt_ars_millions(acum12)}" if acum12 is not None else "")],
            spark(df, "Resultado_Financiero_Base_Caja_Real"), "bar",
            help="Resultado financiero (después de intereses de deuda) a precios del último IPC (Hacienda).",
        )

    return [
        k_rp,
        k_rf,
        _real_ars_kpi("fis-ing", "Ingresos totales SPN (real)", "Ingresos_Publicos_Totales_Real", "up", "bar",
                      "Ingresos totales después de figurativos deflactados por IPC (Hacienda)."),
        kpi_gasto_real(df),
        _real_ars_kpi("fis-int", "Intereses de la deuda (real)", "Intereses_Deuda_Real", "neutral", "bar",
                      "Gasto Total − Gasto Primario deflactado por IPC (Hacienda)."),
        _real_ars_kpi("fis-rectot", "Recaudación tributaria (real)", "Recaudacion_Total_Real", "up", "line",
                      "Recaudación tributaria nacional total deflactada por IPC (ARCA / Hacienda)."),
        _real_ars_kpi("fis-dgi", "Recaudación DGI (real)", "Recaudacion_DGI_Real", "up", "line",
                      "Recaudación impositiva vinculada a la actividad interna (IVA, Ganancias, Cheque)."),
        _real_ars_kpi("fis-dga", "Recaudación Aduana DGA (real)", "Recaudacion_DGA_Real", "up", "line",
                      "Recaudación aduanera y comercio exterior deflactada por IPC."),
    ]


def build_dinero_kpis(df: pd.DataFrame) -> list[KPI]:
    # Base Monetaria Real
    lo_bm = last_obs(df, "Base_Monetaria_Real")
    k_bm = _missing_kpi("din-bm", "Base Monetaria (real)")
    if lo_bm:
        k_bm = KPI(
            "din-bm", "Base Monetaria (real)", fmt_ars_millions(lo_bm[1]), fmt_month(lo_bm[0]),
            [_pct_delta("interanual real", change_pct(df, "Base_Monetaria_Real", 12), "neutral"),
             _pct_delta("vs. mes anterior", change_pct(df, "Base_Monetaria_Real", 1), "neutral")],
            spark(df, "Base_Monetaria_Real"),
            help="Saldo de la Base Monetaria deflactado por IPC (BCRA API v4.0).",
        )

    # M2 Privado var. i.a.
    lo_m2 = last_obs(df, "M2_Privado_Var_IA")
    k_m2 = _missing_kpi("din-m2", "M2 Privado (var. i.a.)")
    if lo_m2:
        d_m2 = change_pp(df, "M2_Privado_Var_IA", 1)
        k_m2 = KPI(
            "din-m2", "M2 Privado (var. i.a.)", fmt_pct(lo_m2[1], 1), fmt_month(lo_m2[0]),
            [Delta(f"{fmt_pp(d_m2, 1)} vs. mes ant."), Delta("Medios de pago transaccionales")],
            spark(df, "M2_Privado_Var_IA"),
            help="Variación interanual del promedio móvil de 30 días del M2 privado (BCRA API v4.0).",
        )

    # Ratio Préstamos / Depósitos
    lo_pd = last_obs(df, "Ratio_Prestamos_Depositos_Pct")
    k_pd = _missing_kpi("din-ratio-pd", "Ratio Préstamos / Depósitos")
    if lo_pd:
        d_pd = change_pp(df, "Ratio_Prestamos_Depositos_Pct", 12)
        k_pd = KPI(
            "din-ratio-pd", "Ratio Préstamos / Depósitos", fmt_pct(lo_pd[1], 1), fmt_month(lo_pd[0]),
            [Delta(f"{fmt_pp(d_pd, 1)} interanual", sentiment(d_pd, "up")),
             Delta("Intermediación bancaria en pesos")],
            spark(df, "Ratio_Prestamos_Depositos_Pct"),
            help="Préstamos en pesos al sector privado sobre Depósitos totales en efectivo (BCRA).",
        )

    # Índice de Salarios INDEC Real
    lo_is = last_obs(df, "Indice_Salarios_Total_Real")
    k_is = _missing_kpi("din-indec-sal", "Índice de Salarios INDEC (real)")
    if lo_is:
        yoy = change_pct(df, "Indice_Salarios_Total_Real", 12)
        mom = change_pct(df, "Indice_Salarios_Total_Real", 1)
        k_is = KPI(
            "din-indec-sal", "Índice Salarios INDEC (real)", f"{fmt_pct(yoy, 1, signed=True)} i.a.", fmt_month(lo_is[0]),
            [_pct_delta("vs. mes anterior", mom, "up"), Delta("Incluye formales, públicos e informales")],
            spark(df, "Indice_Salarios_Total_Real"),
            help="Índice de Salarios Total (INDEC) deflactado por IPC Nacional.",
        )

    # Cobertura Salario / CBT
    lo_cbt = last_obs(df, "Ratio_Salario_CBT")
    k_cbt = _missing_kpi("din-cbt", "Cobertura Salario / Canasta (CBT)")
    if lo_cbt:
        yoy = change_pct(df, "Ratio_Salario_CBT", 12)
        k_cbt = KPI(
            "din-cbt", "Salario RIPTE / Canasta Básica", f"{fmt_num(lo_cbt[1], 2)}x CBT", fmt_month(lo_cbt[0]),
            [_pct_delta("interanual", yoy, "up"), Delta("Canastas básicas cubiertas por 1 RIPTE")],
            spark(df, "Ratio_Salario_CBT"),
            help="Cantidad de Canastas Básicas Totales (CBT) cubiertas por un salario formal RIPTE.",
        )

    # Desocupación y Pobreza (EPH)
    lo_des = last_obs(df, "Tasa_Desocupacion")
    lo_pob = last_obs(df, "Pobreza_Personas")
    k_eph = _missing_kpi("din-eph", "Desocupación y Pobreza (EPH)")
    if lo_des:
        d_des = change_pp(df, "Tasa_Desocupacion", 12)
        pob_txt = f"Pobreza personas: {fmt_pct(lo_pob[1], 1)}" if lo_pob else ""
        k_eph = KPI(
            "din-eph", "Desocupación (EPH)", fmt_pct(lo_des[1], 1), fmt_month(lo_des[0]),
            [Delta(f"{fmt_pp(d_des, 1)} interanual", sentiment(d_des, "down")), Delta(pob_txt)],
            spark(df, "Tasa_Desocupacion"),
            help="Tasa de desocupación abierta e incidencia de la pobreza en personas (EPH continua INDEC).",
        )

    return [
        k_bm,
        k_m2,
        kpi_credito_real(df),
        k_pd,
        kpi_salario_real(df),
        k_is,
        k_cbt,
        k_eph,
    ]


# --------------------------------------------------------------------------- #
# Lectura rápida automática
# --------------------------------------------------------------------------- #
def build_insights(df: pd.DataFrame) -> list[Delta]:
    """Frases automáticas que resumen la coyuntura, cada una con su connotación."""
    out: list[Delta] = []

    lo = last_obs(df, "Inflacion_Mensual_Pct")
    if lo:
        d = change_pp(df, "Inflacion_Mensual_Pct")
        yoy = value_at(df, "Inflacion_Interanual_Pct", lo[0])
        nucleo = value_at(df, "IPC_Nucleo_Mensual_Pct", lo[0])
        trend = "bajó" if (d or 0) < 0 else "subió" if (d or 0) > 0 else "se mantuvo"
        txt = f"La inflación de {fmt_month(lo[0])} fue {fmt_pct(lo[1], 1)} ({trend} {fmt_pp(abs(d) if d else 0).lstrip('+')} m/m)"
        if nucleo is not None:
            txt += f", con IPC Núcleo en {fmt_pct(nucleo, 1)}"
        if yoy is not None:
            txt += f" e interanual en {fmt_pct(yoy, 1)}"
        out.append(Delta(txt + ".", sentiment(d, "down")))

    lo = last_obs(df, "Tasa_Interes_Real_Mensual_Exacta")
    if lo:
        signo = "positiva" if lo[1] > 0 else "negativa"
        rem = last_obs(df, "REM_Inflacion_12m")
        rem_txt = f" El REM proyecta {fmt_pct(rem[1], 1)} de inflación a 12 meses." if rem else ""
        out.append(Delta(
            f"La tasa de plazo fijo fue {signo} en términos reales en {fmt_month(lo[0])} "
            f"({fmt_pct(lo[1], 2, signed=True)} mensual).{rem_txt}", sign_sentiment(lo[1])))

    lo = last_obs(df, "EMAE_Original")
    if lo:
        yoy = change_pct(df, "EMAE_Original", 12)
        uci = last_obs(df, "UCI_Industria")
        if yoy is not None:
            verbo = "creció" if yoy > 0 else "cayó"
            uci_txt = f" La industria operó al {fmt_pct(uci[1], 1)} de su capacidad instalada." if uci else ""
            out.append(Delta(
                f"La actividad económica {verbo} {fmt_pct(abs(yoy), 1)} interanual en {fmt_month(lo[0])}.{uci_txt}",
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
        res = last_obs(df, "Reservas_BCRA")
        res_txt = f", con reservas brutas en {fmt_usd_millions(res[1])}" if res else ""
        out.append(Delta(
            f"El saldo comercial de los últimos 12 meses acumula {fmt_usd_millions(acum)}{res_txt}.",
            sign_sentiment(acum)))

    lo_rp = last_obs(df, "Riesgo_Pais")
    lo_itc = last_obs(df, "ITCRM")
    if lo_rp and lo_itc:
        d_rp = change_pp(df, "Riesgo_Pais", 1)
        out.append(Delta(
            f"El Riesgo País se ubica en {fmt_num(lo_rp[1], 0)} pb ({fmt_num(d_rp, 0, signed=True)} pb mensual) "
            f"y el Tipo de Cambio Real Multilateral (ITCRM) promedia {fmt_num(lo_itc[1], 1)}.",
            sentiment(d_rp, "down"),
        ))

    return out
