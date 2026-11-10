"""Formateo de números, fechas y montos en convención es-AR (1.234,5)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pandas as pd

DASH = "—"
MINUS = "−"  # signo menos tipográfico
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x)) or pd.isna(x)


def fmt_num(x, dec: int = 1, signed: bool = False) -> str:
    """1234567.891 -> '1.234.567,9'. Con signed=True agrega '+' o '−'."""
    if _missing(x):
        return DASH
    s = f"{abs(x):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if x < 0 and float(s.replace(".", "").replace(",", ".")) != 0:
        return f"{MINUS}{s}"
    if signed and x > 0:
        return f"+{s}"
    return s


def fmt_int(x, signed: bool = False) -> str:
    """Formatea un entero con separador de miles es-AR."""
    return fmt_num(x, 0, signed=signed)


def fmt_pct(x, dec: int = 1, signed: bool = False) -> str:
    """Valor ya expresado en porcentaje: 1.66 -> '1,7%'."""
    return DASH if _missing(x) else f"{fmt_num(x, dec, signed)}%"


def fmt_pp(x, dec: int = 2) -> str:
    """Diferencia en puntos porcentuales: 0.45 -> '+0,45 pp'."""
    return DASH if _missing(x) else f"{fmt_num(x, dec, signed=True)} pp"


def fmt_ars_millions(x_millions, dec: int = 1) -> str:
    """Monto expresado en millones de pesos -> texto abreviado."""
    if _missing(x_millions):
        return DASH
    return fmt_ars(x_millions * 1e6, dec)


def fmt_ars(x, dec: int = 1) -> str:
    """Monto en pesos -> '$ 12,3 billones' / '$ 850 mil M' / '$ 1,9 M' / '$ 12.345'."""
    if _missing(x):
        return DASH
    a = abs(x)
    if a >= 1e12:
        return f"$ {fmt_num(x / 1e12, dec)} billones"
    if a >= 1e9:
        return f"$ {fmt_num(x / 1e9, 0)} mil M"
    if a >= 1e6:
        return f"$ {fmt_num(x / 1e6, dec)} M"
    return f"$ {fmt_num(x, 0)}"


def fmt_usd_millions(x_millions, dec: int = 0) -> str:
    return DASH if _missing(x_millions) else f"US$ {fmt_num(x_millions, dec)} M"


def fmt_month(ts) -> str:
    """Timestamp -> 'ago 2026'."""
    if _missing(ts):
        return DASH
    ts = pd.Timestamp(ts)
    return f"{MESES[ts.month - 1]} {ts.year}"


def fmt_day(ts) -> str:
    """Timestamp -> '28 oct 2026'."""
    if _missing(ts):
        return DASH
    ts = pd.Timestamp(ts)
    return f"{ts.day:02d} {MESES[ts.month - 1]} {ts.year}"



def fmt_month_short(ts) -> str:
    """Timestamp -> 'ago-26'."""
    if _missing(ts):
        return DASH
    ts = pd.Timestamp(ts)
    return f"{MESES[ts.month - 1]}-{ts.strftime('%y')}"


def fmt_ago(dt: datetime | None, now: datetime | None = None) -> str:
    """Tiempo relativo: 'hace 5 min', 'hace 3 h', 'hace 2 días'."""
    if dt is None:
        return DASH
    now = now or datetime.now(timezone.utc)
    secs = max(0, (now - dt).total_seconds())
    if secs < 60:
        return "hace instantes"
    if secs < 3600:
        return f"hace {int(secs // 60)} min"
    if secs < 86400:
        return f"hace {int(secs // 3600)} h"
    d = int(secs // 86400)
    return f"hace {d} día{'s' if d != 1 else ''}"


AR_TZ = timezone(timedelta(hours=-3))  # Argentina no aplica horario de verano


def fmt_quote_time(iso: str | None) -> str:
    """'2026-11-05T18:55:00.000Z' -> '05 nov 15:55' (hora de Argentina)."""
    if not iso:
        return DASH
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return DASH
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(AR_TZ)
    return f"{dt.day:02d} {MESES[dt.month - 1]} {dt:%H:%M}"
