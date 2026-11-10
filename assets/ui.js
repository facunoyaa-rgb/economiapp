// Cierra el panel de estado de los datos al hacer clic fuera o al pulsar Esc.
(function () {
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
})();
