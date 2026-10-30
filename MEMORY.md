# MEMORY.md - Memoria a Largo Plazo

## Proyecto: Dashboard de Variables Macroeconómicas Argentinas
- **Objetivo**: Desarrollar un dashboard interactivo que consuma y muestre variables macroeconómicas de la República Argentina a partir de la API oficial de Series de Tiempo (`datos.gob.ar`).
- **Estado**: Configuración de variables, pipeline de datos e interfaz gráfica completados.

## Aprendizajes y Resoluciones Técnicas

### 1. Consumo de la API y Alineación de Series
- Las llamadas a la API de series de tiempo utilizan la URL base `https://apis.datos.gob.ar/series/api/series` y el parámetro `ids` con los códigos alfanuméricos provistos en `config.json`.
- Para obtener todo el historial de las series, se agregó el parámetro `limit=5000` en la llamada a la API, evitando el truncamiento por defecto del endpoint.

### 2. Estructura de la Configuración y de la Pipeline
- Se centralizaron todas las series requeridas bajo un formato estructurado y autodescriptivo en `config.json`.
- En [pipeline.py](file:///home/facundo/antigravity/Dashboard%20Macro/pipeline.py), se implementó la función `get_macro_data()`, la cual realiza peticiones individuales por serie para optimizar la robustez ante fallas de red y realiza un `pd.merge(..., how="outer")` sobre la columna `Fecha`.
- Este proceso alinea y consolida series con distintos horizontes históricos de inicio (como el IPC que inicia en 2016 y Exportaciones que inician en 1992) preservando todos los datos disponibles y completando con `NaN` los períodos previos a la publicación de cada serie.

### 3. Interfaz del Dashboard (Streamlit & Plotly)
- En [app.py](file:///home/facundo/antigravity/Dashboard%20Macro/app.py), se desarrolló un dashboard web completo.
- **Robustez de Métricas**: Debido a los desfases de publicación de los distintos organismos (INDEC, BCRA, Hacienda), la última fila del dataset consolidado suele tener NaNs. Para solucionarlo, las tarjetas de métricas filtran los nulos de forma independiente para cada indicador antes de extraer el último dato reportado y su respectiva variación intermensual (MoM) o intermensual en puntos porcentuales (pp), mostrando siempre la fecha correspondiente al valor visualizado.
- **Visualizaciones**:
  - *Actividad (EMAE)*: Comparación entre la serie Original y la Desestacionalizada en un solo gráfico de líneas.
  - *Inflación (IPC)*: Opción interactiva mediante botones de selección para graficar el Número Índice o la Tasa de Variación Mensual.
  - *Sector Externo (ICA)*: Comparación temporal entre Exportaciones FOB e Importaciones CIF, incluyendo un área de sombreado que representa la evolución del Saldo Comercial (Balanza Comercial).
  - *Tasas*: Curva de la Tasa BADLAR promedio mensual.
  - *Sector Fiscal*: Comparación entre el Gasto Público Primario y el Gasto Público Total.
- **Estética**: Se integraron estilos CSS en Streamlit para definir contenedores con sombras suaves y una tipografía homogénea para lograr un acabado profesional y pulido.
