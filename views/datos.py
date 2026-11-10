"""Pestaña Datos y Metodología: Catálogo de 77 series, estado por proveedor, exportación CSV y notas metodológicas."""
from __future__ import annotations

from dash import dcc, html

from series_meta import HIDDEN, meta

from pipeline import CSV_FALLBACK, ERROR, FROM_CACHE, MacroData
from ui.components import card
from ui.format import fmt_ago, fmt_day, fmt_int, fmt_month


# Nombre corto del proveedor para la tabla (el largo va en las tarjetas de resumen)
PROVIDER_SHORT = {
    "datos_gob_ar": "datos.gob.ar",
    "bcra_v4": "BCRA",
    "bluelytics": "Bluelytics",
    "xlsx_bcra_itcrm": "BCRA (planilla ITCRM)",
    "xls_indec_uci": "INDEC (planilla UCI)",
    "scraper_ambito_rava": "Ámbito / Rava",
}

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
                    html.Div(html.Div(ok_txt, className="kpi-value kpi-value--sm"), className="kpi-body"),
                    html.Div(obs_txt, className="kpi-date"),
                ],
                className="kpi-card",
            )
        )
    return html.Div(cards, className="kpi-grid")


def layout(data: MacroData, years: int | None = None) -> html.Div:
    rows = []
    for col, st in sorted(data.series_status.items(), key=lambda kv: (meta(kv[0]).group, meta(kv[0]).label)):
        m = meta(col)
        daily = data.is_daily(col)
        ult = data.last_date(col)
        ult_str = "—" if ult is None else (fmt_day(ult) if daily else fmt_month(ult))
        prov = st.get("provider", "datos_gob_ar")
        sid = str(st.get("id", ""))
        explore = None
        if col not in HIDDEN and st.get("estado") != ERROR:
            key = f"d.{col}" if daily else col
            explore = dcc.Link("Explorar →", href=f"?s={key}#explorador", className="explore-link",
                               title=f"Abrir {m.label} en el Explorador")
        rows.append(
            html.Tr(
                [
                    html.Td([html.Strong(m.label), html.Span(col, className="series-col")],
                            **{"data-sort": m.label}),
                    html.Td(m.group),
                    html.Td(PROVIDER_SHORT.get(prov, prov), title=PROVIDER_NAMES.get(prov, prov)),
                    html.Td([html.Code(sid, className="series-id"),
                             html.Button("Copiar", type="button", className="copy-id",
                                         **{"data-copy": sid, "aria-label": f"Copiar el ID {sid}"})] if sid else "—"),
                    html.Td(str(st.get("frecuencia", "mensual")).capitalize()),
                    html.Td(st.get("unidad", "—")),
                    html.Td(STATUS_LABELS.get(st.get("estado", ""), st.get("estado", "")),
                            className=f"st st--{st.get('estado', '')}"),
                    html.Td(fmt_int(st.get("observaciones", 0)), **{"data-sort": str(st.get("observaciones", 0))}),
                    html.Td(ult_str, **{"data-sort": ult.strftime("%Y-%m-%d") if ult is not None else ""}),
                    html.Td(explore),
                ],
                title=st.get("descripcion", ""),
            )
        )

    C = html.Code
    methodology_notes = html.Ul(
        [
            html.Li([
                html.Strong("Separación de frecuencias (mensual y diaria). "),
                "El tablero principal usa una grilla mensual (", C("MS"), ", inicio de mes) para que el "
                "deflactado por IPC y las variaciones interanuales sean consistentes. Las series diarias se "
                "consolidan por promedio mensual (tasas, tipos de cambio, ITCRM) o por último valor hábil "
                "(stocks y reservas), y además se muestran sin agregar en la pestaña ",
                html.Strong("Alta frecuencia (diario)"), ".",
            ], className="method-note"),
            html.Li([
                html.Strong("Deflactación a precios constantes. "),
                "Las magnitudes nominales en pesos (base monetaria, crédito, plazos fijos, ingresos y gastos "
                "del SPN, recaudación, salarios y los tipos de cambio mayorista y blue) se expresan en pesos constantes del último mes con IPC "
                "publicado: ", C("Valor_Real[t] = Valor_Nominal[t] × IPC[T] / IPC[t]"), ".",
            ], className="method-note"),
            html.Li([
                html.Strong("Tasas efectivas y reales (ecuación de Fisher). "),
                "A partir de la TNA publicada por el BCRA se calcula la tasa efectiva mensual ",
                C("TEM = TNA / 12"), " y la efectiva anual ", C("TEA = (1 + TNA/12)^12 − 1"),
                ". La tasa real ex-post descuenta la inflación mensual observada: ",
                C("(1 + TEM) / (1 + π_m) − 1"),
                ". La tasa real ex-ante usa, en cambio, la inflación esperada a 12 meses del REM.",
            ], className="method-note"),
            html.Li([
                html.Strong("Variaciones y estacionalidad. "),
                "Las variaciones contra el mes anterior se muestran solo para series desestacionalizadas. "
                "En las series originales (aperturas del EMAE, exportaciones, cuentas fiscales base caja) "
                "se informa la variación interanual, que no está afectada por la estacionalidad.",
            ], className="method-note"),
            html.Li([
                html.Strong("Fuentes y tolerancia a fallos. "),
                "Los datos se combinan en paralelo desde APIs oficiales (", C("datos.gob.ar"),
                ", con las distribuciones CSV del catálogo SSPM, y ", C("api.bcra.gob.ar/estadisticas/v4.0"),
                "), APIs de mercado (Bluelytics y DolarAPI), planillas oficiales leídas en memoria (",
                C("ITCRMSerie.xlsx"), " del BCRA y la planilla de capacidad instalada del INDEC) y la lectura "
                "web de Ámbito y Rava para el riesgo país. Todo queda en una caché Parquet: si una fuente "
                "falla, se usa el último dato guardado.",
            ], className="method-note"),
        ],
        className="method-notes",
    )

    export_bar = html.Div(
        [
            html.Div(
                [
                    html.Strong("Paneles consolidados: "),
                    html.Span(
                        f"Panel mensual ({len(data.df)} filas × {len(data.df.columns)} columnas) · "
                        f"Panel diario ({len(data.daily_df)} filas × {len(data.daily_df.columns)} columnas) · "
                        f"Última actualización {fmt_ago(data.fetched_at)}.",
                        className="muted",
                    ),
                ],
                className="export-text",
            ),
            html.Div(
                [
                    html.Button("⬇ Panel mensual (CSV)", id="btn-download-monthly", n_clicks=0, className="btn"),
                    html.Button("⬇ Panel diario (CSV)", id="btn-download-daily", n_clicks=0, className="btn"),
                    dcc.Download(id="download-monthly-csv"),
                    dcc.Download(id="download-daily-csv"),
                ],
                className="export-actions",
            ),
        ],
        className="export-bar",
    )

    headers = ["Serie", "Grupo", "Proveedor", "ID en la fuente", "Frecuencia", "Unidad", "Estado", "Obs.",
               "Último dato", ""]
    table = html.Div(
        [
            html.Div(
                [html.Label("Filtrar el catálogo", htmlFor="catalog-filter", className="sr-only"),
                 # El filtro corre en assets/ui.js: no hay callback y el valor no viaja al servidor
                 dcc.Input(id="catalog-filter", type="search", className="catalog-filter", autoComplete="off",
                           placeholder="Filtrar por nombre, grupo, proveedor, ID o estado…", debounce=True),
                 html.Span(f"{len(rows)} series", className="catalog-count", **{"aria-live": "polite"})],
                className="catalog-tools",
            ),
            html.Div(
                html.Table(
                    [
                        html.Thead(html.Tr([
                            html.Th(html.Button(h, type="button", className="sort-btn",
                                                **{"data-col": str(i)}) if h else h,
                                    **({"aria-sort": "none"} if h else {}))
                            for i, h in enumerate(headers)
                        ])),
                        html.Tbody(rows),
                    ],
                    className="status-table catalog-table",
                ),
                className="table-scroll",
            ),
        ],
        className="catalog",
    )

    return html.Div(
        [
            html.Section(
                [html.H2("Catálogo de datos, fuentes y metodología", className="section-title"),
                 html.Span(f"Auditoría en vivo de las {data.n_total} series configuradas y notas metodológicas",
                           className="section-hint")],
                className="section-head",
            ),
            _provider_summary_cards(data),
            card(export_bar, "Descarga de datos (CSV)"),
            card(methodology_notes, "Notas metodológicas y transformaciones"),
            card(table, f"Catálogo de series ({data.n_ok}/{data.n_total} operativas)",
                 "Clic en un encabezado para ordenar. Pasá el mouse sobre una fila para ver la descripción "
                 "oficial; «Explorar» abre la serie en el Explorador."),
        ],
        className="view",
    )
