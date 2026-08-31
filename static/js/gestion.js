(function () {
  "use strict";

  document.documentElement.classList.add("js");

  // Navegacion por fila: un clic en cualquier parte de la fila abre la vista
  // completa del caso. Los enlaces y controles internos siguen su comportamiento
  // propio (el enlace "Abrir", el telefono, los botones deshabilitados).
  document.addEventListener("click", (event) => {
    const row = event.target.closest("[data-detail-url]");
    if (!row) return;
    if (event.target.closest("a, button, input, select, textarea, label")) return;
    window.location.href = row.dataset.detailUrl;
  });

  // WhatsApp: se abre en una pestana nueva sin perder el sistema en la actual.
  // La pestana se abre antes del fetch para conservar el gesto del usuario y no
  // caer en el bloqueador de popups. El POST registra el intento y devuelve la
  // URL de wa.me; luego se recarga la vista para que el historial quede al dia.
  let whatsappInFlight = false;

  document.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-whatsapp-form]");
    if (!form) return;
    event.preventDefault();
    if (whatsappInFlight) return;
    whatsappInFlight = true;

    const popup = window.open("", "_blank");
    if (popup) popup.opener = null;

    const separador = form.action.includes("?") ? "&" : "?";
    const action = form.action + separador + "fragmento=1";

    fetch(action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "fetch" },
    })
      .then((response) => response.text().then((html) => ({ response, html })))
      .then(({ response, html }) => {
        if (response.redirected) {
          if (popup) popup.close();
          window.location.href = response.url;
          return;
        }
        const plantilla = document.createElement("template");
        plantilla.innerHTML = html.trim();
        const fragmento = plantilla.content.querySelector("[data-fragment-kind]");
        const url = fragmento && fragmento.dataset.whatsappUrl;

        if (url && popup) {
          popup.location.href = url;
          window.location.reload();
          return;
        }
        if (url) {
          mostrarEnlaceManual(form, url);
          whatsappInFlight = false;
          return;
        }
        // Sin URL: telefono invalido o cuerpo rechazado. Se muestra el detalle
        // devuelto con sus errores, sin recargar para no perderlos.
        if (popup) popup.close();
        const actual = document.querySelector('[data-fragment-kind="comunicador-detail"]');
        if (fragmento && actual) {
          actual.replaceWith(fragmento);
        } else {
          window.location.reload();
        }
        whatsappInFlight = false;
      })
      .catch(() => {
        if (popup) popup.close();
        whatsappInFlight = false;
        form.submit();
      });
  });

  function mostrarEnlaceManual(form, url) {
    let aviso = form.querySelector("[data-whatsapp-manual]");
    if (!aviso) {
      aviso = document.createElement("p");
      aviso.className = "warning-text";
      aviso.setAttribute("data-whatsapp-manual", "");
      const enlace = document.createElement("a");
      enlace.target = "_blank";
      enlace.rel = "noopener";
      enlace.textContent = "Abrir WhatsApp";
      aviso.appendChild(enlace);
      form.prepend(aviso);
    }
    aviso.querySelector("a").href = url;
  }
})();
