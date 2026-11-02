"""
Pipeline multi-fuente de datos macroeconómicos y financieros de Argentina.

Proveedores soportados:
1. `datos_gob_ar`        : API de Series de Tiempo (apis.datos.gob.ar) + respaldo CSV (infra.datos.gob.ar).
2. `bcra_v4`             : API Estadísticas BCRA v4.0 (/estadisticas/v4.0/monetarias/{id}).
3. `bluelytics`          : API Bluelytics (histórico diario Dólar Oficial y Blue) + DolarAPI (cotizaciones en vivo).
4. `xlsx_bcra_itcrm`     : Planilla Excel oficial diaria del BCRA (ITCRMSerie.xlsx).
5. `xls_indec_uci`       : Scraper + planilla XLS oficial de INDEC (sh_capacidad_*.xls) + serie histórica SSPM.
6. `scraper_ambito_rava` : Web scraping de Riesgo País EMBI+ (Ámbito Financiero + fallback HTML Rava Bursátil).

Mantiene el dataset principal 100% mensual (`df`) y expone en paralelo el dataset diario de
alta frecuencia (`daily_df`) junto con las cotizaciones cambiarias en vivo (`fx_quotes`).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
import io
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
import urllib3
import warnings

from bs4 import BeautifulSoup
import pandas as pd
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message=".*xlrd engine is deprecated.*")

log = logging.getLogger("pipeline")

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}

# Estados posibles de cada serie
OK, CSV_FALLBACK, FROM_CACHE, ERROR = "ok", "respaldo_csv", "cache", "error"

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}


# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #
def load_config(config_path: str | Path = DEFAULT_CONFIG) -> dict:
    config_path = Path(config_path)
    if not config_path.is_absolute():
        config_path = BASE_DIR / config_path
    if not config_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de configuración en: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_catalog(config: dict) -> dict[str, dict]:
    """Devuelve {columna: metadatos} a partir de `columnas` en config.json."""
    series_cfg = config.get("series", {})
    catalog = {}
    for col, dotted in config["columnas"].items():
        parts = dotted.split(".")
        node = series_cfg
        for p in parts:
            node = node[p]
        root = series_cfg[parts[0]]
        catalog[col] = {
            "id": str(node["id"]),
            "provider": node.get("provider", root.get("provider", "datos_gob_ar")),
            "agg": node.get("agg", "mean"),
            "daily": bool(node.get("daily", False)),
            "field_title": node.get("field_title"),
            "csv_url": node.get("csv_url"),
            "descripcion": node.get("descripcion", ""),
            "frecuencia": node.get("frecuencia", "mensual"),
            "unidad": node.get("unidad", ""),
            "fuente": node.get("fuente", root.get("fuente", "")),
        }
    return catalog


# --------------------------------------------------------------------------- #
# Utilidades HTTP y Fechas
# --------------------------------------------------------------------------- #
def _get(url: str, params: dict | None, timeout: float, retries: int, verify: bool = True) -> requests.Response:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout, verify=verify)
            resp.raise_for_status()
            return resp
        except requests.HTTPError as e:
            if e.response is not None and 400 <= e.response.status_code < 500:
                raise
            last_err = e
        except requests.RequestException as e:
            last_err = e
        if attempt < retries - 1:
            time.sleep(1.0 * (attempt + 1))
    raise last_err  # type: ignore[misc]


def _to_month(dates) -> pd.Series:
    return pd.to_datetime(dates).dt.to_period("M").dt.to_timestamp()


def _aggregate_monthly(s: pd.Series, agg: str = "mean") -> pd.Series:
    """Agrupa una serie indexada por fecha a frecuencia mensual (MS)."""
    s = s.dropna().sort_index()
    if s.empty:
        return pd.Series(dtype=float)
    m_idx = s.index.to_period("M").to_timestamp()
    grouped = s.groupby(m_idx)
    out = grouped.last() if agg == "last" else grouped.mean()
    out.index.name = "Fecha"
    return out


def _rows_to_frame(rows: list, columns: list[str]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["Fecha", *columns])
    df["Fecha"] = _to_month(df["Fecha"])
    for c in columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.groupby("Fecha").mean()


# --------------------------------------------------------------------------- #
# Proveedor 1: API Series de Tiempo (datos.gob.ar) + Respaldo CSV
# --------------------------------------------------------------------------- #
def _fetch_csv_distribution(
    url: str,
    timeout: float,
    retries: int,
    field_title: str | None = None,
    csv_cache: dict[str, pd.DataFrame] | None = None,
) -> pd.Series:
    if csv_cache is not None and url in csv_cache:
        csv_df = csv_cache[url]
    else:
        resp = _get(url, None, timeout, retries)
        csv_df = pd.read_csv(io.StringIO(resp.text))
        if csv_cache is not None:
            csv_cache[url] = csv_df

    date_col = next(c for c in csv_df.columns if "fecha" in c.lower() or "tiempo" in c.lower())
    if field_title and field_title in csv_df.columns:
        val_col = field_title
    else:
        val_col = next(c for c in csv_df.columns if c != date_col)

    s = csv_df[[date_col, val_col]].dropna()
    out = pd.Series(pd.to_numeric(s[val_col], errors="coerce").values, index=_to_month(s[date_col]))
    return out.dropna().groupby(level=0).mean()


def _fetch_api_batch(api_base: str, ids: list[str], timeout: float, retries: int) -> tuple[pd.DataFrame, dict]:
    params = {"ids": ",".join(ids), "limit": 1000, "sort": "desc", "format": "json", "metadata": "full"}
    payload = _get(f"{api_base}/series/", params, timeout, retries).json()

    df = _rows_to_frame(payload.get("data", []), ids)
    urls = {}
    for m in payload.get("meta", [])[1:]:
        f = m.get("field", {})
        if f.get("id"):
            urls[f["id"]] = {
                "url": m.get("distribution", {}).get("downloadURL"),
                "end": f.get("time_index_end"),
                "field_title": f.get("title"),
            }
    return df, urls


def _fetch_datos_gob_ar(
    cols_meta: dict[str, dict], api_base: str, timeout: float, retries: int
) -> tuple[dict[str, pd.Series], dict[str, dict]]:
    id_to_col = {v["id"]: k for k, v in cols_meta.items()}
    ids = list(id_to_col)
    series: dict[str, pd.Series] = {}
    status: dict[str, dict] = {}
    urls: dict[str, dict] = {}
    csv_cache: dict[str, pd.DataFrame] = {}

    # Lotes de hasta 25 series para respetar el límite de la API
    batch_size = 25
    for i in range(0, len(ids), batch_size):
        batch = ids[i : i + batch_size]
        try:
            df, u = _fetch_api_batch(api_base, batch, timeout, retries)
            urls.update(u)
            for sid in batch:
                if sid in df:
                    series[id_to_col[sid]] = df[sid]
        except Exception as e:  # noqa: BLE001
            log.warning("Falló lote datos.gob.ar (%s). Intentando serie por serie.", e)
            for sid in batch:
                col = id_to_col[sid]
                try:
                    df, u = _fetch_api_batch(api_base, [sid], timeout, retries)
                    series[col] = df[sid]
                    urls.update(u)
                except Exception as e2:  # noqa: BLE001
                    # Intentar CSV directo si está declarado en config.json
                    csv_url = cols_meta[col].get("csv_url")
                    if csv_url:
                        try:
                            series[col] = _fetch_csv_distribution(
                                csv_url, timeout, retries, cols_meta[col].get("field_title"), csv_cache
                            )
                            status[col] = {"estado": CSV_FALLBACK, "detalle": "Recuperada desde distribución CSV"}
                            continue
                        except Exception:  # noqa: BLE001
                            pass
                    status[col] = {"estado": ERROR, "detalle": str(e2)[:200]}

    # 2) Enriquecer / recuperar series desde su distribución CSV oficial (que suele estar más al día que el índice API)
    for col, meta in cols_meta.items():
        s = series.get(col, pd.Series(dtype=float))
        info = urls.get(meta["id"], {})
        url = meta.get("csv_url") or info.get("url")
        field_title = meta.get("field_title") or info.get("field_title")

        need_csv = (not s.notna().any()) or (
            bool(meta.get("csv_url")) and bool(field_title) and int(s.dropna().size) < 150
        )
        if not need_csv:
            status.setdefault(col, {"estado": OK})
            continue
        if not url:
            if s.notna().any():
                status.setdefault(col, {"estado": OK})
            else:
                status[col] = {"estado": ERROR, "detalle": "Serie vacía en API y sin CSV de respaldo"}
                series.pop(col, None)
            continue
        try:
            s_csv = _fetch_csv_distribution(url, timeout, retries, field_title, csv_cache)
            if info.get("end") and not s.notna().any():
                s_csv = s_csv[s_csv.index <= pd.Timestamp(info["end"])]
            combined = s_csv.combine_first(s).dropna().sort_index()
            if combined.notna().any():
                was_empty = not s.notna().any()
                series[col] = combined
                status[col] = (
                    {"estado": CSV_FALLBACK, "detalle": "Recuperada desde la distribución CSV"}
                    if was_empty
                    else {"estado": OK}
                )
            else:
                status[col] = {"estado": ERROR, "detalle": "CSV de respaldo sin observaciones válidas"}
                series.pop(col, None)
        except Exception as e:  # noqa: BLE001
            if s.notna().any():
                status.setdefault(col, {"estado": OK})
            else:
                status[col] = {"estado": ERROR, "detalle": f"CSV de respaldo falló: {str(e)[:150]}"}
                series.pop(col, None)


    return series, status


# --------------------------------------------------------------------------- #
# Proveedor 2: API Estadísticas BCRA v4.0
# --------------------------------------------------------------------------- #
def _fetch_bcra_one(
    col: str, meta: dict, bcra_base: str, timeout: float, retries: int
) -> tuple[str, pd.Series | None, pd.Series | None, dict]:
    var_id = meta["id"]
    url = f"{bcra_base}/{var_id}"
    try:
        resp = _get(url, {"desde": "2015-01-01", "limit": 3000}, timeout, retries, verify=False).json()
        results = resp.get("results", [])
        detalle = results[0].get("detalle", []) if results else []
        if not detalle:
            return col, None, None, {"estado": ERROR, "detalle": f"BCRA v4 devolvió vacío para ID {var_id}"}
        df = pd.DataFrame(detalle)
        df["Fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
        s_daily = df.dropna(subset=["Fecha", "valor"]).groupby("Fecha")["valor"].last().sort_index()
        s_monthly = _aggregate_monthly(s_daily, meta.get("agg", "mean"))
        return col, s_monthly, (s_daily if meta.get("daily") else None), {"estado": OK}
    except Exception as e:  # noqa: BLE001
        return col, None, None, {"estado": ERROR, "detalle": f"BCRA v4 falló: {str(e)[:160]}"}


def _fetch_bcra_v4(
    cols_meta: dict[str, dict], bcra_base: str, timeout: float, retries: int
) -> tuple[dict[str, pd.Series], dict[str, pd.Series], dict[str, dict]]:
    monthly: dict[str, pd.Series] = {}
    daily: dict[str, pd.Series] = {}
    status: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [
            pool.submit(_fetch_bcra_one, col, meta, bcra_base, timeout, retries)
            for col, meta in cols_meta.items()
        ]
        for fut in futures:
            col, s_m, s_d, st = fut.result()
            status[col] = st
            if s_m is not None and s_m.notna().any():
                monthly[col] = s_m
            if s_d is not None and s_d.notna().any():
                daily[col] = s_d
    return monthly, daily, status


# --------------------------------------------------------------------------- #
# Proveedor 3: Bluelytics (histórico diario Blue/Oficial) + DolarAPI (vivo)
# --------------------------------------------------------------------------- #
def _fetch_bluelytics_and_dolarapi(
    cols_meta: dict[str, dict], config: dict, timeout: float, retries: int
) -> tuple[dict[str, pd.Series], dict[str, pd.Series], dict[str, dict], list[dict]]:
    monthly: dict[str, pd.Series] = {}
    daily: dict[str, pd.Series] = {}
    status: dict[str, dict] = {}
    fx_quotes: list[dict] = []

    api_cfg = config.get("api", {})
    bl_url = api_cfg.get("bluelytics_url", "https://api.bluelytics.com.ar/v2/evolution.json")
    da_url = api_cfg.get("dolarapi_url", "https://dolarapi.com/v1/dolares")

    try:
        rows = _get(bl_url, None, timeout, retries).json()
        df = pd.DataFrame(rows)
        df["Fecha"] = pd.to_datetime(df["date"], errors="coerce")
        df["value_sell"] = pd.to_numeric(df["value_sell"], errors="coerce")
        for col, meta in cols_meta.items():
            src = meta["id"]
            sub = df[df["source"].str.lower() == src.lower()].dropna(subset=["Fecha", "value_sell"])
            if sub.empty:
                status[col] = {"estado": ERROR, "detalle": f"Fuente {src} sin datos en Bluelytics"}
                continue
            s_d = sub.groupby("Fecha")["value_sell"].last().sort_index()
            monthly[col] = _aggregate_monthly(s_d, meta.get("agg", "mean"))
            if meta.get("daily"):
                daily[col] = s_d
            status[col] = {"estado": OK}
    except Exception as e:  # noqa: BLE001
        for col in cols_meta:
            status[col] = {"estado": ERROR, "detalle": f"Bluelytics falló: {str(e)[:150]}"}

    try:
        q = _get(da_url, None, timeout, min(retries, 2)).json()
        if isinstance(q, list):
            fx_quotes = q
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudieron obtener cotizaciones en vivo de DolarAPI: %s", e)

    return monthly, daily, status, fx_quotes


# --------------------------------------------------------------------------- #
# Proveedor 4: Planilla Excel Oficial BCRA (ITCRMSerie.xlsx)
# --------------------------------------------------------------------------- #
def _fetch_xlsx_bcra_itcrm(
    cols_meta: dict[str, dict], config: dict, timeout: float, retries: int
) -> tuple[dict[str, pd.Series], dict[str, pd.Series], dict[str, dict]]:
    monthly: dict[str, pd.Series] = {}
    daily: dict[str, pd.Series] = {}
    status: dict[str, dict] = {}
    url = config.get("api", {}).get(
        "itcrm_xlsx_url", "https://www.bcra.gob.ar/Pdfs/PublicacionesEstadisticas/ITCRMSerie.xlsx"
    )
    try:
        resp = _get(url, None, max(timeout, 25), retries, verify=False)
        xls = pd.read_excel(io.BytesIO(resp.content), sheet_name=0)
        headers = xls.iloc[0].astype(str).str.strip().tolist()
        xls = xls.iloc[1:].copy()
        xls.columns = headers
        date_col = next((c for c in xls.columns if "per" in c.lower() or "fecha" in c.lower()), xls.columns[0])
        xls["Fecha"] = pd.to_datetime(xls[date_col], errors="coerce")
        xls = xls.dropna(subset=["Fecha"]).set_index("Fecha").sort_index()

        for col, meta in cols_meta.items():
            target = meta["id"].strip()
            match_col = next((c for c in xls.columns if c.strip().lower() == target.lower()), None)
            if not match_col:
                status[col] = {"estado": ERROR, "detalle": f"Columna '{target}' no encontrada en ITCRMSerie.xlsx"}
                continue
            s_d = pd.to_numeric(xls[match_col], errors="coerce").dropna()
            s_d = s_d.groupby(level=0).last().sort_index()
            monthly[col] = _aggregate_monthly(s_d, meta.get("agg", "mean"))
            if meta.get("daily"):
                daily[col] = s_d
            status[col] = {"estado": OK, "detalle": "Extraído de planilla oficial ITCRMSerie.xlsx (BCRA)"}
    except Exception as e:  # noqa: BLE001
        for col in cols_meta:
            status[col] = {"estado": ERROR, "detalle": f"XLSX ITCRM falló: {str(e)[:150]}"}
    return monthly, daily, status


# --------------------------------------------------------------------------- #
# Proveedor 5: Planilla XLS Oficial INDEC (Capacidad Instalada UCI + empalme)
# --------------------------------------------------------------------------- #
def _fetch_xls_indec_uci(
    cols_meta: dict[str, dict], config: dict, timeout: float, retries: int
) -> tuple[dict[str, pd.Series], dict[str, dict]]:
    monthly: dict[str, pd.Series] = {}
    status: dict[str, dict] = {}
    xls_url = config.get("api", {}).get(
        "indec_uci_xls_url", "https://www.indec.gob.ar/ftp/cuadros/economia/sh_capacidad_08_26.xls"
    )
    for col, meta in cols_meta.items():
        s_base = pd.Series(dtype=float)
        # 1) Serie histórica base desde CSV/API de datos.gob.ar (2004-presente)
        if meta.get("csv_url"):
            try:
                s_base = _fetch_csv_distribution(meta["csv_url"], timeout, retries, meta.get("field_title"))
            except Exception:  # noqa: BLE001
                pass

        # 2) Planilla XLS oficial de INDEC (2016-2026)
        try:
            resp = _get(xls_url, None, timeout, retries, verify=False)
            raw_uci = pd.read_excel(io.BytesIO(resp.content), sheet_name=0)
            cur_year = None
            uci_rows: dict[pd.Timestamp, float] = {}
            for _, row in raw_uci.iterrows():
                c0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
                m_yr = re.search(r"A[ñn]o\s+(\d{4})", c0, re.I)
                if m_yr:
                    cur_year = int(m_yr.group(1))
                    continue
                m_clean = re.sub(r"[^a-zA-Záéíóúñ]", "", c0).lower()
                if cur_year and m_clean in MESES_ES:
                    val = pd.to_numeric(row.iloc[1], errors="coerce")
                    if pd.notna(val):
                        uci_rows[pd.Timestamp(year=cur_year, month=MESES_ES[m_clean], day=1)] = float(val)
            s_xls = pd.Series(uci_rows, dtype=float).sort_index()
            s_xls.index.name = "Fecha"
            combined = s_xls.combine_first(s_base).sort_index()
            if combined.notna().any():
                monthly[col] = combined
                status[col] = {"estado": OK, "detalle": "Extraído de planilla XLS de INDEC + serie histórica"}
            else:
                status[col] = {"estado": ERROR, "detalle": "No se encontraron filas en XLS de INDEC"}
        except Exception as e:  # noqa: BLE001
            if s_base.notna().any():
                monthly[col] = s_base
                status[col] = {"estado": CSV_FALLBACK, "detalle": f"XLS falló ({e}); se usa CSV datos.gob.ar"}
            else:
                status[col] = {"estado": ERROR, "detalle": f"XLS INDEC UCI falló: {str(e)[:150]}"}
    return monthly, status


# --------------------------------------------------------------------------- #
# Proveedor 6: Web Scraping Ámbito / Rava Bursátil (Riesgo País EMBI+)
# --------------------------------------------------------------------------- #
def _fetch_scraper_riesgo_pais(
    cols_meta: dict[str, dict], config: dict, timeout: float, retries: int
) -> tuple[dict[str, pd.Series], dict[str, pd.Series], dict[str, dict]]:
    monthly: dict[str, pd.Series] = {}
    daily: dict[str, pd.Series] = {}
    status: dict[str, dict] = {}

    api_cfg = config.get("api", {})
    ambito_url = api_cfg.get(
        "ambito_riesgo_url",
        "https://mercados.ambito.com//riesgopais/historico-general/2016-01-01/2027-12-31",
    )
    rava_url = api_cfg.get("rava_riesgo_url", "https://www.rava.com/perfil/riesgo%20pais")

    s_d = pd.Series(dtype=float)
    detalle_ok = ""

    # Opción A: Endpoint histórico de Ámbito Financiero
    try:
        raw_list = _get(ambito_url, None, timeout, retries).json()
        if isinstance(raw_list, list) and len(raw_list) > 1:
            df = pd.DataFrame(raw_list[1:], columns=["Fecha", "Valor"])
            df["Fecha"] = pd.to_datetime(df["Fecha"], format="%d-%m-%Y", errors="coerce")
            df["Valor"] = pd.to_numeric(
                df["Valor"].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
                errors="coerce",
            )
            s_d = df.dropna(subset=["Fecha", "Valor"]).groupby("Fecha")["Valor"].last().sort_index()
            detalle_ok = "Scraping Ámbito Financiero (serie histórica diaria)"
    except Exception as e:  # noqa: BLE001
        log.warning("Scraping Ámbito Riesgo País falló (%s). Probando fallback Rava HTML.", e)

    # Opción B: Fallback HTML Scraping con BeautifulSoup sobre Rava Bursátil
    if s_d.empty:
        try:
            html_text = _get(rava_url, None, timeout, retries).text
            soup = BeautifulSoup(html_text, "html.parser")
            m = re.search(r'"cierre"\s*:\s*(\[\s*\{.*?\}\s*\])', str(soup), re.S)
            if m:
                rows = json.loads(m.group(1))
                df = pd.DataFrame(rows)
                df["Fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
                df["Valor"] = pd.to_numeric(df["ultimo"], errors="coerce")
                s_d = df.dropna(subset=["Fecha", "Valor"]).groupby("Fecha")["Valor"].last().sort_index()
                detalle_ok = "Scraping HTML Rava Bursátil"
        except Exception as e2:  # noqa: BLE001
            log.warning("Fallback Rava Riesgo País falló: %s", e2)

    for col, meta in cols_meta.items():
        if s_d.notna().any():
            monthly[col] = _aggregate_monthly(s_d, meta.get("agg", "last"))
            if meta.get("daily"):
                daily[col] = s_d
            status[col] = {"estado": OK, "detalle": detalle_ok}
        else:
            status[col] = {"estado": ERROR, "detalle": "No se pudo extraer Riesgo País de Ámbito ni de Rava"}

    return monthly, daily, status


# --------------------------------------------------------------------------- #
# Orquestador de Descarga Multi-Fuente
# --------------------------------------------------------------------------- #
def fetch_all_bundle(
    config: dict,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict], list[dict]]:
    """
    Descarga todas las series de todos los proveedores en paralelo.
    Devuelve (raw_monthly_df, raw_daily_df, status_dict, fx_quotes).
    """
    catalog = resolve_catalog(config)
    api_cfg = config.get("api", {})
    api_base = api_cfg.get("base_url", "https://apis.datos.gob.ar/series/api")
    bcra_base = api_cfg.get("bcra_v4_url", "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias")
    cache_cfg = config.get("cache", {})
    timeout = cache_cfg.get("timeout_seconds", 20)
    retries = cache_cfg.get("retries", 3)

    by_provider: dict[str, dict[str, dict]] = {}
    for col, meta in catalog.items():
        by_provider.setdefault(meta["provider"], {})[col] = meta

    monthly_series: dict[str, pd.Series] = {}
    daily_series: dict[str, pd.Series] = {}
    status: dict[str, dict] = {}
    fx_quotes: list[dict] = []

    with ThreadPoolExecutor(max_workers=6) as pool:
        f_dga = (
            pool.submit(_fetch_datos_gob_ar, by_provider["datos_gob_ar"], api_base, timeout, retries)
            if "datos_gob_ar" in by_provider
            else None
        )
        f_bcra = (
            pool.submit(_fetch_bcra_v4, by_provider["bcra_v4"], bcra_base, timeout, retries)
            if "bcra_v4" in by_provider
            else None
        )
        f_bl = (
            pool.submit(_fetch_bluelytics_and_dolarapi, by_provider["bluelytics"], config, timeout, retries)
            if "bluelytics" in by_provider
            else None
        )
        f_itcrm = (
            pool.submit(_fetch_xlsx_bcra_itcrm, by_provider["xlsx_bcra_itcrm"], config, timeout, retries)
            if "xlsx_bcra_itcrm" in by_provider
            else None
        )
        f_uci = (
            pool.submit(_fetch_xls_indec_uci, by_provider["xls_indec_uci"], config, timeout, retries)
            if "xls_indec_uci" in by_provider
            else None
        )
        f_rp = (
            pool.submit(
                _fetch_scraper_riesgo_pais, by_provider["scraper_ambito_rava"], config, timeout, retries
            )
            if "scraper_ambito_rava" in by_provider
            else None
        )

        if f_dga:
            m, st = f_dga.result()
            monthly_series.update(m)
            status.update(st)
        if f_bcra:
            m, d, st = f_bcra.result()
            monthly_series.update(m)
            daily_series.update(d)
            status.update(st)
        if f_bl:
            m, d, st, quotes = f_bl.result()
            monthly_series.update(m)
            daily_series.update(d)
            status.update(st)
            fx_quotes = quotes
        if f_itcrm:
            m, d, st = f_itcrm.result()
            monthly_series.update(m)
            daily_series.update(d)
            status.update(st)
        if f_uci:
            m, st = f_uci.result()
            monthly_series.update(m)
            status.update(st)
        if f_rp:
            m, d, st = f_rp.result()
            monthly_series.update(m)
            daily_series.update(d)
            status.update(st)

    if not monthly_series:
        raise ConnectionError("No se pudo descargar ninguna serie de los proveedores configurados")

    raw_monthly = pd.DataFrame(monthly_series).sort_index()
    raw_monthly.index.name = "Fecha"

    raw_daily = pd.DataFrame(daily_series).sort_index() if daily_series else pd.DataFrame()
    if not raw_daily.empty:
        raw_daily.index.name = "Fecha"

    return raw_monthly, raw_daily, status, fx_quotes


def fetch_all(config: dict) -> tuple[pd.DataFrame, dict[str, dict]]:
    """Compatibilidad con la firma original: devuelve (raw_monthly_df, status_dict)."""
    raw_m, _, status, _ = fetch_all_bundle(config)
    return raw_m, status


# --------------------------------------------------------------------------- #
# Variables derivadas (Mensuales y Diarias)
# --------------------------------------------------------------------------- #
def _pct_change_series(s: pd.Series, periods: int) -> pd.Series:
    return (s / s.shift(periods) - 1) * 100


def derive(raw: pd.DataFrame, deflate_cols: list[str]) -> pd.DataFrame:
    """Calcula columnas derivadas sobre un DataFrame mensual indexado por Fecha."""
    if raw.empty:
        return raw.copy()
    idx = pd.date_range(raw.index.min(), raw.index.max(), freq="MS", name="Fecha")
    df = raw.reindex(idx).copy()

    # Forward-fill acotado (hasta 2 meses) para series trimestrales/semestrales (EPH)
    for q_col in ["Tasa_Desocupacion", "Tasa_Empleo", "Tasa_Actividad"]:
        if q_col in df:
            df[q_col] = df[q_col].ffill(limit=2)
    for s_col in ["Pobreza_Personas", "Pobreza_Hogares"]:
        if s_col in df:
            df[s_col] = df[s_col].ffill(limit=5)

    # 1. Deflactación por IPC Nivel General (a precios del último IPC disponible)
    if "IPC_Nivel_General" in df:
        ipc = df["IPC_Nivel_General"]
        ipc_valid = ipc.dropna()
        if not ipc_valid.empty:
            ipc_last = ipc_valid.iloc[-1]
            for col in deflate_cols:
                if col in df:
                    df[f"{col}_Real"] = df[col] / ipc * ipc_last
        df["Inflacion_Interanual_Pct"] = _pct_change_series(ipc, 12)

    if "IPC_Variacion_Mensual" in df:
        df["Inflacion_Mensual_Pct"] = df["IPC_Variacion_Mensual"] * 100

    # Aperturas del IPC y Precios Mayoristas (variaciones mensuales e interanuales)
    for col, prefix in [
        ("IPC_Nucleo", "IPC_Nucleo"),
        ("IPC_Regulados", "IPC_Regulados"),
        ("IPC_Estacionales", "IPC_Estacionales"),
        ("IPIM_Nivel_General", "IPIM"),
    ]:
        if col in df:
            df[f"{prefix}_Mensual_Pct"] = _pct_change_series(df[col], 1)
            df[f"{prefix}_Interanual_Pct"] = _pct_change_series(df[col], 12)

    # 2. Tasas de interés reales (Fisher exacta ex-post y ex-ante con REM)
    if "Tasa_Interes_Nominal" in df:
        i_m = df["Tasa_Interes_Nominal"] / 12 / 100
        df["Tasa_Nominal_Mensual_Pct"] = i_m * 100
        if "IPC_Variacion_Mensual" in df:
            inf_m = df["IPC_Variacion_Mensual"]
            real_m = (1 + i_m) / (1 + inf_m) - 1
            df["Tasa_Interes_Real_Mensual_Exacta"] = real_m * 100
            df["Tasa_Interes_Real_Mensual_Aprox"] = (i_m - inf_m) * 100
            df["Tasa_Real_Anualizada_Pct"] = ((1 + real_m) ** 12 - 1) * 100
        if "REM_Inflacion_12m" in df:
            tea = (1 + i_m) ** 12 - 1
            rem_dec = df["REM_Inflacion_12m"] / 100
            df["Tasa_Real_ExAnte_Anual_Pct"] = ((1 + tea) / (1 + rem_dec) - 1) * 100

    # 3. Sector Externo y Cambiario
    if {"Exportaciones_FOB", "Importaciones_CIF"} <= set(df.columns):
        df["Saldo_Comercial"] = df["Exportaciones_FOB"] - df["Importaciones_CIF"]

    if {"Expo_Combustibles_Energia", "Impo_Combustibles"} <= set(df.columns):
        df["Balanza_Energetica"] = df["Expo_Combustibles_Energia"] - df["Impo_Combustibles"]

    if {"Dolar_Blue", "TC_Mayorista"} <= set(df.columns):
        df["Brecha_Cambiaria_Pct"] = (df["Dolar_Blue"] / df["TC_Mayorista"] - 1) * 100

    if "TC_Mayorista" in df:
        df["Crawling_Peg_Mensual_Pct"] = _pct_change_series(df["TC_Mayorista"], 1)

    # 4. Sector Fiscal
    if {"Gasto_Publico_Total_Real", "Gasto_Publico_Primario_Real"} <= set(df.columns):
        df["Intereses_Deuda_Real"] = df["Gasto_Publico_Total_Real"] - df["Gasto_Publico_Primario_Real"]

    if "Resultado_Primario_Base_Caja_Real" in df:
        df["Resultado_Primario_Real_12m"] = (
            df["Resultado_Primario_Base_Caja_Real"].rolling(12, min_periods=12).sum()
        )
    if "Resultado_Financiero_Base_Caja_Real" in df:
        df["Resultado_Financiero_Real_12m"] = (
            df["Resultado_Financiero_Base_Caja_Real"].rolling(12, min_periods=12).sum()
        )

    # 5. Liquidez Bancaria y Poder Adquisitivo Social
    if {"Credito_Interno", "Depositos_Privados_Pesos"} <= set(df.columns):
        df["Ratio_Prestamos_Depositos_Pct"] = df["Credito_Interno"] / df["Depositos_Privados_Pesos"] * 100

    if {"Salarios", "Canasta_Basica_Total"} <= set(df.columns):
        df["Ratio_Salario_CBT"] = df["Salarios"] / df["Canasta_Basica_Total"]

    return df


def derive_daily(raw_daily: pd.DataFrame) -> pd.DataFrame:
    """Calcula variables derivadas en el DataFrame diario de alta frecuencia."""
    if raw_daily is None or raw_daily.empty:
        return pd.DataFrame(columns=["Fecha"])
    df = raw_daily.sort_index().copy()
    # Forward-fill corto (hasta 5 días) para alinear feriados/fines de semana entre mercados
    df_ff = df.ffill(limit=5)
    if {"Dolar_Blue", "TC_Mayorista"} <= set(df.columns):
        df["Brecha_Cambiaria_Pct"] = (df_ff["Dolar_Blue"] / df_ff["TC_Mayorista"] - 1) * 100
    if {"Tasa_TAMAR", "Tasa_BADLAR"} <= set(df.columns):
        df["Spread_TAMAR_BADLAR_pp"] = df_ff["Tasa_TAMAR"] - df_ff["Tasa_BADLAR"]
    return df.reset_index()


# --------------------------------------------------------------------------- #
# Caché en disco
# --------------------------------------------------------------------------- #
def _cache_paths(config: dict) -> tuple[Path, Path]:
    cache_dir = BASE_DIR / config.get("cache", {}).get("dir", "data/cache")
    return cache_dir / "series_raw.parquet", cache_dir / "meta.json"


def _daily_cache_path(config: dict) -> Path:
    cache_dir = BASE_DIR / config.get("cache", {}).get("dir", "data/cache")
    return cache_dir / "series_daily.parquet"


def read_cache(config: dict) -> tuple[pd.DataFrame, dict] | None:
    data_path, meta_path = _cache_paths(config)
    if not (data_path.exists() and meta_path.exists()):
        return None
    try:
        raw = pd.read_parquet(data_path)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return raw, meta
    except Exception as e:  # noqa: BLE001
        log.warning("Caché ilegible (%s); se ignora.", e)
        return None


def read_daily_cache(config: dict) -> pd.DataFrame:
    p = _daily_cache_path(config)
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def write_cache(
    config: dict, raw: pd.DataFrame, meta: dict, raw_daily: pd.DataFrame | None = None
) -> None:
    data_path, meta_path = _cache_paths(config)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = f".{os.getpid()}.{threading.get_ident()}.tmp"

    tmp_data = data_path.with_suffix(suffix)
    raw.to_parquet(tmp_data)
    tmp_data.replace(data_path)

    if raw_daily is not None and not raw_daily.empty:
        daily_path = _daily_cache_path(config)
        tmp_daily = daily_path.with_suffix(suffix)
        raw_daily.to_parquet(tmp_daily)
        tmp_daily.replace(daily_path)

    tmp_meta = meta_path.with_suffix(suffix)
    tmp_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_meta.replace(meta_path)


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
@dataclass
class MacroData:
    df: pd.DataFrame                                      # DataFrame mensual (Fecha + series + derivadas)
    fetched_at: datetime | None                           # Momento de la última descarga exitosa
    source: str                                           # "api" | "cache" | "cache_desactualizada"
    series_status: dict[str, dict] = field(default_factory=dict)
    error: str | None = None
    daily_df: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["Fecha"]))
    fx_quotes: list[dict] = field(default_factory=list)

    @property
    def n_ok(self) -> int:
        return sum(1 for s in self.series_status.values() if s["estado"] != ERROR)

    @property
    def n_total(self) -> int:
        return len(self.series_status)


def _annotate_status(raw: pd.DataFrame, status: dict[str, dict], catalog: dict) -> dict[str, dict]:
    for col in catalog:
        st = status.setdefault(col, {"estado": ERROR, "detalle": "Sin datos"})
        s = raw[col].dropna() if col in raw else pd.Series(dtype=float)
        st["ultimo_dato"] = s.index.max().strftime("%Y-%m") if not s.empty else None
        st["observaciones"] = int(s.size)
        st["descripcion"] = catalog[col]["descripcion"]
        st["fuente"] = catalog[col]["fuente"]
        st["provider"] = catalog[col]["provider"]
        st["frecuencia"] = catalog[col]["frecuencia"]
        st["unidad"] = catalog[col]["unidad"]
        st["id"] = catalog[col]["id"]
    return status


def _finalize(raw: pd.DataFrame, config: dict) -> pd.DataFrame:
    df = derive(raw, config.get("deflactar", []))
    return df.reset_index()


def get_macro_data(config_path: str | Path = DEFAULT_CONFIG, force: bool = False) -> MacroData:
    """Punto de entrada principal. Usa caché si está fresca, si no descarga y actualiza la caché."""
    config = load_config(config_path)
    catalog = resolve_catalog(config)
    max_age_h = config.get("cache", {}).get("max_age_hours", 6)
    cached = read_cache(config)
    cached_daily = read_daily_cache(config)

    if cached and not force:
        raw_c, meta_c = cached
        fetched_at = datetime.fromisoformat(meta_c["fetched_at"])
        age_h = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
        # Si la caché tiene todas las columnas configuradas y es fresca, se devuelve sin red
        if age_h < max_age_h and set(catalog.keys()) <= set(raw_c.columns):
            return MacroData(
                _finalize(raw_c, config),
                fetched_at,
                "cache",
                meta_c.get("series", {}),
                daily_df=derive_daily(cached_daily),
                fx_quotes=meta_c.get("fx_quotes", []),
            )

    raw_daily = pd.DataFrame()
    fx_quotes: list[dict] = []
    try:
        # Llamamos a fetch_all para respetar monkeypatches en tests unitarios;
        # cuando es nuestra función nativa, delegamos a fetch_all_bundle para traer también daily_df.
        if fetch_all is _DEFAULT_FETCH_ALL:
            raw, raw_daily, status, fx_quotes = fetch_all_bundle(config)
        else:
            raw, status = fetch_all(config)
    except Exception as e:  # noqa: BLE001
        log.error("Descarga fallida: %s", e)
        if cached:
            raw_c, meta_c = cached
            return MacroData(
                _finalize(raw_c, config),
                datetime.fromisoformat(meta_c["fetched_at"]),
                "cache_desactualizada",
                meta_c.get("series", {}),
                error=str(e),
                daily_df=derive_daily(cached_daily),
                fx_quotes=meta_c.get("fx_quotes", []),
            )
        raise

    # Completar series fallidas con la caché anterior
    if cached:
        raw_c, meta_c = cached
        for col, st in status.items():
            if st["estado"] == ERROR and col in raw_c and raw_c[col].notna().any():
                raw = raw.join(raw_c[[col]], how="outer") if col not in raw else raw
                status[col] = {
                    "estado": FROM_CACHE,
                    "detalle": f"Descarga falló; se usa caché. ({st.get('detalle', '')})",
                }
        if raw_daily.empty and not cached_daily.empty:
            raw_daily = cached_daily
        if not fx_quotes and meta_c.get("fx_quotes"):
            fx_quotes = meta_c["fx_quotes"]

    raw = raw.sort_index()
    status = _annotate_status(raw, status, catalog)
    fetched_at = datetime.now(timezone.utc)
    write_cache(
        config,
        raw,
        {"fetched_at": fetched_at.isoformat(), "series": status, "fx_quotes": fx_quotes},
        raw_daily=raw_daily,
    )
    return MacroData(
        _finalize(raw, config),
        fetched_at,
        "api",
        status,
        daily_df=derive_daily(raw_daily),
        fx_quotes=fx_quotes,
    )


_DEFAULT_FETCH_ALL = fetch_all


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    data = get_macro_data(force=True)
    print(f"Fuente: {data.source} · descargado: {data.fetched_at} · series OK: {data.n_ok}/{data.n_total}")
    print(f"Filas mensuales: {len(data.df)} · Filas diarias: {len(data.daily_df)} · Cotizaciones FX: {len(data.fx_quotes)}")
    for col, st in data.series_status.items():
        print(f"  {col:30s} [{st.get('provider', ''):19s}] {st['estado']:13s} último: {st.get('ultimo_dato')}  n={st.get('observaciones')}")
