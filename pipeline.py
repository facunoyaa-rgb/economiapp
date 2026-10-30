"""
Pipeline de datos macroeconómicos de Argentina.

Descarga las series de la API de Series de Tiempo (datos.gob.ar) definidas en
config.json, las alinea a frecuencia mensual, calcula variables derivadas y
guarda un respaldo en disco (Parquet + JSON de metadatos).

Estrategia de resiliencia:
1. Si existe caché más nueva que `cache.max_age_hours`, se usa sin llamar a la API.
2. Si no, se descarga todo en una sola request multi-serie (con reintentos).
   Si esa request falla, se intenta serie por serie.
3. Series que vienen vacías desde la API se recuperan desde su distribución CSV.
4. Series que fallan igualmente conservan su valor de la caché anterior.
5. Si la API está caída por completo, se devuelve la caché (marcada como desactualizada).

Convenciones de unidades:
- IPC_Variacion_Mensual: decimal (0.0258 = 2,58%), tal como lo publica la API.
- Columnas con sufijo `_Pct` y todas las tasas de interés: en porcentaje.
- Columnas con sufijo `_Real`: deflactadas por IPC a precios del último IPC disponible.
"""
from __future__ import annotations

import io
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger("pipeline")

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Dashboard Macro Argentina)"}

# Estados posibles de cada serie
OK, CSV_FALLBACK, FROM_CACHE, ERROR = "ok", "respaldo_csv", "cache", "error"


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
    """Devuelve {columna: {id, descripcion, unidad, fuente}} a partir de `columnas` en config.json."""
    series_cfg = config.get("series", {})
    catalog = {}
    for col, dotted in config["columnas"].items():
        parts = dotted.split(".")
        node = series_cfg
        for p in parts:
            node = node[p]
        root = series_cfg[parts[0]]
        catalog[col] = {
            "id": node["id"],
            "descripcion": node.get("descripcion", ""),
            "unidad": node.get("unidad", ""),
            "fuente": root.get("fuente", ""),
        }
    return catalog


# --------------------------------------------------------------------------- #
# Descarga
# --------------------------------------------------------------------------- #
def _get(url: str, params: dict | None, timeout: float, retries: int) -> requests.Response:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.HTTPError as e:
            # Errores 4xx no se reintentan (p. ej. un ID inválido)
            if e.response is not None and 400 <= e.response.status_code < 500:
                raise
            last_err = e
        except requests.RequestException as e:
            last_err = e
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    raise last_err  # type: ignore[misc]


def _to_month(dates) -> pd.Series:
    return pd.to_datetime(dates).dt.to_period("M").dt.to_timestamp()


def _rows_to_frame(rows: list, columns: list[str]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["Fecha", *columns])
    df["Fecha"] = _to_month(df["Fecha"])
    for c in columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # Varias observaciones en el mismo mes -> promedio
    return df.groupby("Fecha").mean()


def _fetch_csv_distribution(url: str, timeout: float, retries: int) -> pd.Series:
    resp = _get(url, None, timeout, retries)
    csv_df = pd.read_csv(io.StringIO(resp.text))
    date_col = next(c for c in csv_df.columns if "fecha" in c.lower() or "tiempo" in c.lower())
    val_col = next(c for c in csv_df.columns if c != date_col)
    s = csv_df[[date_col, val_col]].dropna()
    out = pd.Series(pd.to_numeric(s[val_col], errors="coerce").values, index=_to_month(s[date_col]))
    return out.groupby(level=0).mean()


def _fetch_api(api_base: str, ids: list[str], timeout: float, retries: int) -> tuple[pd.DataFrame, dict]:
    """Request multi-serie. Devuelve (DataFrame por Fecha con columnas = ids, {id: {url, end}})."""
    params = {"ids": ",".join(ids), "limit": 5000, "format": "json", "metadata": "full"}
    payload = _get(f"{api_base}/series/", params, timeout, retries).json()
    df = _rows_to_frame(payload.get("data", []), ids)
    urls = {}
    for m in payload.get("meta", [])[1:]:
        f = m.get("field", {})
        if f.get("id"):
            urls[f["id"]] = {"url": m.get("distribution", {}).get("downloadURL"), "end": f.get("time_index_end")}
    return df, urls


def fetch_all(config: dict) -> tuple[pd.DataFrame, dict[str, dict]]:
    """Descarga todas las series. Devuelve (df con columnas por nombre, estado por columna)."""
    catalog = resolve_catalog(config)
    api_base = config.get("api", {}).get("base_url", "https://apis.datos.gob.ar/series/api")
    cache_cfg = config.get("cache", {})
    timeout = cache_cfg.get("timeout_seconds", 20)
    retries = cache_cfg.get("retries", 3)

    id_to_col = {v["id"]: k for k, v in catalog.items()}
    ids = list(id_to_col)
    series: dict[str, pd.Series] = {}
    status: dict[str, dict] = {}
    urls: dict[str, dict] = {}

    # 1) Intento multi-serie
    try:
        df, urls = _fetch_api(api_base, ids, timeout, retries)
        for sid in ids:
            series[id_to_col[sid]] = df[sid]
    except Exception as e:  # noqa: BLE001
        log.warning("Falló la request multi-serie (%s). Reintentando serie por serie.", e)
        for sid in ids:
            col = id_to_col[sid]
            try:
                df, u = _fetch_api(api_base, [sid], timeout, retries)
                series[col] = df[sid]
                urls.update(u)
            except Exception as e2:  # noqa: BLE001
                status[col] = {"estado": ERROR, "detalle": str(e2)[:200]}

    # 2) Series vacías -> distribución CSV
    for col, s in list(series.items()):
        if s.notna().any():
            status[col] = {"estado": OK}
            continue
        info = urls.get(catalog[col]["id"], {})
        url = info.get("url")
        if not url:
            status[col] = {"estado": ERROR, "detalle": "La API devolvió la serie vacía y no hay CSV de respaldo"}
            series.pop(col)
            continue
        try:
            s_csv = _fetch_csv_distribution(url, timeout, retries)
            # El CSV a veces trae filas espurias posteriores al fin declarado de la serie
            if info.get("end"):
                s_csv = s_csv[s_csv.index <= pd.Timestamp(info["end"])]
            series[col] = s_csv
            status[col] = {"estado": CSV_FALLBACK, "detalle": "Recuperada desde la distribución CSV"}
        except Exception as e:  # noqa: BLE001
            status[col] = {"estado": ERROR, "detalle": f"CSV de respaldo falló: {str(e)[:150]}"}
            series.pop(col)

    if not series:
        raise ConnectionError("No se pudo descargar ninguna serie de la API de datos.gob.ar")

    raw = pd.DataFrame(series).sort_index()
    raw.index.name = "Fecha"
    return raw, status


# --------------------------------------------------------------------------- #
# Variables derivadas
# --------------------------------------------------------------------------- #
def derive(raw: pd.DataFrame, deflate_cols: list[str]) -> pd.DataFrame:
    """Calcula columnas derivadas sobre un DataFrame mensual indexado por Fecha."""
    if raw.empty:
        return raw.copy()
    idx = pd.date_range(raw.index.min(), raw.index.max(), freq="MS", name="Fecha")
    df = raw.reindex(idx).copy()

    if "IPC_Nivel_General" in df:
        ipc = df["IPC_Nivel_General"]
        ipc_valid = ipc.dropna()
        if not ipc_valid.empty:
            ipc_last = ipc_valid.iloc[-1]
            for col in deflate_cols:
                if col in df:
                    df[f"{col}_Real"] = df[col] / ipc * ipc_last
        df["Inflacion_Interanual_Pct"] = (ipc / ipc.shift(12) - 1) * 100

    if "IPC_Variacion_Mensual" in df:
        df["Inflacion_Mensual_Pct"] = df["IPC_Variacion_Mensual"] * 100

    if "Tasa_Interes_Nominal" in df:
        i_m = df["Tasa_Interes_Nominal"] / 12 / 100
        df["Tasa_Nominal_Mensual_Pct"] = i_m * 100
        if "IPC_Variacion_Mensual" in df:
            inf_m = df["IPC_Variacion_Mensual"]
            real_m = (1 + i_m) / (1 + inf_m) - 1
            df["Tasa_Interes_Real_Mensual_Exacta"] = real_m * 100
            df["Tasa_Interes_Real_Mensual_Aprox"] = (i_m - inf_m) * 100
            df["Tasa_Real_Anualizada_Pct"] = ((1 + real_m) ** 12 - 1) * 100

    if {"Exportaciones_FOB", "Importaciones_CIF"} <= set(df.columns):
        df["Saldo_Comercial"] = df["Exportaciones_FOB"] - df["Importaciones_CIF"]

    return df


# --------------------------------------------------------------------------- #
# Caché en disco
# --------------------------------------------------------------------------- #
def _cache_paths(config: dict) -> tuple[Path, Path]:
    cache_dir = BASE_DIR / config.get("cache", {}).get("dir", "data/cache")
    return cache_dir / "series_raw.parquet", cache_dir / "meta.json"


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


def write_cache(config: dict, raw: pd.DataFrame, meta: dict) -> None:
    data_path, meta_path = _cache_paths(config)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = data_path.with_suffix(".tmp")
    raw.to_parquet(tmp)
    tmp.replace(data_path)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
@dataclass
class MacroData:
    df: pd.DataFrame                      # DataFrame con columna Fecha + series + derivadas
    fetched_at: datetime | None           # Momento de la última descarga exitosa
    source: str                           # "api" | "cache" | "cache_desactualizada"
    series_status: dict[str, dict] = field(default_factory=dict)
    error: str | None = None

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

    if cached and not force:
        raw_c, meta_c = cached
        fetched_at = datetime.fromisoformat(meta_c["fetched_at"])
        age_h = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
        if age_h < max_age_h:
            return MacroData(_finalize(raw_c, config), fetched_at, "cache", meta_c.get("series", {}))

    try:
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
            )
        raise

    # Completar series fallidas con la caché anterior
    if cached:
        raw_c, _ = cached
        for col, st in status.items():
            if st["estado"] == ERROR and col in raw_c and raw_c[col].notna().any():
                raw = raw.join(raw_c[[col]], how="outer") if col not in raw else raw
                status[col] = {"estado": FROM_CACHE, "detalle": f"Descarga falló; se usa caché. ({st.get('detalle', '')})"}

    raw = raw.sort_index()
    status = _annotate_status(raw, status, catalog)
    fetched_at = datetime.now(timezone.utc)
    write_cache(config, raw, {"fetched_at": fetched_at.isoformat(), "series": status})
    return MacroData(_finalize(raw, config), fetched_at, "api", status)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    data = get_macro_data(force=True)
    print(f"Fuente: {data.source} · descargado: {data.fetched_at} · series OK: {data.n_ok}/{data.n_total}")
    for col, st in data.series_status.items():
        print(f"  {col:28s} {st['estado']:13s} último: {st.get('ultimo_dato')}  n={st.get('observaciones')}")
    print(data.df.tail(3).T)
