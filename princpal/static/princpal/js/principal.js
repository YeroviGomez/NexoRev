const sidebarToggle = document.getElementById("sidebarToggle");
const navTriggers = document.querySelectorAll("[data-nav]");
const sidebarLinks = document.querySelectorAll(".sidebar-link[data-nav]");
const appViews = document.querySelectorAll(".app-view");
const favoriteUser = document.body.dataset.currentUser?.toLowerCase() || 'anonymous';
const favoritesStorageKey = `nexorev_favorites_${favoriteUser}`;

const getFavorites = () => {
  try {
    const favorites = JSON.parse(localStorage.getItem(favoritesStorageKey) || '[]');
    return Array.isArray(favorites) ? favorites : [];
  } catch {
    return [];
  }
};

const saveFavorites = (favorites) => {
  localStorage.setItem(favoritesStorageKey, JSON.stringify(favorites));
};

const updateFavoriteButtons = () => {
  const favorites = getFavorites();
  document.querySelectorAll('.favorite-btn[data-favorite-id]').forEach((button) => {
    const isFavorite = favorites.includes(button.dataset.favoriteId);
    button.classList.toggle('is-favorite', isFavorite);
    button.setAttribute('aria-pressed', String(isFavorite));
    button.setAttribute('aria-label', isFavorite ? 'Quitar de favoritos' : 'Agregar a favoritos');
  });
};

const renderFavorites = () => {
  const favoritesGrid = document.getElementById('favoritesGrid');
  const favoritesEmpty = document.getElementById('favoritesEmpty');
  const favoritesCount = document.getElementById('favoritesCount');
  if (!favoritesGrid || !favoritesEmpty || !favoritesCount) return;

  const favoriteIds = getFavorites();
  const sourceCards = Array.from(document.querySelectorAll('#videosView .video-card'));
  const cardsById = new Map(sourceCards.map((card) => [
    card.querySelector('.favorite-btn')?.dataset.favoriteId,
    card,
  ]));
  favoritesGrid.innerHTML = '';
  favoritesCount.textContent = `${favoriteIds.length} ${favoriteIds.length === 1 ? 'video guardado' : 'videos guardados'}`;
  favoritesEmpty.hidden = favoriteIds.length > 0;

  favoriteIds.forEach((favoriteId, index) => {
    const sourceCard = cardsById.get(favoriteId);
    if (!sourceCard) return;
    const card = sourceCard.cloneNode(true);
    card.classList.add('favorite-card');
    card.hidden = false;
    const favoriteButton = card.querySelector('.favorite-btn');
    favoriteButton.setAttribute('aria-pressed', 'true');
    favoriteButton.setAttribute('aria-label', 'Quitar de favoritos');
    favoriteButton.classList.add('is-favorite');
    favoriteButton.addEventListener('click', () => {
      saveFavorites(getFavorites().filter((id) => id !== favoriteId));
      updateFavoriteButtons();
      renderFavorites();
    });

    const actions = document.createElement('div');
    actions.className = 'favorite-order-actions';
    actions.innerHTML = `
      <button type="button" class="favorite-order-btn" aria-label="Mover hacia arriba" ${index === 0 ? 'disabled' : ''}>↑</button>
      <button type="button" class="favorite-order-btn" aria-label="Mover hacia abajo" ${index === favoriteIds.length - 1 ? 'disabled' : ''}>↓</button>
    `;
    const [moveUp, moveDown] = actions.querySelectorAll('button');
    moveUp.addEventListener('click', () => moveFavorite(favoriteId, -1));
    moveDown.addEventListener('click', () => moveFavorite(favoriteId, 1));
    card.querySelector('.video-copy').append(actions);
    favoritesGrid.append(card);
  });
};

const moveFavorite = (favoriteId, direction) => {
  const favorites = getFavorites();
  const currentIndex = favorites.indexOf(favoriteId);
  const nextIndex = currentIndex + direction;
  if (currentIndex < 0 || nextIndex < 0 || nextIndex >= favorites.length) return;
  [favorites[currentIndex], favorites[nextIndex]] = [favorites[nextIndex], favorites[currentIndex]];
  saveFavorites(favorites);
  renderFavorites();
};

document.querySelectorAll('#videosView .favorite-btn[data-favorite-id]').forEach((button) => {
  button.addEventListener('click', () => {
    const favorites = getFavorites();
    const favoriteId = button.dataset.favoriteId;
    const nextFavorites = favorites.includes(favoriteId)
      ? favorites.filter((id) => id !== favoriteId)
      : [...favorites, favoriteId];
    saveFavorites(nextFavorites);
    updateFavoriteButtons();
    renderFavorites();
  });
});

document.getElementById('clearFavorites')?.addEventListener('click', () => {
  saveFavorites([]);
  updateFavoriteButtons();
  renderFavorites();
});

updateFavoriteButtons();
renderFavorites();

const progressStorageKey = 'nexorev_completed_routines';
const getCompletedRoutines = () => {
  try {
    const routines = JSON.parse(localStorage.getItem(progressStorageKey) || '[]');
    return Array.isArray(routines) ? routines : [];
  } catch {
    return [];
  }
};

const renderProgress = () => {
  const routines = getCompletedRoutines();
  const count = routines.length;
  const completedRoutines = document.getElementById('completedRoutines');
  const homeProgressText = document.getElementById('homeProgressText');
  const homeProgressBar = document.getElementById('homeProgressBar');
  if (completedRoutines) completedRoutines.textContent = count;
  if (homeProgressText) homeProgressText.textContent = `${count} rutinas completadas`;
  if (homeProgressBar) homeProgressBar.style.width = `${Math.min(count * 16.67, 100)}%`;
  const historyList = document.getElementById('historyList');
  if (historyList) {
    historyList.innerHTML = routines.length
      ? routines.map((routine) => `<li><span>${routine}</span><time>${new Date().toLocaleDateString('es-ES')}</time></li>`).join('')
      : '<li>Aún no has completado rutinas.</li>';
  }
};

document.querySelectorAll('.filter-chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    document.querySelectorAll('.filter-chip').forEach((item) => item.classList.toggle('active', item === chip));
    const category = chip.dataset.category;
    document.querySelectorAll('.video-card').forEach((card) => {
      card.hidden = category !== 'Todas' && card.dataset.category !== category;
    });
    updateVideoCount();
  });
});

const videoSearch = document.getElementById('videoSearch');
const updateVideoCount = () => {
  const visible = document.querySelectorAll('.video-card:not([hidden])').length;
  const videoCount = document.querySelector('.video-count');
  if (videoCount) videoCount.textContent = `Mostrando ${visible} videos`;
};
if (videoSearch) {
  videoSearch.addEventListener('input', () => {
    const query = videoSearch.value.trim().toLowerCase();
    document.querySelectorAll('.video-card').forEach((card) => {
      card.hidden = query && !card.dataset.title.includes(query);
    });
    updateVideoCount();
  });
}

document.querySelectorAll('.routine-button').forEach((button) => {
  button.addEventListener('click', () => {
    const routines = getCompletedRoutines();
    if (!routines.includes(button.dataset.routine)) routines.push(button.dataset.routine);
    localStorage.setItem(progressStorageKey, JSON.stringify(routines));
    button.textContent = 'Rutina completada';
    button.disabled = true;
    button.nextElementSibling.hidden = false;
    button.nextElementSibling.querySelector('span').style.width = '100%';
    renderProgress();
    window.dispatchEvent(new CustomEvent('routine-completed'));
  });
});

renderProgress();

const videoSafetyTips = document.getElementById('videoSafetyTips');
const openVideoSafetyTips = document.getElementById('openVideoSafetyTips');
const closeVideoSafetyTips = document.getElementById('closeVideoSafetyTips');
const closeVideoSafetyModal = () => {
  if (videoSafetyTips) videoSafetyTips.classList.add('hidden');
};
if (openVideoSafetyTips && videoSafetyTips) {
  openVideoSafetyTips.addEventListener('click', () => {
    videoSafetyTips.classList.remove('hidden');
    closeVideoSafetyTips?.focus();
  });
  closeVideoSafetyTips?.addEventListener('click', closeVideoSafetyModal);
  videoSafetyTips.addEventListener('click', (event) => {
    if (event.target === videoSafetyTips) closeVideoSafetyModal();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !videoSafetyTips.classList.contains('hidden')) {
      closeVideoSafetyModal();
      openVideoSafetyTips.focus();
    }
  });
}

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

const initialView = window.location.hash.replace("#", "") || document.body.dataset.initialView || "";
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
const saveButton = document.querySelector(".profile-page .save-button");
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
const fontSizeSelect = document.querySelector(".font-size-select");
const themePreferenceStorageKey = 'nexorev_theme_preferences';
const fontSizePreferenceStorageKey = 'nexorev_font_size_preferences';
const allowedFontSizes = ['normal', 'large', 'xlarge'];
const currentUser = document.body.dataset.currentUser?.toLowerCase() || '';

const getPreferenceMap = (storageKey) => {
  try {
    const rawValue = localStorage.getItem(storageKey);
    const parsedValue = rawValue ? JSON.parse(rawValue) : {};
    return parsedValue && typeof parsedValue === 'object' ? parsedValue : {};
  } catch (e) {
    console.warn(`No se pudo leer ${storageKey}`, e);
    return {};
  }
};

const savePreferenceMap = (storageKey, preferenceMap) => {
  try {
    localStorage.setItem(storageKey, JSON.stringify(preferenceMap));
  } catch (e) {
    console.warn(`No se pudo guardar ${storageKey}`, e);
  }
};

const getThemeForUser = () => {
  const themePreferences = getPreferenceMap(themePreferenceStorageKey);
  if (currentUser && themePreferences[currentUser] === 'dark') {
    return 'dark';
  }
  return localStorage.getItem('nexorev_dark_mode') === 'true' ? 'dark' : 'light';
};

const getFontSizeForUser = () => {
  const fontSizePreferences = getPreferenceMap(fontSizePreferenceStorageKey);
  const savedValue = currentUser ? fontSizePreferences[currentUser] : null;
  return allowedFontSizes.includes(savedValue) ? savedValue : 'normal';
};

const applyDarkMode = (enabled) => {
  document.documentElement.classList.toggle('dark-mode', enabled);
  if (document.body) {
    document.body.classList.toggle('dark-mode', enabled);
  }
  try {
    document.documentElement.setAttribute('data-theme', enabled ? 'dark' : 'light');
  } catch (e) {
    console.warn('No se pudo aplicar data-theme', e);
  }
};

const applyFontSize = (size) => {
  const selected = allowedFontSizes.includes(size) ? size : 'normal';
  document.documentElement.setAttribute('data-font-size', selected);
  if (fontSizeSelect) {
    fontSizeSelect.value = selected;
  }
};

const currentTheme = getThemeForUser();
const currentFontSize = getFontSizeForUser();
applyDarkMode(currentTheme === 'dark');
applyFontSize(currentFontSize);

if (darkModeSwitch) {
  darkModeSwitch.checked = currentTheme === 'dark';
  darkModeSwitch.addEventListener("change", (e) => {
    const modoOscuroActivo = e.target.checked;
    applyDarkMode(modoOscuroActivo);

    if (currentUser) {
      const themePreferences = getPreferenceMap(themePreferenceStorageKey);
      themePreferences[currentUser] = modoOscuroActivo ? 'dark' : 'light';
      savePreferenceMap(themePreferenceStorageKey, themePreferences);
    } else {
      try {
        localStorage.setItem('nexorev_dark_mode', String(modoOscuroActivo));
      } catch (error) {
        console.warn('No se pudo guardar modo oscuro en localStorage', error);
      }
    }
  });
}

if (fontSizeSelect) {
  fontSizeSelect.value = currentFontSize;
  fontSizeSelect.addEventListener('change', (e) => {
    const selectedValue = allowedFontSizes.includes(e.target.value) ? e.target.value : 'normal';
    applyFontSize(selectedValue);

    if (currentUser) {
      const fontSizePreferences = getPreferenceMap(fontSizePreferenceStorageKey);
      fontSizePreferences[currentUser] = selectedValue;
      savePreferenceMap(fontSizePreferenceStorageKey, fontSizePreferences);
    }
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

const securityTips = document.getElementById('securityTips');
const securityCriticalCheck = document.getElementById('securityCriticalCheck');
const securityTipsClose = document.getElementById('securityTipsClose');
if (securityTips && securityCriticalCheck && securityTipsClose) {
  securityCriticalCheck.addEventListener('change', () => {
    securityTipsClose.disabled = !securityCriticalCheck.checked;
  });
  securityTipsClose.addEventListener('click', () => {
    securityTips.classList.add('hidden');
    document.body.classList.remove('security-open');
  });
  if (!securityTips.classList.contains('hidden')) document.body.classList.add('security-open');
}

const enableBiometric = document.getElementById('enableBiometric');
if (enableBiometric) {
  enableBiometric.addEventListener('click', async () => {
    if (!window.PublicKeyCredential || !navigator.credentials) {
      showAlert('Biometría no disponible', 'Este dispositivo no ofrece biometría web. La validación por código de correo seguirá activa.');
      return;
    }
    try {
      const challenge = new Uint8Array(32);
      crypto.getRandomValues(challenge);
      await navigator.credentials.create({
        publicKey: {
          challenge,
          rp: { name: 'Nexo ReV' },
          user: { id: challenge, name: currentUser || 'usuario', displayName: currentUser || 'Usuario' },
          pubKeyCredParams: [{ type: 'public-key', alg: -7 }],
          authenticatorSelection: { authenticatorAttachment: 'platform', userVerification: 'required' },
          timeout: 60000,
        },
      });
      localStorage.setItem(`nexorev_biometric_${currentUser}`, 'enabled');
      showSuccess('Biometría configurada', 'La próxima validación intentará usar tu dispositivo.');
      enableBiometric.textContent = 'Configurada';
    } catch {
      showAlert('Validación no completada', 'La biometría falló o fue cancelada. Puedes continuar usando el código enviado por correo.');
    }
  });
}
