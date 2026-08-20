(function () {
  "use strict";

  document.documentElement.classList.add("js");

  const dialog = document.createElement("dialog");
  dialog.className = "gestion-dialog";
  dialog.setAttribute("aria-label", "Detalle de solicitud");
  document.body.appendChild(dialog);

  let lastTrigger = null;

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
    const focusTarget = dialog.querySelector("[data-dialog-focus]");
    if (focusTarget) focusTarget.focus();
  }

  function setFormButtonsDisabled(form, disabled) {
    form.querySelectorAll("button").forEach((button) => {
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

  function decrementarContadorSelector() {
    const seccion = new URLSearchParams(window.location.search).get("seccion") || "pendientes";
    if (seccion !== "pendientes") return;
    const counter = document.querySelector(`[data-selector-counter="${seccion}"]`);
    if (!counter) return;
    const actual = Number.parseInt(counter.textContent, 10);
    if (Number.isFinite(actual)) counter.textContent = String(Math.max(0, actual - 1));
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
    setFormButtonsDisabled(form, true);
    const data = new FormData(form);
    if (submitter && submitter.name) data.set(submitter.name, submitter.value);
    const action = submitter && submitter.formAction ? submitter.formAction : form.action;
    const response = await fetch(action, {
      method: "POST",
      body: data,
      headers: { "X-Requested-With": "fetch" },
    });
    if (!response.ok) {
      throw new Error("No se pudo guardar.");
    }
    const previousId = dialog
      .querySelector("[data-current-row-id]")
      ?.getAttribute("data-current-row-id");
    dialog.innerHTML = await response.text();
    const confirmation = dialog.querySelector('[data-fragment-kind="comunicador-confirmation"]');
    if (confirmation?.dataset.caseResolved === "true" && previousId) removeResolvedRow(previousId);
    const fragmentRoot = dialog.querySelector("[data-fragment-kind]");
    const muestraSiguienteCaso =
      fragmentRoot?.dataset.fragmentKind === "selector-detail" &&
      fragmentRoot.dataset.currentRowId !== previousId;
    const muestraColaVacia = fragmentRoot?.dataset.fragmentKind === "selector-empty";
    if (muestraSiguienteCaso || muestraColaVacia) {
      removeResolvedRow(previousId);
      decrementarContadorSelector();
    }
    bindDialog();
    focusDialogContent();
  }

  function bindDialog() {
    dialog.querySelectorAll("[data-dialog-close]").forEach((button) => {
      button.addEventListener("click", closeDialog);
    });
    dialog.querySelectorAll("[data-fragment-form]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        submitFragmentForm(form, event.submitter).catch(() => {
          setFormButtonsDisabled(form, false);
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
