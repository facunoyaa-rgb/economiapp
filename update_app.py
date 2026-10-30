import re

file_path = "/home/facundo/antigravity/Dashboard_Macro/app.py"
with open(file_path, "r") as f:
    content = f.read()

# CSS changes
old_css = """        /* Tipografía y fondos generales */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }
        
        /* Título del Dashboard con degradado */
        .title-container {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            padding: 2rem;
            border-radius: 12px;
            color: white;
            margin-bottom: 2rem;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        .title-container h1 {
            margin: 0;
            font-weight: 700;
            font-size: 2.5rem;
            letter-spacing: -0.5px;
        }
        .title-container p {
            margin: 0.5rem 0 0 0;
            font-weight: 300;
            opacity: 0.9;
        }
        
        /* Contenedores de métricas personalizados */
        div[data-testid="stMetric"] {
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            padding: 0.8rem 0.6rem;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
            transition: all 0.3s ease;
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.05);
            border-color: #cbd5e1;
        }
        /* Forzar color de texto oscuro para legibilidad en fondo claro de tarjeta */
        div[data-testid="stMetric"] [data-testid="stMetricLabel"],
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] * {
            color: #475569 !important;
            font-size: 0.78rem !important;
            white-space: normal !important;
            line-height: 1.25 !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"],
        div[data-testid="stMetric"] [data-testid="stMetricValue"] * {
            color: #0f172a !important;
            font-size: 1.35rem !important;
            line-height: 1.15 !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricDelta"],
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] * {
            font-size: 0.78rem !important;
        }"""

new_css = """        /* Tipografía M3 */
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
        }"""

content = content.replace(old_css, new_css)

# Update layout for charts function
layout_old = """    fig_%s.update_layout(
        template="plotly_white",
        margin=dict(l=40, r=40, t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(gridcolor="#e2e8f0"),
        yaxis=dict(title="%s", gridcolor="#e2e8f0")
    )"""

def m3_layout(title=""):
    return f"""    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor="#1a1c22",
        paper_bgcolor="#1a1c22",
        font=dict(color="#c3c6cf", family="Roboto"),
        margin=dict(l=40, r=40, t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#e2e2e9")),
        xaxis=dict(showgrid=False, color="#c3c6cf", linecolor="#43474e"),
        yaxis=dict(title="{title}", showgrid=True, gridcolor="#33373e", color="#c3c6cf", linecolor="#43474e", nticks=4)
    )"""

# Regular expressions for chart modifications
import re

# We will just replace everything manually for better precision
content = re.sub(
    r"template=\"plotly_white\",\s*margin=dict\([^)]+\),\s*legend=dict\([^)]+\),\s*xaxis=dict\(gridcolor=\"#[a-f0-9]+\"\),\s*yaxis=dict\(title=\"([^\"]+)\",\s*gridcolor=\"#[a-f0-9]+\"\)",
    lambda m: f'''template="plotly_dark",
        plot_bgcolor="#1a1c22",
        paper_bgcolor="#1a1c22",
        font=dict(color="#c3c6cf", family="Roboto"),
        margin=dict(l=40, r=40, t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#e2e2e9")),
        xaxis=dict(showgrid=False, color="#c3c6cf", linecolor="#43474e"),
        yaxis=dict(title="{m.group(1)}", showgrid=True, gridcolor="#33373e", color="#c3c6cf", linecolor="#43474e", nticks=4)''',
    content
)

# For the complex subplot (fig_cred_sal)
content = re.sub(
    r"template=\"plotly_white\",\s*margin=dict\([^)]+\),\s*legend=dict\([^)]+\),\s*xaxis=dict\(gridcolor=\"#[a-f0-9]+\"\)",
    '''template="plotly_dark",
        plot_bgcolor="#1a1c22",
        paper_bgcolor="#1a1c22",
        font=dict(color="#c3c6cf", family="Roboto"),
        margin=dict(l=40, r=40, t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#e2e2e9")),
        xaxis=dict(showgrid=False, color="#c3c6cf", linecolor="#43474e")''',
    content
)
# update_yaxes gridcolor
content = content.replace('secondary_y=False, gridcolor="#e2e8f0"', 'secondary_y=False, showgrid=True, gridcolor="#33373e", color="#c3c6cf", linecolor="#43474e", nticks=4')
content = content.replace('secondary_y=True)', 'secondary_y=True, showgrid=False, color="#c3c6cf", linecolor="#43474e")')

# Chart Line colors and widths and shape
# Line 1: EMAE Original (color='#7bc0e3', width=1.5) -> color='#a8c7fa', width=2, shape='spline'
content = content.replace("color='#7bc0e3', width=1.5", "color='#c4eed0', width=2, shape='spline'")
# Line 2: EMAE Desest (color='#005f73', width=2.5) -> color='#a8c7fa', width=2.5, shape='spline'
content = content.replace("color='#005f73', width=2.5", "color='#a8c7fa', width=2.5, shape='spline'")

# Line 3: TNA (color='#e9d8a6', width=2.5)
content = content.replace("color='#e9d8a6', width=2.5", "color='#ffdca8', width=2.5, shape='spline'")
# Line 4: Tasa Real (color='#d90429', width=2)
content = content.replace("color='#d90429', width=2", "color='#ffb4ab', width=2, shape='spline'")

# Line 5: IPC Tasa (color='#9b5de5', width=2)
content = content.replace("color='#9b5de5', width=2", "color='#a8c7fa', width=2.5, shape='spline'")
# Line 6: IPC Nivel General (color='#560bad', width=2.5)
content = content.replace("color='#560bad', width=2.5", "color='#ffdca8', width=2.5, shape='spline'")

# Line 7: Expo (color='#2a9d8f', width=2)
content = content.replace("color='#2a9d8f', width=2", "color='#c4eed0', width=2.5, shape='spline'")
# Line 8: Impo (color='#e76f51', width=2)
content = content.replace("color='#e76f51', width=2", "color='#ffb4ab', width=2.5, shape='spline'")
# Line 9: Saldo Comercial (color='#4a4e69', width=1.5, dash='dot')
content = content.replace("color='#4a4e69', width=1.5, dash='dot'", "color='#a8c7fa', width=2, shape='spline', dash='dot'")
content = content.replace("rgba(74, 78, 105, 0.1)", "rgba(168, 199, 250, 0.1)")

# Line 10: Gasto Primario (color='#f4a261', width=2.5)
content = content.replace("color='#f4a261', width=2.5", "color='#ffdca8', width=2.5, shape='spline'")
# Line 11: Gasto Total (color='#e76f51', width=1.5, dash='dash')
content = content.replace("color='#e76f51', width=1.5, dash='dash'", "color='#ffb4ab', width=2, dash='dash', shape='spline'")

# Line 12: Credito (color='#1d3557', width=2.5)
content = content.replace("color='#1d3557', width=2.5", "color='#a8c7fa', width=2.5, shape='spline'")
# Line 13: Salario (color='#457b9d', width=2, dash='dot')
content = content.replace("color='#457b9d', width=2, dash='dot'", "color='#c4eed0', width=2.5, dash='dot', shape='spline'")

with open(file_path, "w") as f:
    f.write(content)
print("Updated app.py successfully")
