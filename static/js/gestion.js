(function () {
  "use strict";

  document.documentElement.classList.add("js");

  const dialog = document.createElement("dialog");
  dialog.className = "gestion-dialog";
  dialog.setAttribute("aria-label", "Detalle de solicitud");
  document.body.appendChild(dialog);

  let lastTrigger = null;
  let dialogRequestInFlight = false;
  let dialogActionsCount = 0;

  function currentSelectorSection() {
    return document.querySelector("[data-selector-table-region]")?.dataset.selectorSection || "pendientes";
  }

  function selectorFragmentUrl() {
    const url = new URL(window.location.href);
    url.searchParams.set("fragmento", "1");
    url.searchParams.set("seccion", currentSelectorSection());
    return url.toString();
  }

  async function refreshSelectorTable() {
    const region = document.querySelector("[data-selector-table-region]");
    if (!region) return;
    const response = await fetch(selectorFragmentUrl(), {
      headers: { "X-Requested-With": "fetch" },
    });
    const html = await response.text();
    const fragment = extractFragmentOrNavigate(response, html);
    if (!fragment) return;
    if (fragment.dataset.fragmentKind !== "selector-table") return;
    region.replaceWith(fragment);
    document.querySelector("[data-gestion-list]")?.scrollIntoView({ block: "start" });
  }

  function extractFragmentOrNavigate(response, html) {
    if (response.redirected) {
      window.location.href = response.url;
      return null;
    }
    const template = document.createElement("template");
    template.innerHTML = html.trim();
    const fragment = template.content.querySelector("[data-fragment-kind]");
    if (!fragment) {
      window.location.href = response.url || window.location.href;
      return null;
    }
    return fragment;
  }

  function replaceDialogWithFragment(response, html) {
    const fragment = extractFragmentOrNavigate(response, html);
    if (!fragment) return false;
    dialog.replaceChildren(fragment);
    bindDialog();
    if (!dialog.open) dialog.showModal();
    focusDialogContent();
    return true;
  }

  function closeDialog() {
    dialog.close();
  }

  function removeResolvedCommunicatorRow(fragment, currentId) {
    if (
      fragment?.dataset.fragmentKind !== "comunicador-confirmation" ||
      fragment.dataset.caseResolved !== "true" ||
      !currentId
    ) return;
    document.querySelector(`[data-row-id="${currentId}"]`)?.remove();
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

  async function loadFragment(url) {
    const response = await fetch(url, { headers: { "X-Requested-With": "fetch" } });
    if (!response.ok) throw new Error("No se pudo cargar el detalle.");
    replaceDialogWithFragment(response, await response.text());
  }

  async function submitFragmentForm(form, submitter) {
    if (dialogRequestInFlight) return;
    dialogRequestInFlight = true;
    const currentId = dialog.querySelector("[data-current-row-id]")?.dataset.currentRowId;
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
      const html = await response.text();
      if (replaceDialogWithFragment(response, html)) {
        removeResolvedCommunicatorRow(
          dialog.querySelector('[data-fragment-kind="comunicador-confirmation"]'),
          currentId
        );
        dialogActionsCount += 1;
      }
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
    const shouldRefreshSelector = dialogActionsCount > 0 && document.querySelector("[data-selector-table-region]");
    dialog.innerHTML = "";
    dialogActionsCount = 0;
    if (lastTrigger) lastTrigger.focus();
    if (shouldRefreshSelector) {
      refreshSelectorTable().catch(() => window.location.reload());
    }
  });
})();
