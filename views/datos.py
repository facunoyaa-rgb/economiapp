"""Pestaña Datos y Metodología: Catálogo de 77 series, estado por proveedor, exportación CSV y notas metodológicas."""
from __future__ import annotations

from dash import dcc, html

from pipeline import CSV_FALLBACK, ERROR, FROM_CACHE, MacroData
from ui.components import card
from ui.format import fmt_ago, fmt_day, fmt_int, fmt_month


PROVIDER_NAMES = {
    "datos_gob_ar": "API Series de Tiempo (datos.gob.ar + Catálogo SSPM)",
    "bcra_v4": "API BCRA Estadísticas Monetarias v4.0",
    "bluelytics": "API Bluelytics (Dólar Libre / Blue Histórico)",
    "xlsx_bcra_itcrm": "Planilla XLSX Oficial BCRA (ITCRMSerie.xlsx)",
    "xls_indec_uci": "Planilla XLS Oficial INDEC (Capacidad Instalada UCI)",
    "scraper_ambito_rava": "Scraper Web Ámbito / Rava (Riesgo País EMBI+)",
}

STATUS_LABELS = {
    "ok": "OK",
    CSV_FALLBACK: "Respaldo CSV",
    FROM_CACHE: "Desde caché",
    ERROR: "Error",
}


def _provider_summary_cards(data: MacroData) -> html.Div:
    counts: dict[str, dict[str, int]] = {}
    for col, st in data.series_status.items():
        prov = st.get("provider", "datos_gob_ar")
        bucket = counts.setdefault(prov, {"total": 0, "ok": 0, "obs": 0})
        bucket["total"] += 1
        if st.get("estado") != ERROR:
            bucket["ok"] += 1
        bucket["obs"] += int(st.get("observaciones") or 0)

    cards = []
    for prov, meta in counts.items():
        title = PROVIDER_NAMES.get(prov, prov)
        ok_txt = f"{meta['ok']}/{meta['total']} series activas"
        obs_txt = f"{fmt_int(meta['obs'])} observaciones descargadas"
        cards.append(
            html.Div(
                [
                    html.Div(html.Span(title, className="kpi-title"), className="kpi-head"),
                    html.Div(html.Div(ok_txt, className="kpi-value", style={"fontSize": "1.12rem"}), className="kpi-body"),
                    html.Div(obs_txt, className="kpi-date"),
                ],
                className="kpi-card",
            )
        )
    return html.Div(cards, className="kpi-grid")


def layout(data: MacroData, years: int | None = None) -> html.Div:
    rows = []
    for col, s in data.series_status.items():
        freq = s.get("frequency", "M")
        ult = s.get("ultimo_dato")
        ult_str = (fmt_day(ult) if freq == "D" else fmt_month(ult)) if ult else "—"
        prov = s.get("provider", "datos_gob_ar")
        rows.append(
            html.Tr(
                [
                    html.Td(html.Strong(col.replace("_", " "))),
                    html.Td(prov),
                    html.Td(html.Code(str(s.get("id", "")), style={"fontSize": "0.72rem"})),
                    html.Td("Diaria" if freq == "D" else "Mensual"),
                    html.Td(s.get("unidad", "—")),
                    html.Td(STATUS_LABELS.get(s.get("estado", ""), s.get("estado", "")),
                            className=f"st st--{s.get('estado', '')}"),
                    html.Td(fmt_int(s.get("observaciones", 0))),
                    html.Td(ult_str),
                    html.Td(s.get("descripcion", ""), className="muted"),
                ]
            )
        )

    methodology_notes = html.Ul(
        [
            html.Li([
                html.Strong("Separación de Frecuencias (Mensual vs. Diaria): "),
                "El tablero principal mantiene una grilla 100% mensual (`MS`, inicio de mes) para asegurar "
                "consistencia en el deflactado por IPC y las variaciones interanuales (a/a). Las series nativas "
                "diarias se consolidan mediante promedio mensual (tasas, tipos de cambio, ITCRM) o último valor "
                "hábil (stocks y reservas), y además se exponen sin agregación en la pestaña ",
                html.Strong("Alta frecuencia (diario)"), ".",
            ], className="insight"),
            html.Li([
                html.Strong("Deflactación a Precios Constantes: "),
                "Todas las magnitudes nominales en pesos (Base Monetaria, Crédito, Plazos Fijos, Ingresos y Gastos "
                "del SPNF, Recaudación, Salarios y Tipos de Cambio Reales bilaterales internos) se expresan en "
                "pesos constantes del último mes con IPC publicado: ",
                html.Code("Valor_Real[t] = Valor_Nominal[t] * (IPC[T] / IPC[t])"), ".",
            ], className="insight"),
            html.Li([
                html.Strong("Tasas de Interés Efectivas y Reales (Ecuación de Fisher): "),
                "A partir de las TNA publicadas por el BCRA se calcula la Tasa Efectiva Mensual ",
                html.Code("TEM = TNA / 12"), " y la Tasa Efectiva Anual ",
                html.Code("TEA = (1 + TNA/12)^12 - 1"), ". La tasa real ex-post descuenta la inflación mensual "
                "efectiva mediante Fisher: ", html.Code("((1 + TEM) / (1 + Inflación_m/m)) - 1"),
                ", mientras que la tasa real ex-ante utiliza la expectativa de inflación a 12 meses del REM.",
            ], className="insight"),
            html.Li([
                html.Strong("Arquitectura Multi-Proveedor y Tolerancia a Fallos: "),
                "La ingesta combina en paralelo APIs gubernamentales REST (`datos.gob.ar` con enriquecimiento de "
                "distribuciones CSV completas del catálogo SSPM y `api.bcra.gob.ar/estadisticas/v4.0`), APIs de "
                "mercado (`Bluelytics` y `DolarAPI`), parseo directo en memoria de planillas Excel oficiales "
                "(`ITCRMSerie.xlsx` del BCRA y `sh_capacidad_08_26.xls` del INDEC) y web scraping de `Ámbito / Rava` "
                "con caché persistente en Parquet (`series_raw.parquet` y `series_daily.parquet`).",
            ], className="insight"),
        ],
        className="insights",
    )

    export_bar = html.Div(
        [
            html.Div(
                [
                    html.Strong("Exportación de bases de datos consolidadas: "),
                    html.Span(
                        f"Panel mensual ({len(data.df)} filas × {len(data.df.columns)} columnas) · "
                        f"Panel diario ({len(data.daily_df)} filas × {len(data.daily_df.columns)} columnas) · "
                        f"Última actualización {fmt_ago(data.fetched_at)}.",
                        className="muted",
                    ),
                ]
            ),
            html.Div(
                [
                    html.Button("⬇ Descargar Panel Mensual (CSV)", id="btn-download-monthly", n_clicks=0, className="btn"),
                    html.Button("⬇ Descargar Panel Diario (CSV)", id="btn-download-daily", n_clicks=0, className="btn"),
                    dcc.Download(id="download-monthly-csv"),
                    dcc.Download(id="download-daily-csv"),
                ],
                style={"display": "flex", "gap": "0.6rem", "flexWrap": "wrap"},
            ),
        ],
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "gap": "1rem",
            "flexWrap": "wrap",
        },
    )

    table = html.Div(
        html.Table(
            [
                html.Thead(
                    html.Tr(
                        [
                            html.Th("Serie"),
                            html.Th("Proveedor"),
                            html.Th("ID / Fuente"),
                            html.Th("Frecuencia"),
                            html.Th("Unidad"),
                            html.Th("Estado"),
                            html.Th("Obs."),
                            html.Th("Último dato"),
                            html.Th("Descripción"),
                        ]
                    )
                ),
                html.Tbody(rows),
            ],
            className="status-table",
        ),
        style={"overflowX": "auto", "maxHeight": "540px", "overflowY": "auto"},
    )

    return html.Div(
        [
            html.Section(
                [html.H2("Catálogo de Datos, Fuentes y Metodología", className="section-title"),
                 html.Span(f"Auditoría en vivo de las {data.n_total} series configuradas y notas metodológicas",
                           className="section-hint")],
                className="section-head",
            ),
            _provider_summary_cards(data),
            card(export_bar, "Descarga de Datos (CSV)"),
            card(methodology_notes, "Notas Metodológicas y Transformaciones"),
            card(table, f"Catálogo Completo de Series ({data.n_ok}/{data.n_total} operativas)",
                 "Detalle de proveedor, identificador técnico, frecuencia nativa y cobertura temporal."),
        ],
        className="view",
    )
