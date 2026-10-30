"""Tests unitarios para formateo, cálculo de indicadores, Fisher y pipeline."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from indicators import build_insights, build_kpis, change_pct, change_pp, kpi_inflacion, sentiment
from pipeline import derive, get_macro_data, load_config, read_cache, write_cache
from ui.format import (
    DASH,
    MINUS,
    fmt_ars,
    fmt_ars_millions,
    fmt_month,
    fmt_num,
    fmt_pct,
    fmt_pp,
    fmt_usd_millions,
)


def test_format_es_ar():
    assert fmt_num(1234567.89, 1) == "1.234.567,9"
    assert fmt_num(-12.34, 1) == f"{MINUS}12,3"
    assert fmt_num(None) == DASH
    assert fmt_num(float("nan")) == DASH
    assert fmt_pct(1.66, 2) == "1,66%"
    assert fmt_pp(-0.45, 2) == f"{MINUS}0,45 pp"
    assert fmt_pp(1.15, 2) == "+1,15 pp"
    assert fmt_ars_millions(12_759_078.9, 1) == "$ 12,8 billones"
    assert fmt_ars(1_946_028.12, 2) == "$ 1,95 M"
    assert fmt_usd_millions(8882.58, 0) == "US$ 8.883 M"
    assert fmt_month(pd.Timestamp("2026-08-01")) == "ago 2026"


def test_semantic_sentiment_directions():
    # Para inflación (direction='down'), una baja es buena y una suba es mala
    assert sentiment(-0.45, "down") == "good"
    assert sentiment(+0.45, "down") == "bad"
    assert sentiment(0.0, "down") == "neutral"

    # Para actividad / salario (direction='up'), una suba es buena
    assert sentiment(+2.1, "up") == "good"
    assert sentiment(-2.1, "up") == "bad"


def test_derive_fisher_and_deflation():
    idx = pd.date_range("2025-01-01", periods=13, freq="MS", name="Fecha")
    raw = pd.DataFrame(
        {
            "IPC_Nivel_General": np.linspace(100.0, 200.0, 13),
            "IPC_Variacion_Mensual": [0.02] * 13,
            "Tasa_Interes_Nominal": [24.0] * 13,  # TNA 24% -> TEM 2%
            "Gasto_Publico_Primario": [1000.0] * 13,
            "Exportaciones_FOB": [500.0] * 13,
            "Importaciones_CIF": [400.0] * 13,
        },
        index=idx,
    )
    df = derive(raw, ["Gasto_Publico_Primario"])

    # Si TEM == inflación mensual (2%), la tasa real exacta debe ser 0%
    assert pytest.approx(df["Tasa_Interes_Real_Mensual_Exacta"].iloc[-1], abs=1e-9) == 0.0
    assert pytest.approx(df["Tasa_Real_Anualizada_Pct"].iloc[-1], abs=1e-9) == 0.0

    # El primer mes (IPC=100) expresado a precios del último mes (IPC=200) se duplica
    assert pytest.approx(df["Gasto_Publico_Primario_Real"].iloc[0]) == 2000.0
    assert pytest.approx(df["Gasto_Publico_Primario_Real"].iloc[-1]) == 1000.0

    # Inflación interanual entre mes 0 (100) y mes 12 (200) = +100%
    assert pytest.approx(df["Inflacion_Interanual_Pct"].iloc[12]) == 100.0
    assert pytest.approx(df["Saldo_Comercial"].iloc[-1]) == 100.0


def test_kpi_inflacion_drop_is_green():
    dates = pd.date_range("2025-07-01", periods=14, freq="MS")
    df = pd.DataFrame(
        {
            "Fecha": dates,
            "Inflacion_Mensual_Pct": [3.0] * 12 + [2.11, 1.66],
            "Inflacion_Interanual_Pct": [40.0] * 14,
        }
    )
    kpi = kpi_inflacion(df)
    assert kpi.available is True
    assert kpi.value == "1,66%"
    assert kpi.deltas[0].sentiment == "good"
    assert f"{MINUS}0,45 pp" in kpi.deltas[0].text


def test_cache_fallback_when_api_offline(tmp_path, monkeypatch):
    cfg = load_config()
    cfg["cache"]["dir"] = str(tmp_path)
    cfg["cache"]["max_age_hours"] = 0  # fuerza a intentar API

    idx = pd.date_range("2026-01-01", periods=3, freq="MS", name="Fecha")
    raw = pd.DataFrame({"EMAE_Desestacionalizado": [140.0, 142.0, 145.0]}, index=idx)
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "series": {"EMAE_Desestacionalizado": {"estado": "ok", "ultimo_dato": "2026-03", "observaciones": 3}},
    }
    write_cache(cfg, raw, meta)
    assert read_cache(cfg) is not None

    monkeypatch.setattr("pipeline.load_config", lambda _=None: cfg)

    def _boom(_cfg):
        raise ConnectionError("API caída simulada")

    monkeypatch.setattr("pipeline.fetch_all", _boom)

    data = get_macro_data(force=True)
    assert data.source == "cache_desactualizada"
    assert data.error is not None
    assert len(data.df) == 3


def test_live_cached_kpis_and_insights():
    data = get_macro_data(force=False)
    kpis = build_kpis(data.df)
    assert len(kpis) == 8
    assert all(k.available for k in kpis)
    insights = build_insights(data.df)
    assert len(insights) >= 3
