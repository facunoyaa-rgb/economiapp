"""Nombres legibles, unidades, grupo y tipo de cada columna de los paneles.

Lo usan el Explorador y el catálogo de la pestaña Datos. `kind` define qué transformaciones tienen sentido:

- "rate":  la serie ya es un porcentaje o una tasa. Las variaciones se expresan como diferencia en puntos
           porcentuales (p.p.) y no se puede llevar a base 100.
- "flow":  flujo mensual (exportaciones, recaudación, resultado fiscal). Admite la suma móvil de 12 meses.
- "level": índice, precio o stock. Variaciones porcentuales y base 100.
"""
from __future__ import annotations

from dataclasses import dataclass

ACT, PRE, TAS, CAM, EXT, FIS, DIN, SAL = (
    "Actividad", "Precios", "Tasas", "Tipo de cambio", "Sector externo", "Fiscal",
    "Dinero y crédito", "Salarios, empleo y pobreza",
)

IDX = "Índice"
PCT = "%"
TNA = "TNA %"
MARS = "Millones de $"
MUSD = "Millones de US$"
ARSUSD = "$ por US$"
REAL = "Millones de $ constantes"


@dataclass(frozen=True)
class SeriesMeta:
    label: str
    unit: str
    group: str
    kind: str = "level"   # "level" | "flow" | "rate"


def _m(label, unit, group, kind="level") -> SeriesMeta:
    return SeriesMeta(label, unit, group, kind)


META: dict[str, SeriesMeta] = {
    # Actividad
    "EMAE_Original": _m("EMAE (original)", IDX, ACT),
    "EMAE_Desestacionalizado": _m("EMAE (desestacionalizado)", IDX, ACT),
    "EMAE_Tendencia_Ciclo": _m("EMAE (tendencia-ciclo)", IDX, ACT),
    "EMAE_Agro": _m("EMAE: agro", IDX, ACT),
    "EMAE_Industria": _m("EMAE: industria manufacturera", IDX, ACT),
    "EMAE_Construccion": _m("EMAE: construcción", IDX, ACT),
    "EMAE_Comercio": _m("EMAE: comercio", IDX, ACT),
    "EMAE_Minas_Canteras": _m("EMAE: minas y canteras", IDX, ACT),
    "EMAE_Financiero": _m("EMAE: intermediación financiera", IDX, ACT),
    "IPI_Manufacturero": _m("IPI manufacturero (original)", IDX, ACT),
    "IPI_Desestacionalizado": _m("IPI manufacturero (desestacionalizado)", IDX, ACT),
    "ISAC_General": _m("ISAC construcción (original)", IDX, ACT),
    "ISAC_Desestacionalizado": _m("ISAC construcción (desestacionalizado)", IDX, ACT),
    "Supermercados_Constantes": _m("Ventas en supermercados (constantes, desest.)", "Millones de $ constantes", ACT),
    "UCI_Industria": _m("Uso de la capacidad instalada (industria)", PCT, ACT, "rate"),
    # Precios
    "IPC_Nivel_General": _m("IPC nivel general", IDX, PRE),
    "IPC_Nucleo": _m("IPC núcleo", IDX, PRE),
    "IPC_Regulados": _m("IPC regulados", IDX, PRE),
    "IPC_Estacionales": _m("IPC estacionales", IDX, PRE),
    "IPIM_Nivel_General": _m("IPIM (precios mayoristas)", IDX, PRE),
    "Inflacion_Mensual_Pct": _m("Inflación mensual", PCT, PRE, "rate"),
    "Inflacion_Interanual_Pct": _m("Inflación interanual", PCT, PRE, "rate"),
    "IPC_Nucleo_Mensual_Pct": _m("Inflación núcleo mensual", PCT, PRE, "rate"),
    "IPC_Nucleo_Interanual_Pct": _m("Inflación núcleo interanual", PCT, PRE, "rate"),
    "IPC_Regulados_Mensual_Pct": _m("Inflación regulados mensual", PCT, PRE, "rate"),
    "IPC_Regulados_Interanual_Pct": _m("Inflación regulados interanual", PCT, PRE, "rate"),
    "IPC_Estacionales_Mensual_Pct": _m("Inflación estacionales mensual", PCT, PRE, "rate"),
    "IPC_Estacionales_Interanual_Pct": _m("Inflación estacionales interanual", PCT, PRE, "rate"),
    "IPIM_Mensual_Pct": _m("IPIM: variación mensual", PCT, PRE, "rate"),
    "IPIM_Interanual_Pct": _m("IPIM: variación interanual", PCT, PRE, "rate"),
    "REM_Inflacion_12m": _m("Inflación esperada a 12 meses (REM)", PCT, PRE, "rate"),
    "Expectativa_Inflacion_UTDT": _m("Inflación esperada a 12 meses (UTDT)", PCT, PRE, "rate"),
    "CER": _m("CER", IDX, PRE),
    "UVA": _m("UVA", "$", PRE),
    "UVI": _m("UVI", "$", PRE),
    "ICL": _m("ICL (alquileres)", IDX, PRE),
    # Tasas
    "Tasa_Interes_Nominal": _m("Tasa de plazo fijo 30-59 días", TNA, TAS, "rate"),
    "Tasa_BADLAR": _m("Tasa BADLAR bancos privados", TNA, TAS, "rate"),
    "Tasa_TAMAR": _m("Tasa TAMAR bancos privados", TNA, TAS, "rate"),
    "Tasa_Adelantos": _m("Tasa de adelantos en cuenta corriente", TNA, TAS, "rate"),
    "Tasa_Personales": _m("Tasa de préstamos personales", TNA, TAS, "rate"),
    "Tasa_Nominal_Mensual_Pct": _m("Tasa de plazo fijo efectiva mensual", PCT, TAS, "rate"),
    "Tasa_Interes_Real_Mensual_Exacta": _m("Tasa real mensual ex-post (Fisher)", PCT, TAS, "rate"),
    "Tasa_Interes_Real_Mensual_Aprox": _m("Tasa real mensual ex-post (aprox. lineal)", PCT, TAS, "rate"),
    "Tasa_Real_Anualizada_Pct": _m("Tasa real anualizada ex-post", PCT, TAS, "rate"),
    "Tasa_Real_ExAnte_Anual_Pct": _m("Tasa real anual ex-ante (REM)", PCT, TAS, "rate"),
    "Spread_TAMAR_BADLAR_pp": _m("Diferencial TAMAR − BADLAR", "p.p.", TAS, "rate"),
    # Tipo de cambio
    "TC_Mayorista": _m("Dólar mayorista (A3500)", ARSUSD, CAM),
    "TC_Minorista": _m("Dólar minorista", ARSUSD, CAM),
    "Dolar_Blue": _m("Dólar blue", ARSUSD, CAM),
    "TC_Mayorista_Real": _m("Dólar mayorista a precios constantes", "$ constantes por US$", CAM),
    "Dolar_Blue_Real": _m("Dólar blue a precios constantes", "$ constantes por US$", CAM),
    "Brecha_Cambiaria_Pct": _m("Brecha blue / mayorista", PCT, CAM, "rate"),
    "Crawling_Peg_Mensual_Pct": _m("Devaluación mensual del mayorista", PCT, CAM, "rate"),
    "ITCRM": _m("Tipo de cambio real multilateral (ITCRM)", IDX, CAM),
    "ITCRB_Brasil": _m("Tipo de cambio real con Brasil", IDX, CAM),
    "ITCRB_EEUU": _m("Tipo de cambio real con EE.UU.", IDX, CAM),
    # Sector externo
    "Exportaciones_FOB": _m("Exportaciones (FOB)", MUSD, EXT, "flow"),
    "Importaciones_CIF": _m("Importaciones (CIF)", MUSD, EXT, "flow"),
    "Saldo_Comercial": _m("Saldo comercial", MUSD, EXT, "flow"),
    "Expo_Productos_Primarios": _m("Exportaciones: productos primarios", MUSD, EXT, "flow"),
    "Expo_MOA": _m("Exportaciones: MOA", MUSD, EXT, "flow"),
    "Expo_MOI": _m("Exportaciones: MOI", MUSD, EXT, "flow"),
    "Expo_Combustibles_Energia": _m("Exportaciones: combustibles y energía", MUSD, EXT, "flow"),
    "Impo_Bienes_Capital": _m("Importaciones: bienes de capital", MUSD, EXT, "flow"),
    "Impo_Bienes_Intermedios": _m("Importaciones: bienes intermedios", MUSD, EXT, "flow"),
    "Impo_Combustibles": _m("Importaciones: combustibles", MUSD, EXT, "flow"),
    "Impo_Bienes_Consumo": _m("Importaciones: bienes de consumo", MUSD, EXT, "flow"),
    "Balanza_Energetica": _m("Balanza energética", MUSD, EXT, "flow"),
    "Reservas_BCRA": _m("Reservas brutas del BCRA", MUSD, EXT),
    "Riesgo_Pais": _m("Riesgo país (EMBI)", "pb", EXT),
    # Fiscal
    "Ingresos_Publicos_Totales": _m("Ingresos totales del SPN", MARS, FIS, "flow"),
    "Gasto_Publico_Primario": _m("Gasto primario del SPN", MARS, FIS, "flow"),
    "Gasto_Publico_Total": _m("Gasto total del SPN", MARS, FIS, "flow"),
    "Resultado_Primario_Base_Caja": _m("Resultado primario", MARS, FIS, "flow"),
    "Resultado_Financiero_Base_Caja": _m("Resultado financiero", MARS, FIS, "flow"),
    "Recaudacion_Total": _m("Recaudación total", MARS, FIS, "flow"),
    "Recaudacion_DGI": _m("Recaudación DGI", MARS, FIS, "flow"),
    "Recaudacion_DGA": _m("Recaudación DGA (aduana)", MARS, FIS, "flow"),
    "Recaudacion_Seg_Social": _m("Recaudación de la seguridad social", MARS, FIS, "flow"),
    "Ingresos_Publicos_Totales_Real": _m("Ingresos totales del SPN (real)", REAL, FIS, "flow"),
    "Gasto_Publico_Primario_Real": _m("Gasto primario del SPN (real)", REAL, FIS, "flow"),
    "Gasto_Publico_Total_Real": _m("Gasto total del SPN (real)", REAL, FIS, "flow"),
    "Resultado_Primario_Base_Caja_Real": _m("Resultado primario (real)", REAL, FIS, "flow"),
    "Resultado_Financiero_Base_Caja_Real": _m("Resultado financiero (real)", REAL, FIS, "flow"),
    "Intereses_Deuda_Real": _m("Intereses de la deuda (real)", REAL, FIS, "flow"),
    "Resultado_Primario_Real_12m": _m("Resultado primario acumulado 12 meses (real)", REAL, FIS),
    "Resultado_Financiero_Real_12m": _m("Resultado financiero acumulado 12 meses (real)", REAL, FIS),
    "Recaudacion_Total_Real": _m("Recaudación total (real)", REAL, FIS, "flow"),
    "Recaudacion_DGI_Real": _m("Recaudación DGI (real)", REAL, FIS, "flow"),
    "Recaudacion_DGA_Real": _m("Recaudación DGA (real)", REAL, FIS, "flow"),
    "Recaudacion_Seg_Social_Real": _m("Recaudación de la seguridad social (real)", REAL, FIS, "flow"),
    # Dinero y crédito
    "Base_Monetaria": _m("Base monetaria", MARS, DIN),
    "Circulacion_Monetaria": _m("Circulación monetaria", MARS, DIN),
    "Depositos_Privados_Pesos": _m("Depósitos en pesos", MARS, DIN),
    "Depositos_Plazo_Fijo": _m("Depósitos a plazo fijo", MARS, DIN),
    "Credito_Interno": _m("Préstamos al sector privado en pesos", MARS, DIN),
    "Base_Monetaria_Real": _m("Base monetaria (real)", REAL, DIN),
    "Circulacion_Monetaria_Real": _m("Circulación monetaria (real)", REAL, DIN),
    "Depositos_Privados_Pesos_Real": _m("Depósitos en pesos (real)", REAL, DIN),
    "Depositos_Plazo_Fijo_Real": _m("Depósitos a plazo fijo (real)", REAL, DIN),
    "Credito_Interno_Real": _m("Préstamos al sector privado en pesos (real)", REAL, DIN),
    "Ratio_Prestamos_Depositos_Pct": _m("Préstamos / depósitos", PCT, DIN, "rate"),
    "M2_Privado_Var_IA": _m("M2 privado: variación interanual", PCT, DIN, "rate"),
    # Salarios, empleo y pobreza
    "Salarios": _m("RIPTE", "$", SAL),
    "Salarios_Real": _m("RIPTE (real)", "$ constantes", SAL),
    "Indice_Salarios_Total": _m("Índice de salarios: total", IDX, SAL),
    "Indice_Salarios_Privado_Reg": _m("Índice de salarios: privado registrado", IDX, SAL),
    "Indice_Salarios_Publico": _m("Índice de salarios: público", IDX, SAL),
    "Indice_Salarios_No_Reg": _m("Índice de salarios: no registrado", IDX, SAL),
    "Indice_Salarios_Total_Real": _m("Índice de salarios: total (real)", IDX, SAL),
    "Indice_Salarios_Privado_Reg_Real": _m("Índice de salarios: privado registrado (real)", IDX, SAL),
    "Indice_Salarios_Publico_Real": _m("Índice de salarios: público (real)", IDX, SAL),
    "Indice_Salarios_No_Reg_Real": _m("Índice de salarios: no registrado (real)", IDX, SAL),
    "Canasta_Basica_Alimentaria": _m("Canasta básica alimentaria", "$", SAL),
    "Canasta_Basica_Total": _m("Canasta básica total", "$", SAL),
    "Ratio_Salario_CBT": _m("RIPTE / canasta básica total", "veces", SAL),
    "Tasa_Desocupacion": _m("Tasa de desocupación", PCT, SAL, "rate"),
    "Tasa_Empleo": _m("Tasa de empleo", PCT, SAL, "rate"),
    "Tasa_Actividad": _m("Tasa de actividad", PCT, SAL, "rate"),
    "Pobreza_Personas": _m("Pobreza (personas)", PCT, SAL, "rate"),
    "Pobreza_Hogares": _m("Pobreza (hogares)", PCT, SAL, "rate"),
}

# Columnas que no se ofrecen en el Explorador (duplican a otra en otra unidad)
HIDDEN = {"IPC_Variacion_Mensual"}

GROUP_ORDER = [ACT, PRE, TAS, CAM, EXT, FIS, DIN, SAL]


def meta(col: str) -> SeriesMeta:
    """Metadatos de una columna. Si falta en el diccionario, se arma uno a partir del nombre."""
    return META.get(col) or SeriesMeta(col.replace("_", " "), "", "Otras")


def label(col: str) -> str:
    return meta(col).label
