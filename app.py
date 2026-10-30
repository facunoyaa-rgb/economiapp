import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

# Importar la función de descarga de datos
from pipeline import get_macro_data

# Configuración de página de Streamlit
st.set_page_config(
    page_title="Dashboard Macro Argentina",
    page_icon="🇦🇷",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados para estética premium (Financial Terminal Look)
st.markdown("""
    <style>
        /* Tipografía M3 */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Roboto', sans-serif;
            background-color: #111318;
            color: #e2e2e9;
        }
        
        /* Fondo principal (App) y barra lateral */
        .stApp {
            background-color: #111318;
        }
        [data-testid="stSidebar"] {
            background-color: #1a1c22 !important;
            border-right: 1px solid #43474e !important;
        }

        /* Título del Dashboard */
        .title-container {
            background: #1a1c22;
            padding: 2rem;
            border-radius: 28px;
            color: #e2e2e9;
            margin-bottom: 2rem;
            border: 1px solid #43474e;
        }
        .title-container h1 {
            margin: 0;
            font-weight: 700;
            font-size: 2.5rem;
            letter-spacing: -0.5px;
            color: #e2e2e9;
        }
        .title-container p {
            margin: 0.5rem 0 0 0;
            font-weight: 400;
            color: #c3c6cf;
        }
        
        /* Contenedores de métricas (KPIs) - M3 */
        div[data-testid="stMetric"] {
            background-color: #1a1c22;
            border: 1px solid #43474e;
            padding: 1.2rem;
            border-radius: 28px;
            transition: all 0.3s ease;
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-2px);
            border-color: #e2e2e9;
        }
        
        /* Textos de métricas */
        div[data-testid="stMetric"] [data-testid="stMetricLabel"],
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] * {
            color: #c3c6cf !important;
            font-size: 0.85rem !important;
            white-space: normal !important;
            line-height: 1.25 !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"],
        div[data-testid="stMetric"] [data-testid="stMetricValue"] * {
            color: #e2e2e9 !important;
            font-size: 32px !important;
            font-weight: 700 !important;
            line-height: 1.15 !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricDelta"],
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] * {
            font-size: 0.85rem !important;
        }
        
        /* Quitar fondo al delta (variación) */
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] > div {
            background-color: transparent !important;
        }
        
        /* Bordes estilo píldora (100px) para inputs */
        .stButton > button,
        .stSelectbox div[data-baseweb="select"] > div,
        .stMultiSelect div[data-baseweb="select"] > div,
        .stSlider div[data-baseweb="slider"] {
            border-radius: 100px !important;
        }
    </style>
""", unsafe_allow_html=True)

# Encabezado principal
st.markdown("""
    <div class="title-container">
        <h1>🇦🇷 Dashboard Macroeconómico de Argentina</h1>
        <p>Monitoreo en tiempo real con datos de la API de Series de Tiempo de la República Argentina (datos.gob.ar)</p>
    </div>
""", unsafe_allow_html=True)

# Función de caché de datos para mejorar performance
@st.cache_data(ttl=3600)  # Expira en 1 hora
def load_data():
    return get_macro_data()

# Carga de datos
with st.spinner("Cargando y alineando series macroeconómicas..."):
    try:
        df_raw = load_data()
    except Exception as e:
        st.error(f"Error al cargar datos del pipeline: {e}")
        st.stop()

# Procesamiento del filtro de años en la barra lateral
st.sidebar.header("⚙️ Configuración del Dashboard")

min_year = int(df_raw["Fecha"].dt.year.min())
max_year = int(df_raw["Fecha"].dt.year.max())

st.sidebar.markdown("### Filtro Temporal")
year_range = st.sidebar.slider(
    "Selecciona el rango de años para los gráficos:",
    min_value=min_year,
    max_value=max_year,
    value=(2010, max_year),
    step=1
)

# Filtrar el DataFrame para visualizaciones
df_filtered = df_raw[(df_raw["Fecha"].dt.year >= year_range[0]) & (df_raw["Fecha"].dt.year <= year_range[1])].copy()

# Sidebar Información de metadatos
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Fuentes e Información")
st.sidebar.markdown(
    """
    Este panel de control consume directamente las series de tiempo del **INDEC**, **Banco Central (BCRA)** y la **Secretaría de Hacienda** a través del catálogo nacional de datos abiertos de la República Argentina.
    """
)
st.sidebar.info("Última actualización de la API del dashboard realizada con éxito.")

# Función auxiliar para calcular métricas globales y su variación mensual
def get_metric_stats(df, col_name, is_ratio=False, is_percentage_rate=False):
    if col_name not in df.columns:
        return "N/A", "N/A", "N/A"
    # Eliminar nulos para obtener el último dato real reportado
    clean_series = df[["Fecha", col_name]].dropna().sort_values(by="Fecha")
    if len(clean_series) < 2:
        return "N/A", "N/A", "N/A"
    
    latest_row = clean_series.iloc[-1]
    prev_row = clean_series.iloc[-2]
    
    latest_val = latest_row[col_name]
    prev_val = prev_row[col_name]
    latest_date = latest_row["Fecha"].strftime("%m/%Y")
    
    if is_ratio:  # Para tasas expresadas en formato decimal (ej: IPC variación = 0.0258)
        val_str = f"{latest_val * 100:.2f}%"
        change = latest_val - prev_val
        change_str = f"{change * 100:+.2f} pp"
    elif is_percentage_rate:  # Para tasas expresadas en porcentaje (ej: Badlar = 46.16)
        val_str = f"{latest_val:.2f}%"
        change = latest_val - prev_val
        change_str = f"{change:+.2f} pp"
    else:  # Para índices o montos absolutos (EMAE, ICA, Gasto)
        if latest_val >= 1000:
            val_str = f"{latest_val:,.1f}"
        else:
            val_str = f"{latest_val:.2f}"
        
        pct_change = ((latest_val - prev_val) / prev_val) * 100
        change_str = f"{pct_change:+.2f}% MoM"
        
    return val_str, change_str, latest_date

# --- SECCIÓN DE AJUSTES IPC EN LA BARRA LATERAL ---
st.sidebar.markdown("---")
st.sidebar.markdown("### 🛠️ Ajuste por Inflación (IPC)")
usar_reales = st.sidebar.checkbox(
    "Ver variables en términos Reales",
    value=True,
    help="Si está activado, el Gasto Público, Crédito Interno y Salarios se mostrarán deflactados por IPC a pesos de hoy."
)

# --- SECCIÓN 1: TARJETAS DE MÉTRICAS (ÚLTIMOS DATOS DISPONIBLES) ---
st.markdown("### 📈 Indicadores Clave (Último Dato Reportado)")

# Computar métricas de las variables solicitadas
emae_val, emae_chg, emae_date = get_metric_stats(df_raw, "EMAE_Desestacionalizado")
ipc_val, ipc_chg, ipc_date = get_metric_stats(df_raw, "IPC_Variacion_Mensual", is_ratio=True)
tasa_nom_val, tasa_nom_chg, tasa_nom_date = get_metric_stats(df_raw, "Tasa_Interes_Nominal", is_percentage_rate=True)
tasa_real_val, tasa_real_chg, tasa_real_date = get_metric_stats(df_raw, "Tasa_Interes_Real_Mensual_Exacta", is_percentage_rate=True)

# Selección de Gasto, Crédito y Salarios (nominal vs real)
suffix = "_Real" if usar_reales else ""
label_prefix = "Real" if usar_reales else "Nominal"

gasto_val, gasto_chg, gasto_date = get_metric_stats(df_raw, f"Gasto_Publico_Primario{suffix}")
credito_val, credito_chg, credito_date = get_metric_stats(df_raw, f"Credito_Interno{suffix}")
salarios_val, salarios_chg, salarios_date = get_metric_stats(df_raw, f"Salarios{suffix}")

# Organizar en 8 columnas para ver todo a primera vista de manera compacta y premium
col1, col2, col3, col4, col5, col6, col7, col8 = st.columns(8)

with col1:
    st.metric(label=f"EMAE Desest. ({emae_date})", value=emae_val, delta=emae_chg)
with col2:
    st.metric(label=f"Inflación Mensual ({ipc_date})", value=ipc_val, delta=ipc_chg)
with col3:
    st.metric(label=f"Tasa Plazo Fijo TNA ({tasa_nom_date})", value=tasa_nom_val, delta=tasa_nom_chg)
with col4:
    st.metric(label=f"Tasa Real Mensual ({tasa_real_date})", value=tasa_real_val, delta=tasa_real_chg)
with col5:
    st.metric(label=f"Gasto Prim. {label_prefix} ({gasto_date})", value=f"$ {gasto_val}M", delta=gasto_chg)
with col6:
    st.metric(label=f"Crédito Priv. {label_prefix} ({credito_date})", value=f"$ {credito_val}M", delta=credito_chg)
with col7:
    st.metric(label=f"Salarios RIPTE {label_prefix} ({salarios_date})", value=f"$ {salarios_val}", delta=salarios_chg)
with col8:
    expos_val, expos_chg, expos_date = get_metric_stats(df_raw, "Exportaciones_FOB")
    st.metric(label=f"Exportaciones ({expos_date})", value=f"US$ {expos_val}M", delta=expos_chg)

st.markdown("---")

# --- SECCIÓN 2: GRÁFICOS INTERACTIVOS (PLOTLY) ---
st.markdown(f"### 📊 Análisis de Series Temporales ({year_range[0]} - {year_range[1]})")

# Fila 1: Actividad Económica y Tasas de Interés (Nominal y Real)
col_left, col_right = st.columns(2)

with col_left:
    st.markdown("#### Estimador Mensual de Actividad Económica (EMAE)")
    fig_emae = go.Figure()
    fig_emae.add_trace(go.Scatter(
        x=df_filtered["Fecha"], y=df_filtered["EMAE_Original"],
        mode='lines', name='EMAE Original', line=dict(color='#c4eed0', width=2, shape='spline')
    ))
    fig_emae.add_trace(go.Scatter(
        x=df_filtered["Fecha"], y=df_filtered["EMAE_Desestacionalizado"],
        mode='lines', name='EMAE Desestacionalizado', line=dict(color='#a8c7fa', width=2.5, shape='spline')
    ))
    fig_emae.update_layout(
        template="plotly_dark",
        plot_bgcolor="#1a1c22",
        paper_bgcolor="#1a1c22",
        font=dict(color="#c3c6cf", family="Roboto"),
        margin=dict(l=40, r=40, t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#e2e2e9")),
        xaxis=dict(showgrid=False, color="#c3c6cf", linecolor="#43474e"),
        yaxis=dict(title="Índice (2004=100)", showgrid=True, gridcolor="#33373e", color="#c3c6cf", linecolor="#43474e", nticks=4)
    )
    st.plotly_chart(fig_emae, use_container_width=True)

with col_right:
    st.markdown("#### Tasas de Interés del BCRA (Nominal Anual vs Real Mensual Fisher)")
    fig_tasas = go.Figure()
    fig_tasas.add_trace(go.Scatter(
        x=df_filtered["Fecha"], y=df_filtered["Tasa_Interes_Nominal"],
        mode='lines', name='TNA Plazo Fijo Nominal (%)', line=dict(color='#ffdca8', width=2.5, shape='spline')
    ))
    fig_tasas.add_trace(go.Scatter(
        x=df_filtered["Fecha"], y=df_filtered["Tasa_Interes_Real_Mensual_Exacta"],
        mode='lines', name='Tasa Real Mensual Fisher (%)', line=dict(color='#ffb4ab', width=2, shape='spline')
    ))
    fig_tasas.update_layout(
        template="plotly_dark",
        plot_bgcolor="#1a1c22",
        paper_bgcolor="#1a1c22",
        font=dict(color="#c3c6cf", family="Roboto"),
        margin=dict(l=40, r=40, t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#e2e2e9")),
        xaxis=dict(showgrid=False, color="#c3c6cf", linecolor="#43474e"),
        yaxis=dict(title="Porcentaje (%)", showgrid=True, gridcolor="#33373e", color="#c3c6cf", linecolor="#43474e", nticks=4)
    )
    st.plotly_chart(fig_tasas, use_container_width=True)

# Fila 2: Inflación e Intercambio Comercial
col_left_2, col_right_2 = st.columns(2)

with col_left_2:
    st.markdown("#### Inflación (Índice de Precios al Consumidor - IPC)")
    ipc_option = st.radio("Ver métrica del IPC:", ["Tasa de Variación Mensual (%)", "Número Índice (Base 2016=100)"], horizontal=True)
    
    fig_ipc = go.Figure()
    if "Tasa" in ipc_option:
        tasa_ipc_pct = df_filtered["IPC_Variacion_Mensual"] * 100
        fig_ipc.add_trace(go.Scatter(
            x=df_filtered["Fecha"], y=tasa_ipc_pct,
            mode='lines+markers', name='Inflación Mensual (%)', line=dict(color='#a8c7fa', width=2.5, shape='spline')
        ))
        yaxis_title = "Variación Mensual (%)"
    else:
        fig_ipc.add_trace(go.Scatter(
            x=df_filtered["Fecha"], y=df_filtered["IPC_Nivel_General"],
            mode='lines', name='IPC Nivel General', line=dict(color='#ffdca8', width=2.5, shape='spline')
        ))
        yaxis_title = "Índice"

    fig_ipc.update_layout(
        template="plotly_dark",
        plot_bgcolor="#1a1c22",
        paper_bgcolor="#1a1c22",
        font=dict(color="#c3c6cf", family="Roboto"),
        margin=dict(l=40, r=40, t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#e2e2e9")),
        xaxis=dict(showgrid=False, color="#c3c6cf", linecolor="#43474e"),
        yaxis=dict(title=yaxis_title, gridcolor="#e2e8f0")
    )
    st.plotly_chart(fig_ipc, use_container_width=True)

with col_right_2:
    st.markdown("#### Intercambio Comercial Argentino (ICA) y Balanza Comercial")
    fig_ica = go.Figure()
    fig_ica.add_trace(go.Scatter(
        x=df_filtered["Fecha"], y=df_filtered["Exportaciones_FOB"],
        mode='lines', name='Exportaciones (FOB)', line=dict(color='#c4eed0', width=2.5, shape='spline')
    ))
    fig_ica.add_trace(go.Scatter(
        x=df_filtered["Fecha"], y=df_filtered["Importaciones_CIF"],
        mode='lines', name='Importaciones (CIF)', line=dict(color='#ffb4ab', width=2.5, shape='spline')
    ))
    
    saldo_comercial = df_filtered["Exportaciones_FOB"] - df_filtered["Importaciones_CIF"]
    fig_ica.add_trace(go.Scatter(
        x=df_filtered["Fecha"], y=saldo_comercial,
        mode='lines', name='Saldo Comercial', line=dict(color='#a8c7fa', width=2, shape='spline', dash='dot'),
        fill='tozeroy', fillcolor='rgba(168, 199, 250, 0.1)'
    ))
    
    fig_ica.update_layout(
        template="plotly_dark",
        plot_bgcolor="#1a1c22",
        paper_bgcolor="#1a1c22",
        font=dict(color="#c3c6cf", family="Roboto"),
        margin=dict(l=40, r=40, t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#e2e2e9")),
        xaxis=dict(showgrid=False, color="#c3c6cf", linecolor="#43474e"),
        yaxis=dict(title="Millones de USD", showgrid=True, gridcolor="#33373e", color="#c3c6cf", linecolor="#43474e", nticks=4)
    )
    st.plotly_chart(fig_ica, use_container_width=True)

# Fila 3: Gasto Público y Crédito/Salarios
col_left_3, col_right_3 = st.columns(2)

with col_left_3:
    st.markdown(f"#### 🏛️ Sector Fiscal: Gasto Público Nacional ({label_prefix})")
    fig_gasto = go.Figure()
    
    # Calcular promedio móvil de 6 meses para el Gasto Primario
    ma_6m_primario = df_filtered[f"Gasto_Publico_Primario{suffix}"].rolling(window=6, min_periods=1).mean()

    fig_gasto.add_trace(go.Scatter(
        x=df_filtered["Fecha"], y=df_filtered[f"Gasto_Publico_Primario{suffix}"],
        mode='lines', name='Gasto Primario', line=dict(color='#ffdca8', width=2.5, shape='spline')
    ))
    fig_gasto.add_trace(go.Scatter(
        x=df_filtered["Fecha"], y=ma_6m_primario,
        mode='lines', name='Gasto Prim. (Tendencia 6M)', line=dict(color='#f4a261', width=2.5, dash='dot', shape='spline')
    ))
    fig_gasto.add_trace(go.Scatter(
        x=df_filtered["Fecha"], y=df_filtered[f"Gasto_Publico_Total{suffix}"],
        mode='lines', name='Gasto Total', line=dict(color='#ffb4ab', width=2, dash='dash', shape='spline')
    ))
    fig_gasto.update_layout(
        template="plotly_dark",
        plot_bgcolor="#1a1c22",
        paper_bgcolor="#1a1c22",
        font=dict(color="#c3c6cf", family="Roboto"),
        margin=dict(l=40, r=40, t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#e2e2e9")),
        xaxis=dict(showgrid=False, color="#c3c6cf", linecolor="#43474e"),
        yaxis=dict(title="Millones de pesos (ARS)", showgrid=True, gridcolor="#33373e", color="#c3c6cf", linecolor="#43474e", nticks=4)
    )
    st.plotly_chart(fig_gasto, use_container_width=True)

with col_right_3:
    st.markdown(f"#### 💰 Crédito Interno y Salarios RIPTE ({label_prefix})")
    fig_cred_sal = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Agregar Crédito Interno en el eje izquierdo
    fig_cred_sal.add_trace(go.Scatter(
        x=df_filtered["Fecha"], y=df_filtered[f"Credito_Interno{suffix}"],
        mode='lines', name='Crédito al Sector Privado (ARS)', line=dict(color='#a8c7fa', width=2.5, shape='spline')
    ), secondary_y=False)
    
    # Agregar Salarios en el eje derecho si está disponible
    salarios_col = f"Salarios{suffix}"
    if salarios_col in df_filtered.columns:
        fig_cred_sal.add_trace(go.Scatter(
            x=df_filtered["Fecha"], y=df_filtered[salarios_col],
            mode='lines', name='Salario RIPTE (Eje Der)', line=dict(color='#c4eed0', width=2.5, dash='dot', shape='spline')
        ), secondary_y=True)
    
    fig_cred_sal.update_layout(
        template="plotly_dark",
        plot_bgcolor="#1a1c22",
        paper_bgcolor="#1a1c22",
        font=dict(color="#c3c6cf", family="Roboto"),
        margin=dict(l=40, r=40, t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#e2e2e9")),
        xaxis=dict(showgrid=False, color="#c3c6cf", linecolor="#43474e")
    )
    fig_cred_sal.update_yaxes(title_text="Crédito (Millones ARS)", secondary_y=False, showgrid=True, gridcolor="#33373e", color="#c3c6cf", linecolor="#43474e", nticks=4)
    fig_cred_sal.update_yaxes(title_text="Salario RIPTE (ARS)", secondary_y=True, showgrid=False, color="#c3c6cf", linecolor="#43474e")
    
    st.plotly_chart(fig_cred_sal, use_container_width=True)
