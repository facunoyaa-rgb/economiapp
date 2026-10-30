"""Paleta de colores y template de Plotly para el tema oscuro del dashboard.

Los colores deben mantenerse sincronizados con las variables CSS de assets/style.css.
"""
import plotly.graph_objects as go
import plotly.io as pio

COLORS = {
    "bg": "#0e1117",
    "surface": "#161a22",
    "surface_2": "#1d222c",
    "border": "#2a303c",
    "grid": "#232935",
    "text": "#e6e9ef",
    "muted": "#8b94a5",
    "accent": "#6ea8fe",
    "good": "#3fb950",
    "bad": "#f85149",
    "neutral": "#8b94a5",
}

# Paleta categórica para series (alto contraste sobre fondo oscuro)
SERIES = ["#6ea8fe", "#f2c14e", "#56d364", "#ff7b72", "#d2a8ff", "#79c0ff", "#ffa657"]

FONT = "Inter, 'Segoe UI', Roboto, system-ui, sans-serif"

TEMPLATE_NAME = "macro_dark"

_template = go.layout.Template(
    layout=go.Layout(
        font=dict(family=FONT, color=COLORS["text"], size=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=SERIES,
        hovermode="x unified",
        hoverlabel=dict(bgcolor=COLORS["surface_2"], bordercolor=COLORS["border"], font=dict(color=COLORS["text"])),
        margin=dict(l=8, r=8, t=8, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                    font=dict(color=COLORS["muted"], size=11), bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=False, linecolor=COLORS["border"], tickcolor=COLORS["border"],
                   tickfont=dict(color=COLORS["muted"]), zeroline=False, ticks="outside", ticklen=4),
        yaxis=dict(gridcolor=COLORS["grid"], linecolor=COLORS["border"], tickfont=dict(color=COLORS["muted"]),
                   zeroline=True, zerolinecolor=COLORS["border"], zerolinewidth=1, separatethousands=True,
                   title=dict(font=dict(color=COLORS["muted"], size=11))),
        separators=",.",  # decimal ',' y miles '.' (es-AR)
        bargap=0.25,
    ),
    data=dict(
        scatter=[go.Scatter(line=dict(width=2))],
    ),
)

pio.templates[TEMPLATE_NAME] = _template
pio.templates.default = TEMPLATE_NAME

GRAPH_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"],
    "locale": "es",
}
