// Comportamientos de interfaz que no necesitan ir al servidor.
(function () {
  "use strict";

  // ------------------------------------------------------------------------
  // Panel de estado de los datos: se cierra al hacer clic fuera o con Esc
  // ------------------------------------------------------------------------
  function openPanels() {
    return document.querySelectorAll("details.status-details[open]");
  }
  document.addEventListener("click", function (ev) {
    openPanels().forEach(function (d) {
      if (!d.contains(ev.target)) d.removeAttribute("open");
    });
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Escape") return;
    openPanels().forEach(function (d) {
      d.removeAttribute("open");
      var s = d.querySelector("summary");
      if (s) s.focus();
    });
  });

  // ------------------------------------------------------------------------
  // Barra de herramientas de Plotly fuera del orden de tabulación
  // (cada gráfico agrega ~6 botones; con el teclado había que atravesar decenas)
  // ------------------------------------------------------------------------
  function untabModebars(root) {
    (root || document).querySelectorAll(".modebar-btn:not([tabindex='-1'])").forEach(function (b) {
      b.setAttribute("tabindex", "-1");
    });
  }
  new MutationObserver(function () { untabModebars(); })
    .observe(document.documentElement, { childList: true, subtree: true });

  // ------------------------------------------------------------------------
  // Exportación por gráfico: CSV con los datos y PNG con fondo claro
  // ------------------------------------------------------------------------
  var LIGHT = { bg: "#ffffff", text: "#1f2633", muted: "#4b5565", grid: "#e3e7ee", border: "#b8c0cc" };
  var COLORWAY = ["#2f6fd6", "#c98a00", "#2e9e48", "#d1453b", "#8a5cc7", "#1f8fb8", "#d9731f"];
  // Paleta oscura del tablero (ui/theme.py) -> equivalente legible sobre blanco
  var DARK_TO_LIGHT = {
    "#6ea8fe": "#2f6fd6", "#f2c14e": "#c98a00", "#56d364": "#2e9e48", "#ff7b72": "#d1453b",
    "#d2a8ff": "#8a5cc7", "#79c0ff": "#1f8fb8", "#ffa657": "#d9731f",
    "#3fb950": "#2e9e48", "#f85149": "#d1453b", "#8b94a5": "#6b7280", "#2a303c": "#b8c0cc",
  };
  function lightColor(c) {
    if (Array.isArray(c)) return c.map(lightColor);
    return typeof c === "string" && DARK_TO_LIGHT[c.toLowerCase()] ? DARK_TO_LIGHT[c.toLowerCase()] : c;
  }

  function slug(text) {
    return (text || "grafico").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "grafico";
  }
  function today() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function download(blob, filename) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  function cardParts(btn) {
    var card = btn.closest(".card");
    var gd = card && card.querySelector(".js-plotly-plot");
    var title = card && card.querySelector(".card-title");
    var footer = card && card.querySelector(".card-footer");
    return {
      gd: gd,
      title: title ? title.textContent.trim() : "Gráfico",
      footer: footer ? footer.textContent.trim() : "",
    };
  }
  function toArray(v) {
    if (v == null) return [];
    return Array.prototype.slice.call(v);
  }
  function csvCell(v) {
    if (v == null || (typeof v === "number" && isNaN(v))) return "";
    // hasta 6 decimales, sin ceros de relleno
    var s = typeof v === "number" ? String(Math.round(v * 1e6) / 1e6) : String(v);
    return /[",\n;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  function cleanDate(v) {
    // "2024-01-01T00:00:00" o "2024-01-01 00:00:00" -> "2024-01-01"
    return typeof v === "string" ? v.replace(/[T ]00:00:00(\.0+)?$/, "") : v;
  }

  function exportCsv(parts) {
    var traces = (parts.gd._fullData || []).filter(function (t) { return t.visible !== false && (t.x || t.y); });
    if (!traces.length) return;
    var horizontal = traces.every(function (t) { return t.orientation === "h"; });
    var keyAxis = horizontal ? "y" : "x";
    var valAxis = horizontal ? "x" : "y";
    var keys = [], index = {}, cols = [];
    traces.forEach(function (t, ti) {
      var raw = t[valAxis];
      // Las series largas viajan en float32: se redondean a 7 dígitos significativos para no
      // exportar ruido de precisión (1545.4000244 -> 1545.4)
      var f32 = typeof Float32Array !== "undefined" && raw instanceof Float32Array;
      var ks = toArray(t[keyAxis]).map(cleanDate);
      var vs = toArray(raw).map(function (v) {
        return (f32 && typeof v === "number" && isFinite(v)) ? Number(v.toPrecision(7)) : v;
      });
      var axTitle = (parts.gd._fullLayout[valAxis + "axis"] || {}).title;
      var generic = !t.name || /^(trace|traza) \d+$/i.test(t.name);
      cols.push(generic ? ((axTitle && axTitle.text) || parts.title || ("Serie " + (ti + 1))) : t.name);
      ks.forEach(function (k, i) {
        if (!(k in index)) { index[k] = keys.length; keys.push({ k: k, vals: [] }); }
        keys[index[k]].vals[ti] = vs[i];
      });
    });
    var head = [horizontal ? "Categoría" : "Fecha"].concat(cols).map(csvCell).join(",");
    var lines = keys.map(function (row) {
      return [row.k].concat(cols.map(function (_, ti) { return row.vals[ti]; })).map(csvCell).join(",");
    });
    // BOM para que Excel reconozca los acentos
    var blob = new Blob(["﻿" + [head].concat(lines).join("\n")], { type: "text/csv;charset=utf-8" });
    download(blob, slug(parts.title) + "_" + today() + ".csv");
  }

  function lightLayout(layout, parts) {
    var L = JSON.parse(JSON.stringify(layout || {}));
    delete L.template;
    L.paper_bgcolor = LIGHT.bg;
    L.plot_bgcolor = LIGHT.bg;
    L.separators = ",.";
    L.colorway = COLORWAY;
    L.font = { family: "Inter, 'Segoe UI', Roboto, Arial, sans-serif", size: 13, color: LIGHT.text };
    L.legend = Object.assign({}, L.legend || {}, {
      font: { color: LIGHT.text, size: 12 }, bgcolor: "rgba(0,0,0,0)",
      orientation: "h", yanchor: "bottom", y: 1.02, xanchor: "left", x: 0,
    });
    Object.keys(L).forEach(function (k) {
      if (!/^[xy]axis\d*$/.test(k)) return;
      var ax = L[k];
      ax.gridcolor = LIGHT.grid;
      ax.linecolor = LIGHT.border;
      ax.tickcolor = LIGHT.border;
      ax.zerolinecolor = LIGHT.border;
      ax.tickfont = Object.assign({}, ax.tickfont || {}, { color: LIGHT.muted });
      ax.automargin = true;
      if (ax.title) {
        ax.title = typeof ax.title === "string" ? { text: ax.title } : ax.title;
        ax.title.font = Object.assign({}, ax.title.font || {}, { color: LIGHT.muted });
      }
    });
    if (!L.xaxis) L.xaxis = {};
    if (!L.yaxis) L.yaxis = { gridcolor: LIGHT.grid, tickfont: { color: LIGHT.muted }, automargin: true };
    L.title = { text: "<b>" + parts.title + "</b>", x: 0.01, xanchor: "left", y: 0.97, font: { size: 17, color: LIGHT.text } };
    L.margin = { l: 60, r: 40, t: 110, b: 110 };
    // Fuente al pie, en píxeles desde el borde inferior del área de trazado (debajo de las fechas del eje)
    L.annotations = (L.annotations || []).concat([{
      text: (parts.footer ? parts.footer + " · " : "") + "Elaborado con EconomiApp",
      xref: "paper", yref: "paper", x: 0, y: 0, yshift: -62,
      xanchor: "left", yanchor: "top", showarrow: false, font: { size: 12, color: LIGHT.muted },
    }]);
    (L.shapes || []).forEach(function (s) { if (s.line) s.line.color = LIGHT.border; });
    return L;
  }

  function exportPng(parts, btn) {
    if (!window.Plotly) return;
    var data = (parts.gd.data || []).map(function (t) {
      var c = JSON.parse(JSON.stringify(t));
      if (c.line && c.line.color) c.line.color = lightColor(c.line.color);
      if (c.marker && c.marker.color) c.marker.color = lightColor(c.marker.color);
      c.textfont = Object.assign({}, c.textfont || {}, { color: LIGHT.text });
      return c;
    });
    var label = btn.textContent;
    btn.disabled = true;
    btn.textContent = "…";
    window.Plotly.toImage({ data: data, layout: lightLayout(parts.gd.layout, parts) },
      { format: "png", width: 1400, height: 720, scale: 2 })
      .then(function (url) { return fetch(url).then(function (r) { return r.blob(); }); })
      .then(function (blob) { download(blob, slug(parts.title) + "_" + today() + ".png"); })
      .catch(function (err) { console.error("No se pudo exportar el gráfico", err); })
      .then(function () { btn.disabled = false; btn.textContent = label; });
  }

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest && ev.target.closest(".chart-action");
    if (!btn) return;
    var parts = cardParts(btn);
    if (!parts.gd) return;
    if (btn.dataset.action === "csv") exportCsv(parts);
    if (btn.dataset.action === "png") exportPng(parts, btn);
  });
})();
