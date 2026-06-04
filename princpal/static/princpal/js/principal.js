const sidebarToggle = document.getElementById("sidebarToggle");
const navTriggers = document.querySelectorAll("[data-nav]");
const sidebarLinks = document.querySelectorAll(".sidebar-link[data-nav]");
const appViews = document.querySelectorAll(".app-view");

function showView(viewName) {
  appViews.forEach((view) => {
    view.classList.toggle("active", view.dataset.view === viewName);
  });

  sidebarLinks.forEach((link) => {
    const isActive = link.dataset.nav === viewName;
    link.classList.toggle("active", isActive);
    if (isActive) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
}

navTriggers.forEach((trigger) => {
  trigger.addEventListener("click", (event) => {
    const viewName = trigger.dataset.nav;
    if (!viewName) return;

    event.preventDefault();
    showView(viewName);
    history.replaceState(null, "", `#${viewName}`);
  });
});

if (sidebarToggle) {
  sidebarToggle.addEventListener("click", () => {
    document.body.classList.toggle("sidebar-collapsed");
  });
}

const initialView = window.location.hash.replace("#", "");
const validViews = Array.from(appViews).map((view) => view.dataset.view);
if (validViews.includes(initialView)) {
  showView(initialView);
}

const tutorialOverlay = document.getElementById("tutorialOverlay");
const tutorialStepBadge = document.getElementById("tutorialStepBadge");
const tutorialSkip = document.getElementById("tutorialSkip");
const tutorialClose = document.getElementById("tutorialClose");
const tutorialIcon = document.getElementById("tutorialIcon");
const tutorialTitle = document.getElementById("tutorialTitle");
const tutorialSubtitle = document.getElementById("tutorialSubtitle");
const tutorialBoxTitle = document.getElementById("tutorialBoxTitle");
const tutorialList = document.getElementById("tutorialList");
const tutorialTip = document.getElementById("tutorialTip");
const tutorialPrev = document.getElementById("tutorialPrev");
const tutorialNext = document.getElementById("tutorialNext");
const tutorialDots = document.getElementById("tutorialDots");
const openTutorial = document.getElementById("openTutorial");

const tutorialSteps = [
  {
    icon: "pulse",
    title: "¡Bienvenido a Nexo ReV!",
    subtitle: "Tu plataforma de rehabilitación domiciliaria",
    boxTitle: "¿Qué puedes hacer?",
    items: [
      "Realiza ejercicios desde la comodidad de tu hogar",
      "Sigue tu progreso y evolución",
      "Accede a videos especializados para cada zona del cuerpo",
      "Recibe recomendaciones personalizadas",
    ],
    tip: true,
  },
  {
    icon: "home",
    title: "Inicio - Selección de zona",
    subtitle: "Identifica la parte del cuerpo que necesita atención",
    boxTitle: "Cómo funciona:",
    items: [
      "Haz clic en el área del cuerpo que te molesta",
      "Puedes seleccionar múltiples zonas en diferentes sesiones",
      "La zona seleccionada se ilumina en color teal",
      'Presiona "Continuar" para ir al diagnóstico',
    ],
  },
  {
    icon: "pulse",
    title: "Diagnóstico - Tu evaluación",
    subtitle: "Completa información sobre tu condición",
    boxTitle: "Cómo funciona:",
    items: [
      "Indica tu nivel de dolor del 1 al 10",
      "Describe cuánto tiempo has tenido el malestar",
      "Especifica la frecuencia del dolor",
      "Puedes guardar borradores y continuar después",
      "Al enviar, recibirás videos recomendados",
    ],
  },
  {
    icon: "video",
    title: "Videos - Biblioteca de ejercicios",
    subtitle: "Explora y realiza rutinas de rehabilitación",
    boxTitle: "Cómo funciona:",
    items: [
      "Usa la barra de búsqueda para encontrar ejercicios específicos",
      "Filtra por categorías (Rodilla, Hombro, Espalda, etc.)",
      "Marca tus favoritos con el corazón 💗",
      "Revisa la dificultad: Principiante, Intermedio o Avanzado",
      "Consulta la duración antes de comenzar",
    ],
  },
  {
    icon: "history",
    title: "Historial - Tu progreso",
    subtitle: "Visualiza tu evolución y estadísticas",
    boxTitle: "Cómo funciona:",
    items: [
      "Ve gráficas de tu evolución de dolor",
      "Revisa tus sesiones completadas",
      "Consulta tu racha de días consecutivos",
      "Descarga reportes semanales en PDF",
      "Compara tu progreso a lo largo del tiempo",
    ],
  },
  {
    icon: "user",
    title: "Perfil - Personalización",
    subtitle: "Configura tu cuenta y preferencias",
    boxTitle: "Cómo funciona:",
    items: [
      "Actualiza tus datos personales",
      "Cambia tu foto de perfil",
      "Activa/desactiva notificaciones",
      "Configura el modo oscuro",
      "Cambia tu contraseña de forma segura",
    ],
  },
];

const tutorialIcons = {
  pulse: '<svg viewBox="0 0 64 64"><path d="M10 34h12l7-24 11 44 7-24h7" /></svg>',
  home: '<svg viewBox="0 0 64 64"><path d="M14 30 32 14l18 16v22H14V30Z" /><path d="M26 52V36h12v16" /></svg>',
  video: '<svg viewBox="0 0 64 64"><rect x="12" y="20" width="30" height="24" rx="5" /><path d="m42 28 12-7v22l-12-7" /></svg>',
  history: '<svg viewBox="0 0 64 64"><path d="M15 20v-9M15 20h9" /><path d="M15 20a21 21 0 1 1-3 17" /><path d="M32 22v12l9 5" /></svg>',
  user: '<svg viewBox="0 0 64 64"><circle cx="32" cy="18" r="10" /><path d="M16 52v-8c0-8 7-14 16-14s16 6 16 14v8" /></svg>',
};

let tutorialIndex = 0;

function renderTutorial() {
  const step = tutorialSteps[tutorialIndex];
  const isFirst = tutorialIndex === 0;
  const isLast = tutorialIndex === tutorialSteps.length - 1;

  tutorialStepBadge.textContent = `Paso ${tutorialIndex + 1} de ${tutorialSteps.length}`;
  tutorialIcon.innerHTML = tutorialIcons[step.icon];
  tutorialTitle.textContent = step.title;
  tutorialSubtitle.textContent = step.subtitle;
  tutorialBoxTitle.textContent = step.boxTitle;
  tutorialList.innerHTML = step.items.map((item) => `<li>${item}</li>`).join("");
  tutorialTip.hidden = !step.tip;
  tutorialSkip.hidden = isFirst;
  tutorialPrev.disabled = isFirst;
  tutorialNext.innerHTML = isLast
    ? '<span>Finalizar</span><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="m9 12 2 2 4-5" /></svg>'
    : '<span>Siguiente</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg>';
  tutorialDots.innerHTML = tutorialSteps
    .map((_, index) => {
      const dotClass = index === tutorialIndex ? "active" : index < tutorialIndex ? "passed" : "";
      return `<button class="${dotClass}" type="button" aria-label="Ir al paso ${index + 1}"></button>`;
    })
    .join("");

  tutorialDots.querySelectorAll("button").forEach((dot, index) => {
    dot.addEventListener("click", () => {
      tutorialIndex = index;
      renderTutorial();
    });
  });
}

function openTutorialModal() {
  tutorialIndex = 0;
  renderTutorial();
  tutorialOverlay.classList.remove("hidden");
  document.body.classList.add("tutorial-open");
}

function closeTutorial() {
  tutorialOverlay.classList.add("hidden");
  document.body.classList.remove("tutorial-open");
}

if (tutorialPrev) {
  tutorialPrev.addEventListener("click", () => {
    if (tutorialIndex > 0) {
      tutorialIndex -= 1;
      renderTutorial();
    }
  });
}

if (tutorialNext) {
  tutorialNext.addEventListener("click", () => {
    if (tutorialIndex === tutorialSteps.length - 1) {
      closeTutorial();
      return;
    }

    tutorialIndex += 1;
    renderTutorial();
  });
}

if (tutorialClose) {
  tutorialClose.addEventListener("click", closeTutorial);
}
if (tutorialSkip) {
  tutorialSkip.addEventListener("click", closeTutorial);
}
if (openTutorial) {
  openTutorial.addEventListener("click", openTutorialModal);
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !tutorialOverlay.classList.contains("hidden")) {
    closeTutorial();
  }
});

renderTutorial();

// ============== FUNCIONALIDAD DE MODALES PERSONALIZADOS ==============
const alertModal = document.getElementById("alertModal");
const confirmModal = document.getElementById("confirmModal");
const successModal = document.getElementById("successModal");
const alertTitle = document.getElementById("alertTitle");
const alertMessage = document.getElementById("alertMessage");
const alertClose = document.getElementById("alertClose");
const alertOk = document.getElementById("alertOk");
const confirmTitle = document.getElementById("confirmTitle");
const confirmMessage = document.getElementById("confirmMessage");
const confirmCancel = document.getElementById("confirmCancel");
const confirmOk = document.getElementById("confirmOk");
const successTitle = document.getElementById("successTitle");
const successMessage = document.getElementById("successMessage");

let confirmCallback = null;

function showAlert(title, message) {
  if (!alertTitle || !alertMessage || !alertModal || !alertOk) {
    console.warn('Modal de alerta no disponible');
    return;
  }
  alertTitle.textContent = title;
  alertMessage.textContent = message;
  alertModal.classList.remove("hidden");
  alertOk.focus();
}

function closeAlert() {
  if (!alertModal) return;
  alertModal.classList.add("hidden");
}

function showConfirm(title, message, callback) {
  if (!confirmTitle || !confirmMessage || !confirmModal || !confirmOk) {
    console.warn('Modal de confirmación no disponible');
    if (callback) callback();
    return;
  }
  confirmTitle.textContent = title;
  confirmMessage.textContent = message;
  confirmCallback = callback;
  confirmModal.classList.remove("hidden");
  confirmOk.focus();
}

function closeConfirm(confirmed) {
  if (confirmModal) {
    confirmModal.classList.add("hidden");
  }
  if (confirmed && confirmCallback) {
    confirmCallback();
  }
  confirmCallback = null;
}

function showSuccess(title, message) {
  if (!successTitle || !successMessage || !successModal) {
    console.warn('Modal de éxito no disponible');
    return;
  }
  successTitle.textContent = title;
  successMessage.textContent = message;
  successModal.classList.remove("hidden");
  
  setTimeout(() => {
    successModal.classList.add("hidden");
  }, 2500);
}

if (alertOk) {
  alertOk.addEventListener("click", closeAlert);
}
if (alertClose) {
  alertClose.addEventListener("click", closeAlert);
}
if (confirmCancel) {
  confirmCancel.addEventListener("click", () => closeConfirm(false));
}
if (confirmOk) {
  confirmOk.addEventListener("click", () => closeConfirm(true));
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (alertModal && !alertModal.classList.contains("hidden")) closeAlert();
    if (confirmModal && !confirmModal.classList.contains("hidden")) closeConfirm(false);
  }
});

// ============== FUNCIONALIDAD DE PERFIL ==============
const profileForm = document.querySelector(".profile-page");
const saveButton = document.querySelector(".save-button");
const changePasswordButton = document.querySelector(".wide-outline-button");
const cambiarFotoButton = document.getElementById("cambiarFotoButton");
const fotoInput = document.getElementById("fotoInput");
const avatarInitial = document.getElementById("avatarInitial");
const avatarImage = document.getElementById("avatarImage");

// Campos del formulario dentro de profile-fields
const profileFields = document.querySelectorAll(".profile-fields input");
const nombreInput = profileFields[0];
const telefonoInput = profileFields[1];
const edadInput = profileFields[2];

// Campos de contraseña
const passwordFields = document.querySelectorAll(".password-fields input");
const currentPasswordInput = passwordFields[0];
const newPasswordInput = passwordFields[1];
const confirmPasswordInput = passwordFields[2];

// Guardar valores originales para comparar
let originalEmail = null;

// Funcionalidad para cambiar foto
if (cambiarFotoButton && fotoInput) {
  cambiarFotoButton.addEventListener("click", (e) => {
    e.preventDefault();
    fotoInput.click();
  });

  fotoInput.addEventListener("change", (e) => {
    const archivo = e.target.files[0];
    if (!archivo) return;

  // Validar tipo
  const tiposPermitidos = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
  if (!tiposPermitidos.includes(archivo.type)) {
    showAlert("Error", "Solo se permiten imágenes (JPG, PNG, GIF, WebP)");
    fotoInput.value = "";
    return;
  }

  // Validar tamaño (5MB)
  if (archivo.size > 5 * 1024 * 1024) {
    showAlert("Error", "La imagen no debe superar 5MB");
    fotoInput.value = "";
    return;
  }

  // Mostrar preview
  const reader = new FileReader();
  reader.onload = (event) => {
    avatarInitial.style.display = "none";
    avatarImage.src = event.target.result;
    avatarImage.style.display = "block";
  };
  reader.readAsDataURL(archivo);

  // Enviar al servidor
  const formData = new FormData();
  formData.append('foto', archivo);

  fetch('/principal/api/upload-photo/', {
    method: 'POST',
    headers: {
      'X-CSRFToken': getCookie('csrftoken'),
    },
    body: formData
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      showSuccess("¡Listo!", "Foto actualizada correctamente");
      // Recargar la foto desde el servidor evitando caché
      if (data.foto_url) {
        setTimeout(() => {
          avatarImage.src = data.foto_url + '?t=' + new Date().getTime();
          avatarInitial.style.display = "none";
          avatarImage.style.display = "block";
        }, 500);
      }
      fotoInput.value = "";
    } else {
      showAlert("Error", data.error || "No se pudo subir la foto");
      avatarInitial.style.display = "block";
      avatarImage.style.display = "none";
      fotoInput.value = "";
    }
  })
  .catch(error => {
    showAlert("Error", "Error al subir la foto: " + error);
    avatarInitial.style.display = "block";
    avatarImage.style.display = "none";
    fotoInput.value = "";
  });
});
}

// ============== FUNCIONALIDAD DE MODO OSCURO ==============
const darkModeSwitch = document.querySelector(".preference-row:first-of-type .mini-switch input");

function saveDarkModePreferenceLocal(value) {
  try {
    localStorage.setItem('nexorev_dark_mode', String(value));
  } catch (e) {
    console.warn('No se pudo guardar modo oscuro en localStorage', e);
  }
}

function loadDarkModePreference() {
  try {
    return localStorage.getItem('nexorev_dark_mode') === 'true';
  } catch (e) {
    console.warn('No se pudo leer modo oscuro de localStorage', e);
    return false;
  }
}

function applyDarkMode(enabled) {
  document.documentElement.classList.toggle('dark-mode', enabled);
  if (document.body) {
    document.body.classList.toggle('dark-mode', enabled);
  }
  try {
    if (enabled) {
      // eliminar atributo para que las reglas :root[data-theme="light"] no se apliquen
      document.documentElement.removeAttribute('data-theme');
    } else {
      // forzar el tema claro para hojas que usan data-theme
      document.documentElement.setAttribute('data-theme', 'light');
    }
  } catch (e) {
    console.warn('No se pudo aplicar data-theme', e);
  }
}

applyDarkMode(loadDarkModePreference());

if (darkModeSwitch) {
  darkModeSwitch.checked = loadDarkModePreference();

  darkModeSwitch.addEventListener("change", (e) => {
    const modoOscuroActivo = e.target.checked;
    applyDarkMode(modoOscuroActivo);
    saveDarkModePreferenceLocal(modoOscuroActivo);
  });
}

// Función para cambiar contraseña
if (changePasswordButton) {
  changePasswordButton.addEventListener("click", (e) => {
  e.preventDefault();

  const currentPassword = currentPasswordInput.value.trim();
  const newPassword = newPasswordInput.value.trim();
  const confirmPassword = confirmPasswordInput.value.trim();

  // Validaciones
  if (!currentPassword || !newPassword || !confirmPassword) {
    showAlert("Campos incompletos", "Por favor completa todos los campos de contraseña");
    return;
  }

  if (newPassword !== confirmPassword) {
    showAlert("Error", "Las nuevas contraseñas no coinciden");
    return;
  }

  if (newPassword.length < 6) {
    showAlert("Error", "La nueva contraseña debe tener al menos 6 caracteres");
    return;
  }

  if (currentPassword === newPassword) {
    showAlert("Error", "La nueva contraseña no puede ser igual a la actual");
    return;
  }

  // Enviar al servidor
  fetch('/principal/api/change-password/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
    },
    body: JSON.stringify({
      currentPassword,
      newPassword,
      confirmPassword,
    })
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      showSuccess("¡Listo!", "Contraseña cambiada correctamente");
      currentPasswordInput.value = "";
      newPasswordInput.value = "";
      confirmPasswordInput.value = "";
    } else {
      showAlert("Error", data.error || "No se pudo cambiar la contraseña");
    }
  })
  .catch(error => {
    showAlert("Error", "Error al cambiar la contraseña: " + error);
  });
});
}

// Función para guardar cambios
if (saveButton) {
  saveButton.addEventListener("click", (e) => {
  e.preventDefault();

  const nuevoNombre = nombreInput.value.trim();
  const nuevoTelefono = telefonoInput.value.trim();
  const nuevaEdad = edadInput.value.trim();

  // Validaciones básicas
  if (!nuevoNombre) {
    showAlert("Error", "El nombre no puede estar vacío");
    return;
  }

  guardarCambios(nuevoNombre, nuevoTelefono, nuevaEdad);
  });
}

function guardarCambios(nombre, telefono, edad) {
  fetch('/principal/api/update-profile/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
    },
    body: JSON.stringify({
      nombre,
      telefono,
      edad,
    })
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      showSuccess("¡Listo!", "Cambios guardados correctamente");
    } else {
      showAlert("Error", data.error || "No se pudieron guardar los cambios");
    }
  })
  .catch(error => {
    showAlert("Error", "Error al guardar los cambios: " + error);
  });
}

// Función para obtener CSRF token
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}
