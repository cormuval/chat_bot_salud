(function () {
  "use strict";

  document.documentElement.classList.add("js");

  const dialog = document.createElement("dialog");
  dialog.className = "gestion-dialog";
  dialog.setAttribute("aria-label", "Detalle de solicitud");
  document.body.appendChild(dialog);

  let lastTrigger = null;
  let dialogRequestInFlight = false;

  function closeDialog() {
    dialog.close();
    dialog.innerHTML = "";
    if (lastTrigger) lastTrigger.focus();
  }

  function removeResolvedRow(currentId) {
    if (!currentId) return;
    const row = document.querySelector(`[data-row-id="${currentId}"]`);
    if (row) row.remove();
  }

  function focusDialogContent() {
    const focusTarget = dialog.querySelector(
      "[data-dialog-error-focus], [data-dialog-focus]"
    );
    if (focusTarget) focusTarget.focus();
  }

  function setDialogButtonsDisabled(disabled) {
    dialog.querySelectorAll("[data-fragment-form] button").forEach((button) => {
      button.disabled = disabled;
    });
  }

  function mostrarErrorDeEnvio() {
    let status = dialog.querySelector("[data-dialog-status]");
    if (!status) {
      status = document.createElement("p");
      status.className = "danger-text";
      status.setAttribute("role", "alert");
      status.setAttribute("data-dialog-status", "");
      status.tabIndex = -1;
      dialog.querySelector(".modal-header")?.after(status);
    }
    status.textContent = "No se pudo guardar. Intente nuevamente.";
    status.focus();
  }

  function ajustarContadorSelector(seccion, diferencia) {
    if (!seccion || !diferencia) return;
    const counter = document.querySelector(`[data-selector-counter="${seccion}"]`);
    if (!counter) return;
    const actual = Number.parseInt(counter.textContent, 10);
    if (Number.isFinite(actual)) {
      counter.textContent = String(Math.max(0, actual + diferencia));
    }
  }

  function actualizarContadoresSelector(fragmentRoot) {
    const origen = fragmentRoot?.dataset.selectorSourceSection;
    const destino = fragmentRoot?.dataset.selectorDestinationSection;
    if (!origen || !destino) return;
    ajustarContadorSelector(origen, -1);
    if (destino !== origen) ajustarContadorSelector(destino, 1);
  }

  function actualizarFilaConservada(currentId, fragmentRoot) {
    if (!currentId) return;
    const row = document.querySelector(`[data-row-id="${currentId}"]`);
    const correction = row?.querySelector("[data-selector-correction]");
    if (!correction || !fragmentRoot?.dataset.selectorCorrectionText) return;
    correction.textContent = fragmentRoot.dataset.selectorCorrectionText;
  }

  async function loadFragment(url) {
    const response = await fetch(url, { headers: { "X-Requested-With": "fetch" } });
    if (!response.ok) throw new Error("No se pudo cargar el detalle.");
    dialog.innerHTML = await response.text();
    bindDialog();
    if (!dialog.open) dialog.showModal();
    focusDialogContent();
  }

  async function submitFragmentForm(form, submitter) {
    if (dialogRequestInFlight) return;
    dialogRequestInFlight = true;
    const previousId = dialog
      .querySelector("[data-current-row-id]")
      ?.getAttribute("data-current-row-id");
    setDialogButtonsDisabled(true);
    const data = new FormData(form);
    if (submitter && submitter.name) data.set(submitter.name, submitter.value);
    const action = submitter && submitter.formAction ? submitter.formAction : form.action;
    try {
      const response = await fetch(action, {
        method: "POST",
        body: data,
        headers: { "X-Requested-With": "fetch" },
      });
      if (!response.ok) {
        throw new Error("No se pudo guardar.");
      }
      dialog.innerHTML = await response.text();
      const confirmation = dialog.querySelector('[data-fragment-kind="comunicador-confirmation"]');
      if (confirmation?.dataset.caseResolved === "true" && previousId) removeResolvedRow(previousId);
      const fragmentRoot = dialog.querySelector("[data-fragment-kind]");
      if (fragmentRoot?.dataset.selectorRowAction === "remove") {
        removeResolvedRow(previousId);
        actualizarContadoresSelector(fragmentRoot);
      } else if (fragmentRoot?.dataset.selectorRowAction === "keep") {
        actualizarFilaConservada(previousId, fragmentRoot);
      }
      bindDialog();
      focusDialogContent();
    } finally {
      dialogRequestInFlight = false;
    }
  }

  function bindDialog() {
    dialog.querySelectorAll("[data-dialog-close]").forEach((button) => {
      button.addEventListener("click", closeDialog);
    });
    dialog.querySelectorAll("[data-fragment-form]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        submitFragmentForm(form, event.submitter).catch(() => {
          setDialogButtonsDisabled(false);
          mostrarErrorDeEnvio();
        });
      });
    });
  }

  document.addEventListener("click", (event) => {
    const close = event.target.closest("[data-dialog-close]");
    if (close) {
      closeDialog();
      return;
    }
    const row = event.target.closest("[data-detail-url]");
    if (!row || event.target.closest("a, button, input, select, textarea")) return;
    event.preventDefault();
    lastTrigger = row;
    loadFragment(row.dataset.detailUrl).catch(() => {
      window.location.href = row.querySelector("a[href]").href;
    });
  });

  dialog.addEventListener("close", () => {
    if (lastTrigger) lastTrigger.focus();
  });
})();
