"""Paletas, templates de Plotly (oscuro y claro) y tema activo de cada pedido.

Las vistas arman las figuras con la paleta oscura (COLORS, SERIES). Si el usuario eligió el tema claro,
`chart_card` pasa cada figura por `themed_figure`, que cambia el template y traduce los colores
explícitos con DARK_TO_LIGHT. Así las vistas no necesitan saber qué tema está activo.

Los colores deben mantenerse sincronizados con las variables CSS de assets/style.css
(:root y :root[data-theme="light"]) y con DARK_TO_LIGHT de assets/ui.js (exportación PNG).
"""
from __future__ import annotations

import contextvars
import re

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

LIGHT_COLORS = {
    "bg": "#f5f7fa",
    "surface": "#ffffff",
    "surface_2": "#ffffff",
    "border": "#c9d0da",
    "grid": "#e6eaf0",
    "text": "#1f2633",
    "muted": "#5b6475",
    "accent": "#2f6fd6",
    "good": "#1f883d",
    "bad": "#cf222e",
    "neutral": "#5b6475",
}

# Paleta categórica para series (alto contraste sobre fondo oscuro) y su equivalente sobre fondo claro
SERIES = ["#6ea8fe", "#f2c14e", "#56d364", "#ff7b72", "#d2a8ff", "#79c0ff", "#ffa657"]
LIGHT_SERIES = ["#2f6fd6", "#b07a00", "#2e9e48", "#d1453b", "#8a5cc7", "#1f8fb8", "#d9731f"]

DARK_TO_LIGHT = {
    **{d: l for d, l in zip(SERIES, LIGHT_SERIES)},
    **{COLORS[k]: LIGHT_COLORS[k] for k in COLORS},
    "#ffffff": LIGHT_COLORS["text"],   # líneas de total en blanco
}

FONT = "Inter, 'Segoe UI', Roboto, system-ui, sans-serif"

TEMPLATE_NAME = "macro_dark"
LIGHT_TEMPLATE_NAME = "macro_light"
THEMES = ("dark", "light")


def _make_template(c: dict, series: list[str]) -> go.layout.Template:
    return go.layout.Template(
        layout=go.Layout(
            font=dict(family=FONT, color=c["text"], size=12),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            colorway=series,
            hovermode="x unified",
            hoverlabel=dict(bgcolor=c["surface_2"], bordercolor=c["border"], font=dict(color=c["text"])),
            margin=dict(l=8, r=8, t=8, b=8),
            legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                        font=dict(color=c["muted"], size=11), bgcolor="rgba(0,0,0,0)"),
            # automargin: Plotly reserva el espacio que necesitan las etiquetas y títulos de cada eje
            # (con margen fijo de 8 px quedaban recortadas fuera del gráfico).
            xaxis=dict(showgrid=False, linecolor=c["border"], tickcolor=c["border"],
                       tickfont=dict(color=c["muted"]), zeroline=False, ticks="outside", ticklen=4,
                       automargin=True),
            yaxis=dict(gridcolor=c["grid"], linecolor=c["border"], tickfont=dict(color=c["muted"]),
                       zeroline=True, zerolinecolor=c["border"], zerolinewidth=1, separatethousands=True,
                       title=dict(font=dict(color=c["muted"], size=11), standoff=8), automargin=True),
            separators=",.",  # decimal ',' y miles '.' (es-AR)
            bargap=0.25,
        ),
        data=dict(scatter=[go.Scatter(line=dict(width=2))]),
    )


pio.templates[TEMPLATE_NAME] = _make_template(COLORS, SERIES)
pio.templates[LIGHT_TEMPLATE_NAME] = _make_template(LIGHT_COLORS, LIGHT_SERIES)
pio.templates.default = TEMPLATE_NAME

GRAPH_CONFIG = {
    "displaylogo": False,
    # La imagen se exporta con el botón propio "PNG" de cada tarjeta (fondo claro para informes).
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines", "toImage"],
    "locale": "es",
}

# --------------------------------------------------------------------------- #
# Tema activo del pedido en curso
# --------------------------------------------------------------------------- #
# Cada callback corre en su propio hilo/contexto, así que el tema de un usuario no afecta a otro.
_CURRENT = contextvars.ContextVar("economiapp_theme", default="dark")


def set_theme(name: str | None) -> str:
    theme = name if name in THEMES else "dark"
    _CURRENT.set(theme)
    return theme


def current_theme() -> str:
    return _CURRENT.get()


def color(c: str) -> str:
    """Traduce un color de la paleta oscura al tema activo (para SVG y estilos fuera de Plotly)."""
    if current_theme() == "light" and isinstance(c, str):
        return DARK_TO_LIGHT.get(c.lower(), c)
    return c


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


_RGB_MAP = {_hex_to_rgb(d): _hex_to_rgb(l) for d, l in DARK_TO_LIGHT.items()}
_RGBA_RE = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(,\s*[\d.]+\s*)?\)")


def _light_str(s: str) -> str:
    low = s.lower()
    if low in DARK_TO_LIGHT:
        return DARK_TO_LIGHT[low]

    def sub(m: re.Match) -> str:
        rgb = tuple(int(m.group(i)) for i in (1, 2, 3))
        new = _RGB_MAP.get(rgb)
        if not new:
            return m.group(0)
        alpha = m.group(4)
        return f"rgba({new[0]}, {new[1]}, {new[2]}{alpha})" if alpha else f"rgb({new[0]}, {new[1]}, {new[2]})"

    return _RGBA_RE.sub(sub, s) if "rgb" in low else s


def _recolor(obj):
    if isinstance(obj, dict):
        return {k: _recolor(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_recolor(v) for v in obj]
    if isinstance(obj, str):
        return _light_str(obj)
    return obj  # números, arrays de numpy, etc.


_COLOR_KEYS = ("color", "fillcolor", "bgcolor", "bordercolor", "linecolor", "gridcolor", "tickcolor",
               "zerolinecolor", "line", "marker", "font", "tickfont", "title", "textfont", "hoverlabel",
               "legend", "shapes", "annotations", "colorway")


def _recolor_trace(t: dict) -> dict:
    # En las trazas solo se recorren las claves de estilo: x/y pueden ser listas largas de fechas o valores
    return {k: (_recolor(v) if k in _COLOR_KEYS else v) for k, v in t.items()}


def themed_figure(fig: go.Figure):
    """Figura lista para dcc.Graph en el tema activo (en el claro, un dict con colores traducidos)."""
    if current_theme() != "light":
        return fig
    d = fig.to_plotly_json()
    layout = {k: v for k, v in d.get("layout", {}).items() if k != "template"}
    layout = _recolor(layout)
    layout["template"] = pio.templates[LIGHT_TEMPLATE_NAME].to_plotly_json()
    return {"data": [_recolor_trace(t) for t in d.get("data", [])], "layout": layout}
