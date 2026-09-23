(function () {
  const root = document.querySelector(".saludbot");
  const messages = document.querySelector("#chatMessages");
  const form = document.querySelector("#chatForm");
  const input = document.querySelector("#chatInput");
  const submitButton = form.querySelector("button");
  const INACTIVITY_LIMIT_MS = 20 * 60 * 1000;
  const ADJUNTO_FOTO_HABILITADO = false;

  const centroInicial = root.dataset.centro || "Corporacion Municipal de Valparaiso";
  const userName = root.dataset.userName || "";
  const centrosSalud = [
    { id: "600", nombre: "Centro De Salud Familiar Laguna Verde" },
    { id: "605", nombre: "Centro De Salud Familiar Placilla (Valparaiso)" },
    { id: "610", nombre: "Centro De Salud Familiar Placeres" },
    { id: "615", nombre: "Centro De Salud Familiar Baron" },
    { id: "620", nombre: "Centro De Salud Familiar Rodelillo" },
    { id: "621", nombre: "Centro De Salud Familiar Padre Damian Molokai" },
    { id: "625", nombre: "Centro De Salud Familiar Quebrada Verde" },
    { id: "626", nombre: "Centro Comunitario De Salud Familiar Porvenir Bajo" },
    { id: "627", nombre: "Centro Comunitario De Salud Familiar Juan Pablo II" },
    { id: "630", nombre: "Centro De Salud Familiar Las Canas" },
    { id: "635", nombre: "Centro De Salud Familiar Mena" },
    { id: "640", nombre: "Centro De Salud Familiar Puertas Negras" },
    { id: "645", nombre: "Centro De Salud Familiar Cordillera" },
    { id: "650", nombre: "Centro De Salud Familiar Esperanza" },
    { id: "655", nombre: "Centro De Salud Familiar Reina Isabel II" },
  ];
  const condicionOpciones = [
    { id: "NEURODIVERGENTE", nombre: "Neurodivergente" },
    { id: "CUIDADOR_NEURODIVERGENTE", nombre: "Cuidador neurodivergente" },
    { id: "PRAIS", nombre: "PRAIS" },
    { id: "GESTANTE", nombre: "Gestante" },
    { id: "OTRO", nombre: "Otro" },
  ];

  const state = {
    index: 0,
    data: {},
    selectedCentroName: centroInicial,
    waiting: false,
    complete: false,
    submitting: false,
    esReceta: false,
  };

  const steps = [
    {
      field: "acepta_terminos",
      prompt: "Antes de continuar, debes aceptar los Terminos y Condiciones de uso de la plataforma.",
      type: "terms",
    },
    {
      field: "motivo",
      prompt: "¿Por qué problema de salud necesitas consultar hoy?",
      quick: true,
      validate: minLength("Describe el motivo de consulta con al menos 3 caracteres.", 3),
    },
    {
      field: "detalle_sintomas",
      prompt() {
        if (state.esReceta) {
          return "¿Qué medicamento(s) necesitas repetir? Indica el nombre y la dosis si la conoces.";
        }
        return `Gracias. Para ayudarte mejor, cuéntanos un poco más:
* ¿Qué síntomas tienes?
* ¿Cuándo comenzaron?
* ¿Han empeorado, mejorado o siguen igual?
* ¿Has recibido atención médica por este problema?`;
      },
      validate(value) {
        if (state.esReceta) {
          return value.trim().length >= 3
            ? null
            : "Indica el medicamento que necesitas repetir (al menos 3 caracteres).";
        }
        return value.trim().length >= 20
          ? null
          : "Describe tus sintomas con al menos 20 caracteres para orientar mejor la atencion.";
      },
    },
    {
      field: "centro_salud",
      prompt: "Selecciona el CESFAM donde quieres orientar esta solicitud.",
      options: centrosSalud,
      validate(value) {
        return centrosSalud.some((centro) => centro.id === value)
          ? null
          : "Selecciona una opcion de CESFAM de la lista.";
      },
      display(value) {
        return centrosSalud.find((centro) => centro.id === value)?.nombre || value;
      },
    },
    {
      field: "rut",
      prompt: "Para continuar, indícame el **RUT de la persona que requiere la atención**.\n**Ejemplo:** 12345678-9",
      validate(value) {
        return isValidRut(value)
          ? null
          : "El RUT ingresado no es valido. Usa el formato 12345678-9.";
      },
      transform: normalizeRutForStorage,
    },
    {
      field: "nombre",
      prompt: "Perfecto. Ahora indícame el nombre completo de la persona que necesita la atención.",
      validate: validateFullName,
      skip() {
        return Boolean(userName);
      },
      defaultValue() {
        return userName;
      },
    },
    {
      field: "edad",
      prompt: "Cual es tu edad?",
      validate(value) {
        const number = Number(value);
        return Number.isInteger(number) && number >= 0 && number <= 120
          ? null
          : "Ingresa una edad valida entre 0 y 120.";
      },
      transform(value) {
        return Number(value);
      },
    },
    {
      field: "telefono",
      prompt: "Por favor, indícame un número de teléfono de contacto para poder comunicarnos contigo.\nEjemplo: 919701239",
      validate(value) {
        return /^9\d{8}$/.test(value.trim())
          ? null
          : "Ingresa un telefono valido con formato 949106239.";
      },
      transform: normalizePhoneForStorage,
    },
    {
      field: "credendencial_cuidador_discapacidad",
      prompt: "Cuentas con credencial de discapacidad o eres cuidador/a?",
      options: [
        { id: "true", nombre: "Si" },
        { id: "false", nombre: "No" },
      ],
      validate: validateBooleanOption,
      transform: valueToBoolean,
      display: displayBooleanOption,
    },
    {
      field: "credencial_cuidador_discapacidad_foto",
      prompt: "Puedes tomar una foto de la credencial para adjuntarla a la solicitud.",
      type: "photo",
      skip() {
        return !ADJUNTO_FOTO_HABILITADO || !state.data.credendencial_cuidador_discapacidad;
      },
      defaultValue() {
        return "";
      },
    },
    {
      field: "Neurodivergente_prais_gestante",
      prompt: "Eres persona neurodivergente, PRAIS o gestante?",
      options: [
        { id: "true", nombre: "Si" },
        { id: "false", nombre: "No" },
      ],
      validate: validateBooleanOption,
      transform: valueToBoolean,
      display: displayBooleanOption,
    },
    {
      field: "Neurodivergente_prais_gestante_tipo",
      prompt: "Especifica la condicion declarada.",
      options: condicionOpciones,
      skip() {
        return !state.data.Neurodivergente_prais_gestante;
      },
      defaultValue() {
        return "";
      },
      validate(value) {
        return condicionOpciones.some((option) => option.id === value)
          ? null
          : "Selecciona una opcion para continuar.";
      },
      display(value) {
        return displayCondicion(value);
      },
    },
    {
      field: "Neurodivergente_prais_gestante_otro",
      prompt: "Especifica la condicion en un maximo de 50 caracteres.",
      skip() {
        return state.data.Neurodivergente_prais_gestante_tipo !== "OTRO";
      },
      defaultValue() {
        return "";
      },
      validate(value) {
        const text = value.trim();
        if (!text) return "Escribe el detalle de la opcion otro.";
        if (text.length > 50) return "El detalle debe tener maximo 50 caracteres.";
        return null;
      },
    },
  ];

  function minLength(message, length) {
    return (value) => (value.trim().length >= length ? null : message);
  }

  function esMotivoReceta(valor) {
    return String(valor).trim().toLowerCase() === "receta";
  }

  function validateFullName(value) {
    const words = value.trim().split(/\s+/).filter(Boolean);
    if (value.trim().length < 8 || words.length < 2) {
      return "Ingresa tu nombre completo, con nombre y apellido.";
    }
    return null;
  }

  function validateBooleanOption(value) {
    return ["true", "false"].includes(value) ? null : "Selecciona Si o No para continuar.";
  }

  function valueToBoolean(value) {
    return value === "true";
  }

  function displayBooleanOption(value) {
    return value === "true" ? "Si" : "No";
  }

  function displayCondicion(value) {
    return condicionOpciones.find((option) => option.id === value)?.nombre || "";
  }

  function esPasoDeBotones(step) {
    return Boolean(step && (step.type || step.options));
  }

  function botIcon() {
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 3h4v5h5v4h-5v5h-4v-5H5V8h5V3Zm-5 17h14v-2H5v2Z"/></svg>';
  }

  function userIcon() {
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 9a7 7 0 0 1 14 0H5Z"/></svg>';
  }

  function addMessage(content, sender, options) {
    const row = document.createElement("div");
    row.className = `message message--${sender}`;

    const leftAvatar = document.createElement("div");
    leftAvatar.className = "avatar";
    leftAvatar.innerHTML = botIcon();

    const rightAvatar = document.createElement("div");
    rightAvatar.className = "avatar avatar--user";
    rightAvatar.innerHTML = userIcon();

    const spacer = document.createElement("div");
    const bubble = document.createElement("div");
    bubble.className = "bubble";

    if (options && options.html) {
      bubble.innerHTML = content;
    } else {
      bubble.textContent = content;
    }

    if (sender === "user") {
      row.append(spacer, bubble, rightAvatar);
    } else {
      row.append(leftAvatar, bubble, spacer);
    }

    messages.appendChild(row);
    scrollToLatest(row, sender);
    return row;
  }

  function scrollToLatest(target, sender) {
    const element = target || messages.lastElementChild;
    if (!element) return;
    window.requestAnimationFrame(() => {
      const contenedor = messages.getBoundingClientRect();
      const fila = element.getBoundingClientRect();
      const entraCompleto = fila.top >= contenedor.top && fila.bottom <= contenedor.bottom;
      if (entraCompleto) return; // ya visible: no forzar salto
      element.scrollIntoView({
        behavior: "smooth",
        block: sender === "bot" ? "start" : "nearest",
        inline: "nearest",
      });
    });
  }

  function showTyping(callback) {
    state.waiting = true;
    input.disabled = true;
    submitButton.disabled = true;

    const row = addMessage('<span class="typing">SaludBot esta escribiendo...</span>', "bot", { html: true });
    window.setTimeout(() => {
      row.remove();
      state.waiting = false;
      const gate = esPasoDeBotones(steps[state.index]);
      input.disabled = gate;
      submitButton.disabled = gate;
      callback();
      if (!gate) input.focus();
    }, 520);
  }

  function askCurrentStep() {
    const step = steps[state.index];

    if (!step) {
      showSummary();
      return;
    }

    if (step.skip && step.skip()) {
      state.data[step.field] = step.defaultValue ? step.defaultValue() : "";
      state.index += 1;
      askCurrentStep();
      return;
    }

    if (step.type === "photo") {
      showTyping(() => addMessage(`${escapeHtml(step.prompt)}${renderPhotoCapture()}`, "bot", { html: true }));
      return;
    }

    if (step.type === "terms") {
      showTyping(() => addMessage(`${escapeHtml(step.prompt)}${renderTermsAcceptance()}`, "bot", { html: true }));
      return;
    }

    if (step.quick) {
      const greetingName = userName ? `, ${escapeHtml(userName)}` : "";
      const saludo = `Hola 👋 Soy SaludBot${greetingName}, asistente virtual de salud familiar. Te ayudaré a solicitar una atención de salud médica y a recopilar información necesaria para que el equipo revise tu caso. ¿Qué problema de salud necesitas consultar hoy?`;
      showTyping(() => addMessage(`${saludo}${quickActions()}`, "bot", { html: true }));
      return;
    }

    let prompt = typeof step.prompt === "function" ? step.prompt() : step.prompt;
    if (step.options) {
      prompt = `${formatPromptText(prompt)}${renderOptionButtons(step.options)}`;
    } else {
      prompt = formatPromptText(prompt);
    }

    showTyping(() => addMessage(prompt, "bot", { html: true }));
  }

  function quickActions() {
    const actions = [
      "Fiebre",
      "Dolor o malestar",
      "Problemas respiratorios",
      "Vómitos o diarrea",
      "Problemas al orinar",
      "Otros motivos",
      "Receta",
    ];
    return `
      <div class="quick-actions" aria-label="Opciones rapidas">
        ${actions.map((label) => `<button class="quick-action" type="button" data-value="${escapeAttr(label)}">${escapeHtml(label)}</button>`).join("")}
      </div>
    `;
  }

  function renderOptionButtons(options) {
    return `
      <div class="quick-actions quick-actions--list" aria-label="Opciones disponibles">
        ${options
          .map(
            (option) =>
              `<button class="quick-action quick-action--wide" type="button" data-value="${escapeAttr(option.id)}" data-label="${escapeAttr(option.nombre)}">${escapeHtml(option.nombre)}</button>`
          )
          .join("")}
      </div>
    `;
  }

  function renderPhotoCapture() {
    return `
      <div class="attachment-actions">
        <input class="sr-only" type="file" accept="image/*" capture="environment" data-photo-input>
        <button class="summary-action" type="button" data-photo-action="capture">Tomar foto de credencial</button>
        <button class="summary-action" type="button" data-photo-action="skip">Continuar sin foto</button>
        <p class="field-hint">La foto se adjunta solo a esta solicitud.</p>
      </div>
    `;
  }

  function renderTermsAcceptance() {
    return `
      <div class="terms-box">
        <label class="terms-check">
          <input type="checkbox" data-terms-checkbox>
          <span>Acepto los <a href="/terminos/" target="_blank" rel="noopener">Terminos y Condiciones</a> de uso de la plataforma</span>
        </label>
        <button class="summary-action" type="button" data-terms-action="accept" disabled>Continuar</button>
      </div>
    `;
  }

  function renderUrgencyWarning() {
    return `
      <div class="urgency-card" role="alert">
        <strong>Antes de continuar, si presentas alguna de estas situaciones:</strong>
        <ul>
          <li>Dolor de pecho intenso</li>
          <li>Dificultad importante para respirar</li>
          <li>Pérdida de conciencia</li>
          <li>Convulsiones</li>
          <li>Sangrado abundante</li>
          <li>Debilidad repentina de un brazo o una pierna</li>
          <li>Problemas o dificultad para hablar (posible ACV)</li>
        </ul>
        <p>Tu situación podría requerir atención inmediata. Te recomendamos acudir a SAPU o Servicio de Urgencia del Hospital; si no puedes acudir por tus propios medios, solicita una ambulancia al número 131.</p>
        <p>Si tienes pensamientos de hacerte daño o quitarte la vida, llama al Fono de prevención del suicidio *4141 (gratuito) o acude al servicio de urgencia más cercano.</p>
        <div class="summary-actions urgency-actions">
          <button class="summary-action urgency-action urgency-action--continue" type="button" data-urgency-action="continue">Continuar</button>
          <button class="summary-action urgency-action urgency-action--stop" type="button" data-urgency-action="stop">Terminar solicitud</button>
        </div>
      </div>
    `;
  }

  function showUrgencyWarning() {
    state.waiting = true;
    input.disabled = true;
    submitButton.disabled = true;

    const row = addMessage('<span class="typing">SaludBot esta escribiendo...</span>', "bot", { html: true });
    window.setTimeout(() => {
      row.remove();
      state.waiting = false;
      addMessage(renderUrgencyWarning(), "bot", { html: true });
    }, 520);
  }

  function start() {
    askCurrentStep();
    resetInactivityTimer();
  }

  function showSummary() {
    if (!state.data.acepta_terminos) {
      askCurrentStep();
      return;
    }

    state.complete = true;
    input.disabled = true;
    submitButton.disabled = true;

    const condicion = state.data.Neurodivergente_prais_gestante
      ? `${displayCondicion(state.data.Neurodivergente_prais_gestante_tipo)}${state.data.Neurodivergente_prais_gestante_otro ? `: ${state.data.Neurodivergente_prais_gestante_otro}` : ""}`
      : "No";

    const summary = `
      <strong>Revisa los datos antes de continuar.</strong>
      <div class="summary">
        <div class="summary__item"><span>Motivo</span><strong>${escapeHtml(state.data.motivo)}</strong></div>
        <div class="summary__item"><span>Sintomas</span><strong>${escapeHtml(state.data.detalle_sintomas)}</strong></div>
        <div class="summary__item"><span>RUT</span><strong>${escapeHtml(state.data.rut)}</strong></div>
        <div class="summary__item"><span>Nombre</span><strong>${escapeHtml(state.data.nombre)}</strong></div>
        <div class="summary__item"><span>Edad</span><strong>${escapeHtml(state.data.edad)}</strong></div>
        <div class="summary__item"><span>Telefono</span><strong>${escapeHtml(state.data.telefono)}</strong></div>
        <div class="summary__item"><span>CESFAM</span><strong>${escapeHtml(state.selectedCentroName)}</strong></div>
        <div class="summary__item"><span>Credencial/cuidador</span><strong>${state.data.credendencial_cuidador_discapacidad ? "Si" : "No"}</strong></div>
        <div class="summary__item"><span>Foto credencial</span><strong>${state.data.credencial_cuidador_discapacidad_foto ? "Adjunta" : "No adjunta"}</strong></div>
        <div class="summary__item"><span>Neurodivergente/PRAIS/gestante</span><strong>${escapeHtml(condicion)}</strong></div>
        <div class="summary__item"><span>Terminos</span><strong>Aceptados</strong></div>
      </div>
      <div class="summary-actions">
        <button class="summary-action" type="button" data-final-action="send">Confirmar y enviar</button>
        <button class="summary-action" type="button" data-final-action="restart">Corregir datos</button>
      </div>
    `;

    showTyping(() => addMessage(summary, "bot", { html: true }));
  }

  function restart() {
    state.index = 0;
    state.complete = false;
    state.data = {};
    state.selectedCentroName = centroInicial;
    state.waiting = false;
    state.submitting = false;
    state.esReceta = false;
    messages.innerHTML = "";
    input.disabled = false;
    submitButton.disabled = false;
    input.placeholder = "Escribe tu respuesta...";
    input.value = "";
    start();
  }

  function resetByInactivity() {
    if (state.complete || state.index === 0) {
      resetInactivityTimer();
      return;
    }

    state.index = 0;
    state.complete = false;
    state.data = {};
    state.selectedCentroName = centroInicial;
    state.waiting = false;
    state.submitting = false;
    state.esReceta = false;
    messages.innerHTML = "";
    input.disabled = false;
    submitButton.disabled = false;
    input.placeholder = "Escribe tu respuesta...";
    input.value = "";
    addMessage("La conversacion se reinicio por inactividad de 20 minutos.", "bot");
    start();
  }

  let inactivityTimer = window.setTimeout(resetByInactivity, INACTIVITY_LIMIT_MS);

  function resetInactivityTimer() {
    window.clearTimeout(inactivityTimer);
    inactivityTimer = window.setTimeout(resetByInactivity, INACTIVITY_LIMIT_MS);
  }

  async function finish() {
    if (state.submitting) return;
    state.submitting = true;
    resetInactivityTimer();
    input.disabled = true;
    submitButton.disabled = true;
    addMessage("Estoy registrando tu solicitud en el sistema.", "bot");

    const payload = {
      nombre: state.data.nombre,
      rut: state.data.rut,
      edad: state.data.edad,
      telefono: state.data.telefono,
      centro_salud: state.data.centro_salud,
      credendencial_cuidador_discapacidad: state.data.credendencial_cuidador_discapacidad,
      credencial_cuidador_discapacidad_foto: state.data.credencial_cuidador_discapacidad_foto || "",
      Neurodivergente_prais_gestante: state.data.Neurodivergente_prais_gestante,
      Neurodivergente_prais_gestante_tipo: state.data.Neurodivergente_prais_gestante_tipo || "",
      Neurodivergente_prais_gestante_otro: state.data.Neurodivergente_prais_gestante_otro || "",
      acepta_terminos: state.data.acepta_terminos,
      motivo: state.data.motivo,
      detalle_motivo: state.data.detalle_sintomas,
    };

    try {
      const response = await fetch("/api/solicitudes/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrfToken(),
        },
        body: JSON.stringify(payload),
      });
      const result = await response.json();

      if (!response.ok) {
        addMessage(`<span class="error">No se pudo guardar la solicitud.</span><br>${formatErrors(result.errors)}`, "bot", { html: true });
        askAnotherSolicitud();
        return;
      }

      addMessage(
        `Solicitud registrada correctamente.<br><br><strong>ID de solicitud:</strong> ${result.id_solicitud}<br><strong>Nombre:</strong> ${escapeHtml(result.resumen.nombre)}<br><strong>RUT:</strong> ${escapeHtml(result.resumen.rut)}<br><strong>Centro de salud:</strong> ${escapeHtml(result.resumen.centro_salud_nombre || state.selectedCentroName)}<br><strong>Edad:</strong> ${escapeHtml(result.resumen.edad)}<div class="success-notice"><strong class="success-notice__title">Importante</strong><p>Su solicitud será revisada por un profesional clínico durante el día. Una vez evaluada, le informaremos si se le asignará una hora de atención médica o si deberá realizar una nueva solicitud al día siguiente.</p></div>`,
        "bot",
        { html: true }
      );
      askAnotherSolicitud();
    } catch (error) {
      addMessage('<span class="error">No se pudo conectar con el servidor. Intenta nuevamente.</span>', "bot", { html: true });
      askAnotherSolicitud();
    }
  }

  function askAnotherSolicitud() {
    addMessage(
      `Deseas realizar otra solicitud?
      <div class="summary-actions">
        <button class="summary-action" type="button" data-post-action="restart">Si</button>
        <button class="summary-action" type="button" data-post-action="close">No</button>
      </div>`,
      "bot",
      { html: true }
    );
  }

  function closeConversation() {
    input.disabled = true;
    submitButton.disabled = true;
    input.placeholder = "La conversacion ha finalizado.";
    addMessage("Gracias. La conversacion ha finalizado.", "bot");
  }

  function disableSiblingActions(button) {
    const container = button.closest(".quick-actions, .summary-actions, .attachment-actions, .terms-box");
    if (!container) return;

    container.querySelectorAll("button").forEach((actionButton) => {
      actionButton.disabled = true;
      actionButton.setAttribute("aria-disabled", "true");
    });
  }

  function submitValue(value) {
    resetInactivityTimer();
    const step = steps[state.index];
    if (!step) return;

    const error = step.validate(value);
    const displayValue = step.display ? step.display(value) : value;
    addMessage(displayValue, "user");

    if (error) {
      showTyping(() => addMessage(`<span class="error">${escapeHtml(error)}</span>`, "bot", { html: true }));
      return;
    }

    state.data[step.field] = step.transform ? step.transform(value) : value.trim();
    if (step.field === "centro_salud") {
      state.selectedCentroName = displayValue;
    }
    if (step.field === "motivo") {
      state.esReceta = esMotivoReceta(value);
    }
    state.index += 1;

    if (step.field === "motivo") {
      if (state.esReceta) {
        askCurrentStep();
      } else {
        showUrgencyWarning();
      }
      return;
    }

    askCurrentStep();
  }

  function handlePhotoFile(file) {
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      state.data.credencial_cuidador_discapacidad_foto = String(reader.result || "");
      addMessage("Foto de credencial adjunta", "user");
      state.index += 1;
      askCurrentStep();
    };
    reader.onerror = () => {
      addMessage('<span class="error">No se pudo leer la foto. Puedes intentar nuevamente o continuar sin foto.</span>', "bot", { html: true });
    };
    reader.readAsDataURL(file);
  }

  function acceptTerms() {
    state.data.acepta_terminos = true;
    addMessage("Acepto los Terminos y Condiciones", "user");
    state.index += 1;
    askCurrentStep();
  }

  function isValidRut(value) {
    const rut = value.trim();
    if (!/^\d{7,8}-[\dkK]$/.test(rut)) return false;

    const clean = rut.replace("-", "").toUpperCase();
    const body = clean.slice(0, -1);
    const checkDigit = clean.slice(-1);
    const factors = [2, 3, 4, 5, 6, 7];
    let sum = 0;

    Array.from(body).reverse().forEach((digit, index) => {
      sum += Number(digit) * factors[index % factors.length];
    });

    const result = 11 - (sum % 11);
    const expected = result === 11 ? "0" : result === 10 ? "K" : String(result);
    return checkDigit === expected;
  }

  function normalizeRutForStorage(value) {
    const clean = value.replace("-", "").toUpperCase();
    return `${clean.slice(0, -1)}-${clean.slice(-1)}`;
  }

  function normalizePhoneForStorage(value) {
    return `+56${value.trim()}`;
  }

  function formatPromptText(value) {
    return escapeHtml(value)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br>");
  }

  function formatErrors(errors) {
    if (Array.isArray(errors)) return errors.map(escapeHtml).join("<br>");
    return Object.entries(errors || {})
      .map(([field, values]) => `${escapeHtml(field)}: ${values.map(escapeHtml).join(", ")}`)
      .join("<br>");
  }

  function getCsrfToken() {
    const csrfInput = document.querySelector("[name=csrfmiddlewaretoken]");
    if (csrfInput) return csrfInput.value;

    const cookie = document.cookie
      .split(";")
      .map((item) => item.trim())
      .find((item) => item.startsWith("csrftoken="));
    return cookie ? decodeURIComponent(cookie.split("=").slice(1).join("=")) : "";
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replaceAll("`", "&#096;");
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (state.waiting || state.complete) return;

    const value = input.value.trim();
    if (!value) return;

    input.value = "";
    submitValue(value);
  });

  messages.addEventListener("click", (event) => {
    resetInactivityTimer();
    const quickButton = event.target.closest("[data-value]");
    const finalButton = event.target.closest("[data-final-action]");
    const postButton = event.target.closest("[data-post-action]");
    const photoButton = event.target.closest("[data-photo-action]");
    const termsButton = event.target.closest("[data-terms-action]");
    const urgencyButton = event.target.closest("[data-urgency-action]");

    if (quickButton && !state.waiting && !state.complete) {
      disableSiblingActions(quickButton);
      submitValue(quickButton.dataset.value);
      return;
    }

    if (urgencyButton && !urgencyButton.disabled) {
      disableSiblingActions(urgencyButton);
      if (urgencyButton.dataset.urgencyAction === "continue") {
        askCurrentStep();
      } else {
        closeConversation();
      }
      return;
    }

    if (photoButton && !photoButton.disabled) {
      if (photoButton.dataset.photoAction === "capture") {
        const fileInput = photoButton.closest(".attachment-actions").querySelector("[data-photo-input]");
        fileInput.click();
      } else {
        disableSiblingActions(photoButton);
        state.data.credencial_cuidador_discapacidad_foto = "";
        addMessage("Continuar sin foto", "user");
        state.index += 1;
        askCurrentStep();
      }
      return;
    }

    if (termsButton && !termsButton.disabled) {
      disableSiblingActions(termsButton);
      acceptTerms();
      return;
    }

    if (postButton) {
      disableSiblingActions(postButton);
      if (postButton.dataset.postAction === "restart") {
        restart();
      } else {
        closeConversation();
      }
      return;
    }

    if (!finalButton || finalButton.disabled) return;

    disableSiblingActions(finalButton);
    if (finalButton.dataset.finalAction === "restart") {
      restart();
    } else {
      finish();
    }
  });

  messages.addEventListener("change", (event) => {
    resetInactivityTimer();
    const fileInput = event.target.closest("[data-photo-input]");
    const termsCheckbox = event.target.closest("[data-terms-checkbox]");

    if (fileInput) {
      if (!fileInput.files[0]) return;
      const container = fileInput.closest(".attachment-actions");
      container.querySelectorAll("button").forEach((button) => {
        button.disabled = true;
      });
      handlePhotoFile(fileInput.files[0]);
      return;
    }

    if (termsCheckbox) {
      const button = termsCheckbox.closest(".terms-box").querySelector("[data-terms-action]");
      button.disabled = !termsCheckbox.checked;
    }
  });

  start();
})();
