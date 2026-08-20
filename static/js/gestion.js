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

  function focusDialogControl() {
    const focusTarget = dialog.querySelector(
      ".errorlist + input, .errorlist + select, button[type='submit'], [data-dialog-close]"
    );
    if (focusTarget) focusTarget.focus();
  }

  async function loadFragment(url) {
    const response = await fetch(url, { headers: { "X-Requested-With": "fetch" } });
    if (!response.ok) throw new Error("No se pudo cargar el detalle.");
    dialog.innerHTML = await response.text();
    bindDialog();
    if (!dialog.open) dialog.showModal();
    focusDialogControl();
  }

  async function submitFragmentForm(form, submitter) {
    const data = new FormData(form);
    if (submitter && submitter.name) data.set(submitter.name, submitter.value);
    if (submitter && submitter.dataset.extraName) {
      data.set(submitter.dataset.extraName, submitter.dataset.extraValue);
    }
    const action = submitter && submitter.formAction ? submitter.formAction : form.action;
    const response = await fetch(action, {
      method: "POST",
      body: data,
      headers: { "X-Requested-With": "fetch" },
    });
    if (!response.ok) throw new Error("No se pudo guardar.");
    const previousId = dialog
      .querySelector("[data-current-row-id]")
      ?.getAttribute("data-current-row-id");
    dialog.innerHTML = await response.text();
    const fragmentRoot = dialog.querySelector("[data-fragment-kind]");
    const muestraSiguienteCaso =
      fragmentRoot?.dataset.fragmentKind === "selector-detail" &&
      fragmentRoot.dataset.currentRowId !== previousId;
    const muestraColaVacia = fragmentRoot?.dataset.fragmentKind === "selector-empty";
    if (muestraSiguienteCaso || muestraColaVacia) removeResolvedRow(previousId);
    bindDialog();
    focusDialogControl();
  }

  function bindDialog() {
    dialog.querySelectorAll("[data-dialog-close]").forEach((button) => {
      button.addEventListener("click", closeDialog);
    });
    dialog.querySelectorAll("[data-fragment-form]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        submitFragmentForm(form, event.submitter).catch(() => form.submit());
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
