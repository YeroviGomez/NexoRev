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

const bindFavoriteButtons = () => {
  document.querySelectorAll('#videosView .favorite-btn[data-favorite-id]:not([data-bound])').forEach((button) => {
    button.dataset.bound = 'true';
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
};
bindFavoriteButtons();

const toggleAddPatientFormButton = document.getElementById('toggleAddPatientForm');
const doctorAddPatientForm = document.getElementById('doctorAddPatientForm');
if (toggleAddPatientFormButton && doctorAddPatientForm) {
  toggleAddPatientFormButton.addEventListener('click', () => {
    const isHidden = doctorAddPatientForm.hasAttribute('hidden');
    if (isHidden) {
      doctorAddPatientForm.removeAttribute('hidden');
      toggleAddPatientFormButton.textContent = 'Cerrar formulario';
      return;
    }
    doctorAddPatientForm.setAttribute('hidden', 'hidden');
    toggleAddPatientFormButton.textContent = 'Añadir paciente';
  });
}

const applyDoctorPatientFilters = () => {
  const filterSelect = document.getElementById('doctorPatientFilter');
  const sortSelect = document.getElementById('doctorPatientSort');
  const patientsList = document.querySelector('.patients-list');
  if (!filterSelect || !sortSelect || !patientsList) return;

  const rows = Array.from(patientsList.querySelectorAll('.patient-row[data-state]'));
  const filterValue = filterSelect.value;
  const sortValue = sortSelect.value;
  const filterStatus = document.getElementById('doctorFilterStatus');
  const filterLabels = {
    all: 'todos los pacientes',
    inicial: 'pacientes en etapa Inicial',
    en_proceso: 'pacientes En proceso',
    avanzado: 'pacientes en etapa Avanzado',
    finalizado: 'pacientes Finalizados',
  };

  const filteredRows = rows.filter((row) => filterValue === 'all' || row.dataset.state === filterValue);
  filteredRows.sort((a, b) => {
    const descending = sortValue.endsWith('_desc');
    let comparison = 0;
    if (sortValue.startsWith('edad')) {
      comparison = Number(a.dataset.age || 0) - Number(b.dataset.age || 0);
    } else if (sortValue.startsWith('nombre')) {
      comparison = String(a.dataset.name || '').localeCompare(String(b.dataset.name || ''));
    } else {
      comparison = Number(a.dataset.advance || 0) - Number(b.dataset.advance || 0);
    }
    return descending ? -comparison : comparison;
  });

  rows.forEach((row) => {
    const isVisible = filterValue === 'all' || row.dataset.state === filterValue;
    row.hidden = !isVisible;
    row.style.display = isVisible ? '' : 'none';
  });
  filteredRows.forEach((row) => patientsList.appendChild(row));
  rows.filter((row) => !filteredRows.includes(row)).forEach((row) => patientsList.appendChild(row));

  const emptyState = document.getElementById('doctorPatientsEmpty');
  if (emptyState) {
    emptyState.hidden = filteredRows.length > 0;
  }
  if (filterStatus) {
    filterStatus.textContent = filteredRows.length
      ? `Mostrando ${filterLabels[filterValue] || filterLabels.all}`
      : 'No hay pacientes en la etapa seleccionada';
  }
};

const doctorPatientFilter = document.getElementById('doctorPatientFilter');
const doctorPatientSort = document.getElementById('doctorPatientSort');
if (doctorPatientFilter) {
  doctorPatientFilter.addEventListener('change', applyDoctorPatientFilters);
}
if (doctorPatientSort) {
  doctorPatientSort.addEventListener('change', applyDoctorPatientFilters);
}

if (doctorPatientFilter && doctorPatientSort) {
  applyDoctorPatientFilters();
}

const doctorRecordView = document.getElementById('doctorRecordView');
const escapeRecordText = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#039;',
}[character]));

const loadPatientRecord = async (patientId) => {
  if (!doctorRecordView) return;
  try {
    const response = await fetch(`/principal/pacientes/${patientId}/`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'No se pudo cargar el expediente.');
    const patient = data.paciente;
    doctorRecordView.innerHTML = `
      <div class="section-head">
        <h2>${escapeRecordText(patient.nombre)}</h2>
        <span class="patient-state" style="--state-color: ${escapeRecordText(patient.color_estado)}">${escapeRecordText(patient.estado_display)}</span>
      </div>
      <div class="record-summary">
        <span>Edad<strong>${escapeRecordText(patient.edad)} años</strong></span>
        <span>Progreso<strong>${escapeRecordText(patient.avance)}%</strong></span>
        <span>Zona afectada<strong>${escapeRecordText(patient.zona_afectada || 'Sin registrar')}</strong></span>
      </div>
      <p><strong>Correo:</strong> ${escapeRecordText(patient.email)}</p>
      <h3>Notas de diagnóstico</h3>
      <p class="record-empty">No hay notas de diagnóstico asociadas a este paciente.</p>
      <h3>Gráfica de progreso</h3>
      <svg class="doctor-record-chart" viewBox="0 0 320 150" preserveAspectRatio="none" aria-label="Gráfica de progreso">
        <polyline points="${(patient.historial_avance || []).map((item, index, values) => `${16 + index * ((320 - 32) / Math.max(values.length - 1, 1))},${134 - (Number(item.avance) || 0) * 1.18}`).join(' ')}" fill="none" stroke="${escapeRecordText(patient.color_estado)}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></polyline>
      </svg>
      <h3>Historial de progreso</h3>
      <ul class="record-history">
        ${(patient.historial_avance || []).map((item) => `<li>${escapeRecordText(item.fecha)} · ${escapeRecordText(item.avance)}%</li>`).join('') || '<li>Sin historial registrado.</li>'}
      </ul>
      <h3>Sesiones</h3>
      <ul class="record-history">
        ${(patient.sesiones || []).map((session) => `<li>${escapeRecordText(session.fecha)} · ${escapeRecordText(session.objetivo)}${session.avance ? ` · ${escapeRecordText(session.avance)}` : ''}</li>`).join('') || '<li>Sin sesiones registradas.</li>'}
      </ul>
    `;
    showView('diagnostico');
    history.replaceState(null, "", '#diagnostico');
    doctorRecordView.scrollIntoView({
      behavior: document.documentElement.dataset.motion === 'off' ? 'auto' : 'smooth',
      block: 'start',
    });
  } catch (error) {
    console.error(error);
  }
};

document.querySelectorAll('.patient-card[data-patient-id]').forEach((card) => {
  const openRecord = () => loadPatientRecord(card.dataset.patientId);
  card.addEventListener('click', openRecord);
  card.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openRecord();
    }
  });
});

/* Keep compatibility with cards rendered by older cached templates. */
document.querySelectorAll('.patient-record-btn[data-patient-id]').forEach((button) => {
  button.addEventListener('click', () => loadPatientRecord(button.dataset.patientId));
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
  const completedRoutines = document.getElementById('completedRoutines');
  const homeProgressText = document.getElementById('homeProgressText');
  const homeProgressBar = document.getElementById('homeProgressBar');
  const serverCount = Number(completedRoutines?.dataset.serverCount || 0);
  const totalCount = serverCount + routines.length;
  if (completedRoutines) completedRoutines.textContent = String(totalCount);
  if (homeProgressText) homeProgressText.textContent = `${totalCount} rutinas completadas`;
  if (homeProgressBar) homeProgressBar.style.width = `${Math.min((totalCount / 6) * 100, 100)}%`;
  const historyList = document.getElementById('historyList');
  if (historyList && !historyList.dataset.serverHistory) {
    historyList.innerHTML = routines.length
      ? routines.map((routine) => `<li><span>${routine}</span><time>${new Date().toLocaleDateString('es-ES')}</time></li>`).join('')
      : '<li>Aún no has completado rutinas.</li>';
  }
};

const renderHistoryItems = (list, items, kind) => {
  if (!list) return;
  list.replaceChildren();
  if (!items.length) {
    const emptyState = document.createElement('li');
    emptyState.className = 'history-empty';
    emptyState.textContent = kind === 'completed'
      ? 'Aún no has completado rutinas.'
      : 'Aún no has visto videos.';
    list.append(emptyState);
    return;
  }

  items.forEach((item) => {
    const row = document.createElement('li');
    row.className = 'history-video-item';
    const thumbnail = document.createElement(item.replay_url ? 'a' : 'span');
    thumbnail.className = 'history-video-thumbnail';
    if (item.replay_url) {
      thumbnail.href = item.replay_url;
      thumbnail.setAttribute('aria-label', `Volver a ver ${item.title}`);
    } else {
      thumbnail.setAttribute('aria-hidden', 'true');
    }
    if (item.preview_image) {
      const image = document.createElement('img');
      image.src = item.preview_image;
      image.alt = `Miniatura de ${item.title}`;
      image.loading = 'lazy';
      thumbnail.append(image);
    } else {
      const placeholder = document.createElement('span');
      placeholder.setAttribute('aria-hidden', 'true');
      placeholder.textContent = '▶';
      thumbnail.append(placeholder);
    }

    const copy = document.createElement('div');
    copy.className = 'history-video-copy';
    const title = document.createElement(item.replay_url ? 'a' : 'span');
    title.className = 'history-video-title';
    title.textContent = item.title;
    if (item.replay_url) title.href = item.replay_url;
    const date = document.createElement('time');
    date.textContent = kind === 'completed'
      ? `${item.completed_at} · Completado`
      : `Visto el ${item.viewed_at}`;
    copy.append(title, date);
    row.append(thumbnail, copy);

    if (item.replay_url) {
      const replay = document.createElement('a');
      replay.className = 'history-replay-link';
      replay.href = item.replay_url;
      replay.textContent = 'Volver a ver';
      row.append(replay);
    }
    list.append(row);
  });
};

const updateHistoryPagination = (kind, pagination) => {
  const controls = document.querySelector(`[data-history-pagination="${kind}"]`);
  if (!controls) return;
  controls.dataset.page = String(pagination.page);
  controls.dataset.hasPrevious = String(pagination.has_previous);
  controls.dataset.hasNext = String(pagination.has_next);
  controls.querySelector('[data-page-direction="-1"]').disabled = !pagination.has_previous;
  controls.querySelector('[data-page-direction="1"]').disabled = !pagination.has_next;
  controls.querySelector('.history-page-number').textContent = `Página ${pagination.page}`;
};

const loadHistory = async (pages = {}) => {
  const historyList = document.getElementById('historyList');
  const recentVideosList = document.getElementById('recentVideosList');
  const completedRoutines = document.getElementById('completedRoutines');
  if (!historyList || !completedRoutines) return;
  try {
    const viewedControls = document.querySelector('[data-history-pagination="viewed"]');
    const completedControls = document.querySelector('[data-history-pagination="completed"]');
    const viewedPage = pages.viewedPage || viewedControls?.dataset.page || '1';
    const completedPage = pages.completedPage || completedControls?.dataset.page || '1';
    const params = new URLSearchParams({
      viewed_page: viewedPage,
      completed_page: completedPage,
    });
    const response = await fetch(`/principal/api/history/?${params}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    if (!response.ok) return;
    const data = await response.json();
    const mergedCount = Number(data.count || 0) + getCompletedRoutines().length;
    completedRoutines.dataset.serverCount = String(data.count || 0);
    completedRoutines.textContent = String(mergedCount);
    sessionStorage.removeItem('nexorev_history_dirty');
    document.querySelectorAll('.routine-button[data-video-id]').forEach((button) => {
      const completed = data.completed_video_ids.includes(button.dataset.videoId);
      button.classList.toggle('is-completed', completed);
      button.textContent = completed ? '✓ Completada' : 'Marcar rutina completada';
    });
    renderHistoryItems(historyList, data.completed_videos.items, 'completed');
    renderHistoryItems(recentVideosList, data.recent_videos.items, 'viewed');
    updateHistoryPagination('completed', data.completed_videos);
    updateHistoryPagination('viewed', data.recent_videos);
    const homeProgressText = document.getElementById('homeProgressText');
    const homeProgressBar = document.getElementById('homeProgressBar');
    if (homeProgressText) homeProgressText.textContent = `${mergedCount} rutinas completadas`;
    if (homeProgressBar) homeProgressBar.style.width = `${Math.min((mergedCount / 6) * 100, 100)}%`;
  } catch (error) {
    console.warn('No se pudo actualizar el historial', error);
  }
};

document.querySelectorAll('[data-history-tab]').forEach((tab) => {
  tab.addEventListener('click', () => {
    const selectedTab = tab.dataset.historyTab;
    document.querySelectorAll('[data-history-tab]').forEach((candidate) => {
      const isActive = candidate === tab;
      candidate.classList.toggle('is-active', isActive);
      candidate.setAttribute('aria-selected', String(isActive));
    });
    document.querySelectorAll('[data-history-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.historyPanel !== selectedTab;
    });
  });
});

document.querySelectorAll('[data-history-pagination] .history-page-button').forEach((button) => {
  button.addEventListener('click', () => {
    if (button.disabled) return;
    const controls = button.closest('[data-history-pagination]');
    const nextPage = Number(controls.dataset.page) + Number(button.dataset.pageDirection);
    const pageKey = controls.dataset.historyPagination === 'viewed' ? 'viewedPage' : 'completedPage';
    loadHistory({ [pageKey]: String(nextPage) });
  });
});

document.querySelectorAll('[data-nav="historial"]').forEach((trigger) => {
  trigger.addEventListener('click', loadHistory);
});
if (document.getElementById('historyList')) {
  loadHistory();
}

const videoSearch = document.getElementById('videoSearch');
const videoDifficulty = document.getElementById('videoDifficulty');
const videosEmpty = document.getElementById('videosEmpty');
let selectedCategory = 'todas';

const updateVideoCount = () => {
  const visible = document.querySelectorAll('#videoResults .video-card:not([hidden])').length;
  const videoCount = document.querySelector('.video-count');
  if (videoCount) videoCount.textContent = `Mostrando ${visible} videos`;
  if (videosEmpty) videosEmpty.hidden = visible > 0;
};

const filterVideos = () => {
  const query = videoSearch?.value.trim().toLowerCase() || '';
  const difficulty = videoDifficulty?.value || 'Todas';
  document.querySelectorAll('#videoResults .video-card').forEach((card) => {
    const matchesCategory = selectedCategory === 'todas' || card.dataset.category === selectedCategory;
    const matchesDifficulty = difficulty === 'Todas' || card.dataset.difficulty === difficulty;
    const matchesSearch = !query || card.dataset.title.includes(query);
    card.hidden = !(matchesCategory && matchesDifficulty && matchesSearch);
  });
  updateVideoCount();
};

document.querySelectorAll('.filter-chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    selectedCategory = chip.dataset.category.toLowerCase();
    document.querySelectorAll('.filter-chip').forEach((item) => {
      const isSelected = item === chip;
      item.classList.toggle('active', isSelected);
      item.setAttribute('aria-pressed', String(isSelected));
    });
    filterVideos();
  });
});

if (videoDifficulty) {
  videoDifficulty.addEventListener('change', filterVideos);
};
if (videoSearch) {
  videoSearch.addEventListener('input', filterVideos);
}
filterVideos();

const bindRoutineButtons = () => {
  document.querySelectorAll('.routine-button:not([data-bound])').forEach((button) => {
    button.dataset.bound = 'true';
    button.addEventListener('click', async () => {
      if (button.dataset.completeUrl) {
        if (button.disabled) return;
        button.disabled = true;
        try {
          const response = await fetch(button.dataset.completeUrl, {
            method: 'POST',
            headers: {
              'X-CSRFToken': getCookie('csrftoken') || document.querySelector('meta[name="csrf-token"]')?.content,
              'X-Requested-With': 'XMLHttpRequest',
            },
          });
          const data = await response.json();
          if (!response.ok || !data.success) throw new Error(data.error || 'No se pudo actualizar la rutina.');
          button.classList.toggle('is-completed', data.completed);
          button.textContent = data.completed ? '✓ Completada' : 'Marcar rutina completada';
          button.disabled = false;
          renderProgress();
          await loadHistory();
        } catch (error) {
          button.disabled = false;
          showAlert('Error', error.message);
        }
        return;
      }
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
};
bindRoutineButtons();

document.body.addEventListener('htmx:afterSwap', (event) => {
  if (event.target.id === 'videoResults') {
    bindFavoriteButtons();
    bindRoutineButtons();
    updateFavoriteButtons();
    filterVideos();
  }
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
const tutorialPrompt = document.getElementById("tutorialPrompt");
const tutorialPromptTitle = document.getElementById("tutorialPromptTitle");
const tutorialPromptDescription = document.getElementById("tutorialPromptDescription");
const tutorialPromptBasic = document.getElementById("tutorialPromptBasic");
const tutorialPromptPro = document.getElementById("tutorialPromptPro");
const tutorialPromptSkip = document.getElementById("tutorialPromptSkip");
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
const proTour = document.getElementById("proTour");
const proTourShade = document.getElementById("proTourShade");
const proTourMaskBackground = document.getElementById("proTourMaskBackground");
const proTourHole = document.getElementById("proTourHole");
const proTourStepBadge = document.getElementById("proTourStepBadge");
const proTourTitle = document.getElementById("proTourTitle");
const proTourDescription = document.getElementById("proTourDescription");
const proTourClose = document.getElementById("proTourClose");
const proTourPrev = document.getElementById("proTourPrev");
const proTourNext = document.getElementById("proTourNext");

function closeTutorialPrompt() {
  if (tutorialPrompt) {
    tutorialPrompt.classList.add("hidden");
    if (tutorialPrompt.open) tutorialPrompt.close();
  }
  document.body.classList.remove("tutorial-open");
}

let tutorialScope = null;

function openTutorialPrompt(scope = null) {
  if (!tutorialPrompt) return;
  closeTutorial();
  closeProTour();
  tutorialScope = scope;
  if (tutorialPromptTitle) {
    const sectionNames = {
      inicio: "Inicio",
      diagnostico: "Diagnóstico",
      videos: "Videos",
      favoritos: "Favoritos",
      historial: "Historial",
      perfil: "Perfil",
    };
    tutorialPromptTitle.textContent = scope
      ? `Guía de uso: ${sectionNames[scope] || "esta sección"}`
      : "¿Qué guía quieres consultar?";
  }
  if (tutorialPromptDescription) {
    tutorialPromptDescription.textContent = scope
      ? "Elige el nivel de detalle para recorrer únicamente esta sección. Puedes cerrar la guía o repetirla cuando quieras."
      : "Elige una guía para conocer las secciones y funciones de Nexo ReV. Puedes volver a abrirla en cualquier momento desde “Guía de uso”.";
  }
  tutorialPrompt.classList.remove("hidden");
  if (!tutorialPrompt.open) tutorialPrompt.showModal();
  document.body.classList.add("tutorial-open");
  tutorialPromptPro?.focus();
}

const tutorialSteps = [
  {
    icon: "pulse",
    title: "¡Bienvenido a Nexo ReV!",
    subtitle: "Tu plataforma de rehabilitación domiciliaria",
    boxTitle: "¿Qué puedes hacer?",
    items: [
      "Usa el menú lateral para cambiar de sección.",
      "Explora ejercicios y consulta tus videos vistos o completados.",
      "Configura tus datos y preferencias desde Perfil.",
      "Abre “Guía de uso” en cualquier momento para repetir este recorrido.",
    ],
    tip: true,
  },
  {
    view: "inicio",
    icon: "home",
    title: document.body.dataset.currentUserRole === "doctor" ? "Inicio - Panel de pacientes" : "Inicio - Tu espacio de rehabilitación",
    subtitle: document.body.dataset.currentUserRole === "doctor"
      ? "Organiza tus pacientes y accede a sus expedientes."
      : "Consulta tu avance y accede rápidamente a ejercicios e historial.",
    boxTitle: "Cómo funciona:",
    items: document.body.dataset.currentUserRole === "doctor"
      ? [
        "Filtra los pacientes por etapa y ordénalos con las listas desplegables.",
        "Selecciona un paciente para abrir su expediente.",
        "Usa “Añadir paciente” para asignar o registrar a una persona.",
        "Los accesos rápidos llevan a Videos y al Historial.",
      ]
      : [
        "Elige la zona afectada cuando el selector corporal esté habilitado; por ahora aparece como “Próximamente”.",
        "Consulta tu progreso, la gráfica de avance y las rutinas completadas hoy.",
        "Los accesos rápidos llevan a Videos y al Historial.",
      ],
  },
  {
    view: "diagnostico",
    icon: "pulse",
    title: document.body.dataset.currentUserRole === "doctor" ? "Diagnóstico - Expediente del paciente" : "Diagnóstico - Tu evaluación",
    subtitle: document.body.dataset.currentUserRole === "doctor"
      ? "Consulta el expediente del paciente seleccionado desde Inicio."
      : "Registra cómo te sientes y guarda los datos de tu evaluación.",
    boxTitle: "Cómo funciona:",
    items: document.body.dataset.currentUserRole === "doctor"
      ? [
        "Selecciona un paciente desde Inicio para consultar su expediente.",
        "El expediente muestra información y progreso del paciente.",
      ]
      : [
        "Indica tu nivel de dolor del 1 al 10 y responde las preguntas obligatorias.",
        "Agrega un comentario si necesitas compartir más información.",
        "Pulsa “Guardar” para registrar la evaluación o “Actualizar” para editarla.",
        "“Cancelar” limpia los datos que todavía no hayas guardado.",
      ],
  },
  {
    view: "videos",
    icon: "video",
    title: "Videos - Biblioteca de ejercicios",
    subtitle: "Encuentra ejercicios y revisa sus detalles antes de comenzar.",
    boxTitle: "Cómo funciona:",
    items: [
      "Busca ejercicios por nombre y filtra por zona o dificultad.",
      "Abre un video para ver la rutina y sus detalles.",
      "Pulsa el corazón de una tarjeta para guardar o quitar un favorito.",
      "Usa “Sorpréndeme” para cargar una sugerencia y consulta los tips de seguridad.",
      "Si vas a cargar un video, completa sus datos y pulsa “Subir video”.",
    ],
  },
  {
    view: "favoritos",
    icon: "heart",
    title: "Favoritos - Tus rutinas guardadas",
    subtitle: "Ten a mano los videos que quieras volver a consultar.",
    boxTitle: "Cómo funciona:",
    items: [
      "Guarda un ejercicio con el botón del corazón en Videos.",
      "Abre Favoritos desde el menú lateral para ver los videos guardados.",
      "Usa las flechas de cada tarjeta para cambiar su orden.",
      "Pulsa “Quitar todos” para vaciar la lista de favoritos.",
    ],
  },
  {
    view: "historial",
    icon: "history",
    title: "Historial - Tu progreso",
    subtitle: "Encuentra videos vistos y rutinas que ya completaste.",
    boxTitle: "Cómo funciona:",
    items: [
      "Cambia entre “Videos vistos” y “Rutinas completadas”.",
      "Usa “Anterior” y “Siguiente” para recorrer las páginas del historial.",
      "Pulsa “Volver a ver” para abrir un ejercicio otra vez.",
    ],
  },
  {
    view: "perfil",
    icon: "user",
    title: "Perfil - Personalización",
    subtitle: "Administra tus datos, preferencias y seguridad.",
    boxTitle: "Cómo funciona:",
    items: [
      "Edita tu información personal y guarda los cambios.",
      "Cambia o restablece tu foto de perfil.",
      "Ajusta el modo oscuro, el tamaño de letra y las animaciones.",
      "En Seguridad puedes configurar biometría y cambiar tu contraseña.",
    ],
  },
];

const tutorialIcons = {
  pulse: '<svg viewBox="0 0 64 64"><path d="M10 34h12l7-24 11 44 7-24h7" /></svg>',
  home: '<svg viewBox="0 0 64 64"><path d="M14 30 32 14l18 16v22H14V30Z" /><path d="M26 52V36h12v16" /></svg>',
  video: '<svg viewBox="0 0 64 64"><rect x="12" y="20" width="30" height="24" rx="5" /><path d="m42 28 12-7v22l-12-7" /></svg>',
  heart: '<svg viewBox="0 0 64 64"><path d="M54 24a12 12 0 0 0-20-9l-2 2-2-2a12 12 0 0 0-17 17l19 19 19-19a12 12 0 0 0 3-8Z" /></svg>',
  history: '<svg viewBox="0 0 64 64"><path d="M15 20v-9M15 20h9" /><path d="M15 20a21 21 0 1 1-3 17" /><path d="M32 22v12l9 5" /></svg>',
  user: '<svg viewBox="0 0 64 64"><circle cx="32" cy="18" r="10" /><path d="M16 52v-8c0-8 7-14 16-14s16 6 16 14v8" /></svg>',
};

let tutorialIndex = 0;
let activeTutorialSteps = tutorialSteps;

function renderTutorial() {
  const step = activeTutorialSteps[tutorialIndex];
  const isFirst = tutorialIndex === 0;
  const isLast = tutorialIndex === activeTutorialSteps.length - 1;

  tutorialStepBadge.textContent = `Paso ${tutorialIndex + 1} de ${activeTutorialSteps.length}`;
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
  tutorialDots.innerHTML = activeTutorialSteps
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
  activeTutorialSteps = tutorialScope
    ? tutorialSteps.filter((step) => step.view === tutorialScope)
    : tutorialSteps;
  if (!activeTutorialSteps.length) return;
  tutorialIndex = 0;
  renderTutorial();
  tutorialOverlay.classList.remove("hidden");
  if (!tutorialOverlay.open) tutorialOverlay.showModal();
  document.body.classList.add("tutorial-open");
}

function closeTutorial() {
  if (tutorialOverlay) {
    tutorialOverlay.classList.add("hidden");
    if (tutorialOverlay.open) tutorialOverlay.close();
  }
  document.body.classList.remove("tutorial-open");
}

const proTourSteps = [
  ...(document.body.dataset.currentUserRole === "doctor" ? [] : [
    {
    view: "inicio",
    selector: ".body-panel",
    title: "Selecciona la zona afectada",
    description: "Aquí aparecerá el selector de las partes del cuerpo. Actualmente muestra “Próximamente”, así que todavía no permite elegir una zona ni abre un formulario asociado.",
    },
    {
    view: "inicio",
    selector: ".selected-panel",
    title: "Zona seleccionada",
    description: "Este panel está pensado para mostrar la zona elegida. Como el selector corporal aún no está habilitado, por ahora indica que no hay una zona seleccionada.",
    },
  ]),
  {
    view: "inicio",
    selector: document.body.dataset.currentUserRole === "doctor" ? ".patients-panel" : ".progress-panel",
    fallbackSelector: document.body.dataset.currentUserRole === "doctor" ? ".patients-list" : ".home-side",
    title: document.body.dataset.currentUserRole === "doctor" ? "Inicio: pacientes asignados" : "Mi progreso y gráfica de avance",
    description: document.body.dataset.currentUserRole === "doctor"
    ? "En este panel puedes revisar la lista de pacientes, su etapa y porcentaje de avance."
    : "La escala muestra las etapas de recuperación y la gráfica representa el porcentaje de avance registrado a lo largo del tiempo.",
  },
  ...(document.body.dataset.currentUserRole === "doctor" ? [] : [
    {
    view: "inicio",
    selector: ".progress-summary",
    title: "Lee tu avance actual",
    description: "Debajo de la gráfica puedes consultar el porcentaje de avance registrado y la etapa actual de recuperación.",
    },
  ]),
  ...(document.body.dataset.currentUserRole === "doctor" ? [] : [
    {
    view: "inicio",
    selector: ".routine-panel",
    title: "Tu progreso de hoy",
    description: "Aquí ves el número de rutinas registradas como completadas y una barra visual que avanza al marcar rutinas en sus videos.",
    },
  ]),
  {
    view: "inicio",
    selector: document.body.dataset.currentUserRole === "doctor" ? ".doctor-filters" : ".quick-panel",
    title: document.body.dataset.currentUserRole === "doctor" ? "Accede a tus pacientes" : "Accesos rápidos",
    description: document.body.dataset.currentUserRole === "doctor"
    ? "Desde Inicio puedes filtrar la lista, abrir el expediente de un paciente o añadir uno."
    : "Estos botones te llevan directamente a la biblioteca de Videos y a tu Historial.",
  },
  {
    view: "inicio",
    selector: document.body.dataset.currentUserRole === "doctor" ? "#doctorPatientFilter" : ".quick-panel .quick-link",
    title: document.body.dataset.currentUserRole === "doctor" ? "Filtra pacientes por etapa" : "Abre Videos o Historial",
    description: document.body.dataset.currentUserRole === "doctor"
    ? "Filtra la lista según la etapa de progreso del paciente."
    : "Usa “Explorar videos de ejercicios” para buscar rutinas, o “Ver mi historial” para consultar tu actividad.",
  },
  ...(document.body.dataset.currentUserRole === "doctor" ? [
    {
      view: "inicio",
      selector: "#doctorPatientSort",
      title: "Ordena la lista de pacientes",
      description: "Elige si quieres ordenar por avance, edad o nombre, de mayor a menor o en orden alfabético.",
    },
  ] : []),
  ...(document.body.dataset.currentUserRole === "doctor" ? [
    {
      view: "inicio",
      selector: "#toggleAddPatientForm",
      title: "Añade o asigna un paciente",
      description: "Pulsa “Añadir paciente” para mostrar el formulario. Puedes asignar a un paciente registrado o introducir los datos de uno nuevo.",
    },
    {
      view: "inicio",
      selector: ".patients-list .patient-row",
      fallbackSelector: ".patients-list",
      title: "Abre el expediente de un paciente",
      description: "Selecciona una fila de paciente para consultar su expediente, progreso, notas y sesiones.",
    },
  ] : []),
  {
    view: "diagnostico",
    selector: document.body.dataset.currentUserRole === "doctor" ? "#doctorRecordView" : "#diagnosticForm .pain-scale",
    title: document.body.dataset.currentUserRole === "doctor" ? "Diagnóstico: consulta el expediente" : "Diagnóstico: registra el nivel de dolor",
    description: document.body.dataset.currentUserRole === "doctor"
      ? "Selecciona un paciente desde Inicio para cargar aquí la información de su expediente."
      : "Mueve la escala para indicar tu nivel de dolor. El valor seleccionado aparece junto a la pregunta.",
  },
  ...(document.body.dataset.currentUserRole === "doctor" ? [] : [
    {
      view: "diagnostico",
      selector: "#diagnosticForm .field-row",
      title: "Responde las preguntas de evaluación",
      description: "Completa las preguntas obligatorias sobre tu molestia. Puedes añadir información adicional en el campo de comentario.",
    },
    {
      view: "diagnostico",
      selector: "#diagnosticForm .diagnostic-actions",
      title: "Guarda tu evaluación",
      description: "Pulsa “Guardar” para registrar o “Actualizar” para editar la evaluación. “Cancelar” limpia los cambios no guardados.",
    },
  ]),
  {
    view: "videos",
    selector: "#videoSearch",
    title: "Videos: busca ejercicios",
    description: "Escribe una palabra en el buscador para filtrar la biblioteca por título, descripción, dificultad o zona.",
  },
  {
    view: "videos",
    selector: "#videosView .filter-chip",
    title: "Filtra por zona del cuerpo",
    description: "Elige una categoría para ver ejercicios de esa zona. Selecciona “Todas” para mostrar de nuevo todas las zonas.",
  },
  {
    view: "videos",
    selector: "#videoDifficulty",
    title: "Filtra por dificultad",
    description: "Selecciona principiante, intermedio o avanzado. Este filtro se combina con la búsqueda y la zona elegida.",
  },
  {
    view: "videos",
    selector: "#videoResults .video-card:not([hidden]) .video-play, #videoResults .video-card:not([hidden]) .video-open-link",
    fallbackSelector: "#videoResults",
    title: "Elige y reproduce un video",
    description: "Cada tarjeta muestra el título, descripción, zona y dificultad. Al continuar, abriremos el primer video disponible para mostrarte el reproductor y sus opciones.",
    openFirstVideo: true,
  },
  {
    view: "videos",
    selector: "#videoResults .favorite-btn",
    fallbackSelector: "#videoResults .video-grid",
    title: "Guarda un video en Favoritos",
    description: "Pulsa el corazón de una tarjeta para guardar el ejercicio; vuelve a pulsarlo para quitarlo. Lo encontrarás en la sección Favoritos.",
  },
  {
    view: "videos",
    selector: "#videoResults .routine-button",
    fallbackSelector: "#videoResults .video-grid",
    title: "Marca una rutina como completada",
    description: "Después de realizar el ejercicio, utiliza “Marcar rutina completada” en su tarjeta para registrarlo en el Historial.",
  },
  {
    view: "videos",
    selector: ".featured-video-zone",
    title: "Descubre una recomendación",
    description: "La zona destacada muestra un ejercicio sugerido. Pulsa “Sorpréndeme” para cargar otra recomendación.",
  },
  {
    view: "videos",
    selector: "#openVideoSafetyTips",
    title: "Consulta los tips de seguridad",
    description: "Antes de comenzar un ejercicio, abre esta opción y revisa las recomendaciones para realizarlo con seguridad.",
  },
  {
    view: "videos",
    selector: ".video-upload-heading",
    title: "Carga un video",
    description: "Completa el título, zona, dificultad y descripción; selecciona el archivo y pulsa “Subir video”. La miniatura es opcional.",
  },
  {
    view: "videos",
    selector: "#videoResults",
    title: "Explora más resultados",
    description: "Si hay más páginas de ejercicios, pulsa “Siguiente página” al final de la lista para cargar más videos.",
  },
  {
    view: "favoritos",
    selector: "#favoritesGrid .favorite-order-actions",
    fallbackSelector: "#favoritesGrid",
    title: "Favoritos: organiza tus ejercicios",
    description: "Aquí aparecen los videos que guardaste. En cada tarjeta puedes abrir la rutina o usar las flechas para cambiar el orden.",
  },
  {
    view: "favoritos",
    selector: "#clearFavorites",
    title: "Quita favoritos",
    description: "“Quitar todos” elimina todos los videos guardados de esta lista.",
  },
  {
    view: "historial",
    selector: ".history-tabs",
    title: "Historial: cambia de pestaña",
    description: "“Videos vistos” muestra lo que has reproducido; “Rutinas completadas” muestra los ejercicios que marcaste como realizados.",
  },
  {
    view: "historial",
    selector: "#completedVideosTab",
    title: "Consulta las rutinas completadas",
    description: "Pulsa esta pestaña para ver las rutinas que marcaste como realizadas y el total de ejercicios completados.",
  },
  {
    view: "historial",
    selector: "[data-history-panel='viewed'] .history-pagination",
    fallbackSelector: ".history-panel",
    title: "Recorre las páginas del historial",
    description: "Usa “Anterior” y “Siguiente” para consultar más videos vistos o rutinas completadas.",
  },
  {
    view: "historial",
    selector: "#viewedVideosPanel .history-replay-link",
    fallbackSelector: "#viewedVideosPanel .history-list",
    title: "Vuelve a reproducir un video",
    description: "Pulsa “Volver a ver” junto a un elemento del historial para abrir de nuevo ese ejercicio.",
  },
  {
    view: "perfil",
    selector: "#profileForm .profile-fields",
    title: "Perfil: actualiza tus datos",
    description: "Edita tu nombre, correo o teléfono. Al terminar, usa el botón “Guardar cambios” para guardar la información.",
  },
  {
    view: "perfil",
    selector: "#cambiarFotoButton",
    title: "Cambia tu foto de perfil",
    description: "Elige una imagen, ajústala en el editor y confirma para actualizar tu foto.",
  },
  {
    view: "perfil",
    selector: "#profileForm .save-button",
    title: "Guarda los cambios del perfil",
    description: "Después de modificar tus datos personales, pulsa “Guardar cambios” para aplicarlos.",
  },
  {
    view: "perfil",
    selector: "#perfilView .profile-form .preference-row .mini-switch",
    title: "Activa el modo oscuro",
    description: "El primer interruptor de Preferencias cambia entre la apariencia clara y el modo oscuro.",
  },
  {
    view: "perfil",
    selector: ".font-size-select",
    title: "Ajusta el tamaño del texto",
    description: "Usa esta lista para elegir un tamaño normal, grande o muy grande según prefieras.",
  },
  {
    view: "perfil",
    selector: "#motionPreferenceToggle",
    title: "Configura las animaciones",
    description: "Activa o desactiva los movimientos y transiciones de la interfaz desde este interruptor.",
  },
  {
    view: "perfil",
    selector: "#enableBiometric",
    title: "Seguridad de la cuenta",
    description: "Pulsa “Configurar” para registrar la validación biométrica si tu dispositivo la admite.",
  },
  {
    view: "perfil",
    selector: "#changePasswordButton",
    title: "Cambia tu contraseña",
    description: "Escribe tu contraseña actual, ingresa y confirma la nueva; luego pulsa “Cambiar contraseña”.",
  },
  {
    view: "perfil",
    selector: ".scroll-top-button",
    title: "Volver arriba",
    description: "Este botón flotante aparece al desplazarte hacia abajo. Púlsalo para regresar suavemente al inicio de la página.",
    showScrollTopButton: true,
  },
];

let proTourIndex = 0;
let activeProTourSteps = proTourSteps;
let isGlobalProTour = true;

function updateScrollTopButtonForTour(forceVisible = false) {
  const button = document.querySelector(".scroll-top-button");
  if (!button) return;

  const isVisible = forceVisible || window.scrollY > 300;
  button.classList.toggle("is-visible", isVisible);
  button.setAttribute("aria-hidden", String(!isVisible));
  button.tabIndex = isVisible ? 0 : -1;
}

function positionProTour() {
  if (!proTour || !proTour.open) return;

  const step = activeProTourSteps[proTourIndex];
  updateScrollTopButtonForTour(Boolean(step.showScrollTopButton));
  const target = document.querySelector(step.selector)
    || (step.fallbackSelector && document.querySelector(step.fallbackSelector))
    || document.querySelector(`[data-view="${step.view}"] .page-head`);
  if (!target || !proTourHole || !proTourShade || !proTourMaskBackground) return;

  const bounds = target.getBoundingClientRect();
  const padding = 8;
  const x = Math.max(8, bounds.left - padding);
  const y = Math.max(8, bounds.top - padding);
  const width = Math.min(window.innerWidth - x - 8, bounds.width + padding * 2);
  const height = Math.min(window.innerHeight - y - 8, bounds.height + padding * 2);
  proTourShade.setAttribute("viewBox", `0 0 ${window.innerWidth} ${window.innerHeight}`);
  proTourMaskBackground.setAttribute("width", String(window.innerWidth));
  proTourMaskBackground.setAttribute("height", String(window.innerHeight));
  proTourHole.setAttribute("x", String(x));
  proTourHole.setAttribute("y", String(y));
  proTourHole.setAttribute("width", String(Math.max(0, width)));
  proTourHole.setAttribute("height", String(Math.max(0, height)));

  if (window.innerWidth > 560) {
    const card = proTour.querySelector(".pro-tour-card");
    const cardBounds = card.getBoundingClientRect();
    const left = Math.min(
      Math.max(16, bounds.left + bounds.width / 2 - cardBounds.width / 2),
      window.innerWidth - cardBounds.width - 16,
    );
    const below = bounds.bottom + 18;
    const top = below + cardBounds.height <= window.innerHeight - 16
      ? below
      : Math.max(16, bounds.top - cardBounds.height - 18);
    card.style.left = `${left}px`;
    card.style.top = `${top}px`;
  }
}

function renderProTour() {
  if (!proTour || !proTourStepBadge || !proTourTitle || !proTourDescription) return;

  const step = activeProTourSteps[proTourIndex];
  showView(step.view);
  proTourStepBadge.textContent = `Paso ${proTourIndex + 1} de ${activeProTourSteps.length}`;
  proTourTitle.textContent = step.title;
  proTourDescription.textContent = step.description;
  proTourPrev.disabled = proTourIndex === 0;
  proTourNext.textContent = step.openFirstVideo && isGlobalProTour
    ? "Ver el primer video"
    : proTourIndex === activeProTourSteps.length - 1 ? "Finalizar" : "Siguiente";
  proTour.classList.remove("hidden");
  if (!proTour.open) proTour.showModal();

  const target = document.querySelector(step.selector)
    || (step.fallbackSelector && document.querySelector(step.fallbackSelector))
    || document.querySelector(`[data-view="${step.view}"] .page-head`);
  target?.scrollIntoView({ behavior: "smooth", block: "center" });
  window.requestAnimationFrame(positionProTour);
  proTourNext?.focus();
}

function closeProTour() {
  if (proTour) {
    proTour.classList.add("hidden");
    if (proTour.open) proTour.close();
  }
  updateScrollTopButtonForTour();
  document.body.classList.remove("tutorial-open");
}

function startProTour(scope = null, startIndex = 0) {
  closeTutorialPrompt();
  closeTutorial();
  isGlobalProTour = scope === null;
  activeProTourSteps = scope
    ? proTourSteps.filter((step) => step.view === scope)
    : proTourSteps;
  if (!activeProTourSteps.length || startIndex < 0 || startIndex >= activeProTourSteps.length) return;
  proTourIndex = startIndex;
  renderProTour();
}

function openFirstVideoFromTour() {
  const firstVideoLink = document.querySelector(
    "#videoResults .video-card:not([hidden]) .video-play[href], #videoResults .video-card:not([hidden]) .video-open-link[href]",
  ) || document.querySelector("#videoResults .video-play[href], #videoResults .video-open-link[href]");
  if (!firstVideoLink) return false;

  const videoUrl = new URL(firstVideoLink.href);
  videoUrl.searchParams.set("resume_app_tour", "1");
  videoUrl.searchParams.set("resume_step", String(proTourIndex + 1));
  window.location.assign(videoUrl);
  return true;
}

if (proTourPrev) {
  proTourPrev.addEventListener("click", () => {
    if (proTourIndex > 0) {
      proTourIndex -= 1;
      renderProTour();
    }
  });
}

if (proTourNext) {
  proTourNext.addEventListener("click", () => {
    const step = activeProTourSteps[proTourIndex];
    if (step.openFirstVideo && isGlobalProTour && openFirstVideoFromTour()) return;
    if (proTourIndex === activeProTourSteps.length - 1) {
      closeProTour();
      return;
    }
    proTourIndex += 1;
    renderProTour();
  });
}

proTourClose?.addEventListener("click", closeProTour);
tutorialPrompt?.addEventListener("close", () => {
  tutorialPrompt.classList.add("hidden");
  document.body.classList.remove("tutorial-open");
});
tutorialOverlay?.addEventListener("close", () => {
  tutorialOverlay.classList.add("hidden");
  document.body.classList.remove("tutorial-open");
});
proTour?.addEventListener("close", () => {
  proTour.classList.add("hidden");
  document.body.classList.remove("tutorial-open");
});

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
    if (tutorialIndex === activeTutorialSteps.length - 1) {
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
  openTutorial.addEventListener("click", () => openTutorialPrompt());
}
document.querySelectorAll("[data-tutorial-view]").forEach((button) => {
  button.addEventListener("click", () => openTutorialPrompt(button.dataset.tutorialView));
});
if (tutorialPromptBasic) {
  tutorialPromptBasic.addEventListener("click", () => {
    closeTutorialPrompt();
    openTutorialModal();
  });
}
if (tutorialPromptPro) {
  tutorialPromptPro.addEventListener("click", () => {
    startProTour(tutorialScope);
  });
}
if (tutorialPromptSkip) {
  tutorialPromptSkip.addEventListener("click", () => {
    closeTutorialPrompt();
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !tutorialOverlay.classList.contains("hidden")) {
    closeTutorial();
  }
  if (event.key === "Escape" && proTour && !proTour.classList.contains("hidden")) {
    closeProTour();
  }
});

window.addEventListener("resize", positionProTour);
window.addEventListener("scroll", positionProTour, { passive: true });

renderTutorial();

const tourResumeParams = new URLSearchParams(window.location.search);
if (tourResumeParams.get("resume_app_tour") === "1") {
  const resumeStep = Number(tourResumeParams.get("resume_step"));
  const cleanUrl = new URL(window.location.href);
  cleanUrl.searchParams.delete("resume_app_tour");
  cleanUrl.searchParams.delete("resume_step");
  window.history.replaceState(null, "", cleanUrl);
  if (Number.isInteger(resumeStep)) startProTour(null, resumeStep);
}

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
const profileForm = document.getElementById("profileForm");
const saveButton = document.querySelector(".profile-form .save-button");
const profileFeedback = document.getElementById("profileFeedback");
const profileFeedbackMessage = document.getElementById("profileFeedbackMessage");
const profileFeedbackClose = document.getElementById("profileFeedbackClose");
const changePasswordButton = document.getElementById("changePasswordButton");
const cambiarFotoButton = document.getElementById("cambiarFotoButton");
const resetAvatarButton = document.getElementById("resetAvatarButton");
const fotoInput = document.getElementById("fotoInput");
const avatarInitial = document.getElementById("avatarInitial");
const avatarImage = document.getElementById("avatarImage");
const avatarEditor = document.getElementById("avatarEditor");
const avatarCropFrame = document.getElementById("avatarCropFrame");
const avatarCropImage = document.getElementById("avatarCropImage");
const avatarZoom = document.getElementById("avatarZoom");
const acceptAvatarEdit = document.getElementById("acceptAvatarEdit");
const cancelAvatarEdit = document.getElementById("cancelAvatarEdit");
const cancelAvatarEditButton = document.getElementById("cancelAvatarEditButton");
const avatarEditorError = document.getElementById("avatarEditorError");

const nombreInput = document.getElementById("profileName");
const emailInput = document.getElementById("profileEmail");
const telefonoInput = document.getElementById("profilePhone");
const currentPasswordInput = document.getElementById("currentPassword");
const newPasswordInput = document.getElementById("newPassword");
const confirmPasswordInput = document.getElementById("confirmPassword");
let profileFeedbackTimeout;

function showProfileSuccess(message) {
  if (!profileFeedback || !profileFeedbackMessage) {
    console.warn("No se encontró el espacio para confirmar los cambios del perfil");
    return;
  }
  window.clearTimeout(profileFeedbackTimeout);
  profileFeedbackMessage.textContent = message;
  profileFeedback.hidden = false;
  profileFeedbackTimeout = window.setTimeout(() => {
    profileFeedback.hidden = true;
  }, 4500);
}

if (profileFeedbackClose && profileFeedback) {
  profileFeedbackClose.addEventListener("click", () => {
    window.clearTimeout(profileFeedbackTimeout);
    profileFeedback.hidden = true;
  });
}

// Funcionalidad para cambiar foto
if (cambiarFotoButton && fotoInput) {
  cambiarFotoButton.addEventListener("click", (e) => {
    e.preventDefault();
    fotoInput.click();
  });

  if (avatarEditor && avatarCropFrame && avatarCropImage && avatarZoom && acceptAvatarEdit) {
    let cropImageUrl = '';
    let imageScale = 1;
    let imageX = 0;
    let imageY = 0;
    let baseScale = 1;
    let dragState = null;

    const clampImagePosition = () => {
      const frameSize = avatarCropFrame.clientWidth;
      const imageWidth = avatarCropImage.clientWidth;
      const imageHeight = avatarCropImage.clientHeight;
      imageX = Math.max(frameSize - imageWidth, Math.min(0, imageX));
      imageY = Math.max(frameSize - imageHeight, Math.min(0, imageY));
      avatarCropImage.style.left = `${imageX}px`;
      avatarCropImage.style.top = `${imageY}px`;
    };

    const layoutCropImage = (keepCenter = false) => {
      const frameSize = avatarCropFrame.clientWidth;
      const previousScale = imageScale;
      const centerSourceX = keepCenter ? (frameSize / 2 - imageX) / previousScale : null;
      const centerSourceY = keepCenter ? (frameSize / 2 - imageY) / previousScale : null;
      imageScale = baseScale * Number(avatarZoom.value);
      avatarCropImage.style.width = `${avatarCropImage.naturalWidth * imageScale}px`;
      avatarCropImage.style.height = `${avatarCropImage.naturalHeight * imageScale}px`;
      imageX = keepCenter ? frameSize / 2 - centerSourceX * imageScale : (frameSize - avatarCropImage.clientWidth) / 2;
      imageY = keepCenter ? frameSize / 2 - centerSourceY * imageScale : (frameSize - avatarCropImage.clientHeight) / 2;
      clampImagePosition();
    };

    const closeAvatarEditor = () => {
      avatarEditor.hidden = true;
      avatarEditorError.hidden = true;
      avatarEditorError.textContent = '';
      fotoInput.value = '';
      if (cropImageUrl) URL.revokeObjectURL(cropImageUrl);
      cropImageUrl = '';
    };

    const uploadCroppedImage = async () => {
      const frameSize = avatarCropFrame.clientWidth;
      const sourceCropX = -imageX / imageScale;
      const sourceCropY = -imageY / imageScale;
      const sourceCropSize = frameSize / imageScale;
      const canvas = document.createElement('canvas');
      canvas.width = 512;
      canvas.height = 512;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('No se pudo preparar el recorte de la imagen.');

      context.drawImage(
        avatarCropImage,
        sourceCropX,
        sourceCropY,
        sourceCropSize,
        sourceCropSize,
        0,
        0,
        canvas.width,
        canvas.height,
      );
      const blob = await new Promise((resolve, reject) => {
        canvas.toBlob((result) => {
          if (result) resolve(result);
          else reject(new Error('No se pudo generar la imagen recortada.'));
        }, 'image/jpeg', 0.92);
      });

      const formData = new FormData();
      formData.append('foto', new File([blob], 'foto-perfil.jpg', { type: 'image/jpeg' }));
      const csrfToken = getCookie('csrftoken')
        || document.querySelector('meta[name="csrf-token"]')?.content;
      const response = await fetch('/principal/api/upload-photo/', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
        body: formData,
      });
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        if (response.redirected || response.status === 401) {
          throw new Error('Tu sesión expiró. Inicia sesión nuevamente y vuelve a intentar.');
        }
        if (response.status === 403) {
          throw new Error('La verificación de seguridad rechazó la solicitud. Recarga la página y vuelve a intentar.');
        }
        throw new Error(`El servidor respondió con un formato inesperado (HTTP ${response.status}).`);
      }
      const data = await response.json();
      if (!response.ok || !data.success || !data.foto_url) {
        throw new Error(data.error || 'No se pudo guardar la foto de perfil.');
      }

      avatarImage.src = `${data.foto_url}?t=${Date.now()}`;
      avatarInitial.hidden = true;
      avatarImage.hidden = false;
      if (resetAvatarButton) resetAvatarButton.disabled = false;
      showProfileSuccess('Foto actualizada correctamente.');
      closeAvatarEditor();
    };

    fotoInput.addEventListener('change', async () => {
      const archivo = fotoInput.files[0];
      if (!archivo) return;

      const tiposPermitidos = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
      if (!tiposPermitidos.includes(archivo.type)) {
        showAlert('Error', 'Solo se permiten imágenes (JPG, PNG, GIF, WebP).');
        fotoInput.value = '';
        return;
      }
      if (archivo.size > 5 * 1024 * 1024) {
        showAlert('Error', 'La imagen no debe superar 5 MB.');
        fotoInput.value = '';
        return;
      }

      if (cropImageUrl) URL.revokeObjectURL(cropImageUrl);
      cropImageUrl = URL.createObjectURL(archivo);
      avatarCropImage.src = cropImageUrl;
      avatarZoom.value = '1';
      avatarEditorError.hidden = true;
      avatarEditor.hidden = false;
      try {
        await avatarCropImage.decode();
        baseScale = Math.max(
          avatarCropFrame.clientWidth / avatarCropImage.naturalWidth,
          avatarCropFrame.clientHeight / avatarCropImage.naturalHeight,
        );
        layoutCropImage();
        acceptAvatarEdit.focus();
      } catch {
        closeAvatarEditor();
        showAlert('Error', 'No se pudo abrir la imagen seleccionada.');
      }
    });

    avatarZoom.addEventListener('input', () => layoutCropImage(true));
    avatarCropFrame.addEventListener('pointerdown', (event) => {
      dragState = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, imageX, imageY };
      avatarCropFrame.setPointerCapture(event.pointerId);
    });
    avatarCropFrame.addEventListener('pointermove', (event) => {
      if (!dragState || event.pointerId !== dragState.pointerId) return;
      imageX = dragState.imageX + event.clientX - dragState.x;
      imageY = dragState.imageY + event.clientY - dragState.y;
      clampImagePosition();
    });
    avatarCropFrame.addEventListener('pointerup', () => {
      dragState = null;
    });
    avatarCropFrame.addEventListener('pointercancel', () => {
      dragState = null;
    });

    [cancelAvatarEdit, cancelAvatarEditButton].forEach((button) => {
      button.addEventListener('click', closeAvatarEditor);
    });
    avatarEditor.addEventListener('click', (event) => {
      if (event.target === avatarEditor) closeAvatarEditor();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !avatarEditor.hidden) closeAvatarEditor();
    });
    acceptAvatarEdit.addEventListener('click', async () => {
      acceptAvatarEdit.disabled = true;
      acceptAvatarEdit.textContent = 'Guardando…';
      avatarEditorError.hidden = true;
      try {
        await uploadCroppedImage();
      } catch (error) {
        avatarEditorError.textContent = error instanceof Error ? error.message : String(error);
        avatarEditorError.hidden = false;
      } finally {
        acceptAvatarEdit.disabled = false;
        acceptAvatarEdit.textContent = 'Aceptar';
      }
    });
  }
}

if (resetAvatarButton) {
  resetAvatarButton.addEventListener('click', async () => {
    resetAvatarButton.disabled = true;
    const buttonText = resetAvatarButton.textContent;
    resetAvatarButton.textContent = 'Restableciendo…';
    try {
      const csrfToken = getCookie('csrftoken')
        || document.querySelector('meta[name="csrf-token"]')?.content;
      const response = await fetch('/principal/api/reset-photo/', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
      });
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        if (response.redirected || response.status === 401) {
          throw new Error('Tu sesión expiró. Inicia sesión nuevamente y vuelve a intentar.');
        }
        if (response.status === 403) {
          throw new Error('La verificación de seguridad rechazó la solicitud. Recarga la página y vuelve a intentar.');
        }
        throw new Error(`El servidor respondió con un formato inesperado (HTTP ${response.status}).`);
      }
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.error || 'No se pudo restablecer la foto.');
      }

      avatarImage.removeAttribute('src');
      avatarImage.hidden = true;
      avatarInitial.hidden = false;
      showProfileSuccess('Foto restablecida al avatar predeterminado.');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      showAlert('Error', message);
    } finally {
      resetAvatarButton.textContent = buttonText;
      resetAvatarButton.disabled = !avatarImage.src || avatarImage.hidden;
    }
  });
}

// ============== FUNCIONALIDAD DE MODO OSCURO ==============
const darkModeSwitch = document.querySelector(".preference-row:first-of-type .mini-switch input");
const fontSizeSelect = document.querySelector(".font-size-select");
const motionPreferenceToggle = document.getElementById('motionPreferenceToggle');
const allowedFontSizes = ['normal', 'large', 'xlarge'];
const currentUser = document.body.dataset.currentUser?.toLowerCase() || '';

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

const applyMotionPreference = (animationsDisabled) => {
  document.documentElement.setAttribute('data-motion', animationsDisabled ? 'off' : 'on');
};

const currentTheme = document.body.dataset.userTheme === 'dark' ? 'dark' : 'light';
let currentFontSize = allowedFontSizes.includes(document.body.dataset.userFontSize)
  ? document.body.dataset.userFontSize
  : 'normal';
let animationsDisabled = document.body.dataset.userMotionDisabled === 'true';
applyDarkMode(currentTheme === 'dark');
applyFontSize(currentFontSize);
applyMotionPreference(animationsDisabled);

const saveAppearancePreference = async (preference, value) => {
  const response = await fetch('/principal/api/update-appearance-preference/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken')
        || document.querySelector('meta[name="csrf-token"]')?.content,
    },
    body: JSON.stringify({ preference, value }),
  });
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    throw new Error(`El servidor respondió con un formato inesperado (HTTP ${response.status}).`);
  }
  const data = await response.json();
  if (!response.ok || !data.success) {
    throw new Error(data.error || 'No se pudo guardar la preferencia.');
  }
};

if (darkModeSwitch) {
  darkModeSwitch.checked = currentTheme === 'dark';
  darkModeSwitch.addEventListener("change", async (e) => {
    const enabled = e.currentTarget.checked;
    applyDarkMode(enabled);
    darkModeSwitch.disabled = true;
    try {
      await saveAppearancePreference('modo_oscuro', enabled);
    } catch (error) {
      darkModeSwitch.checked = !enabled;
      applyDarkMode(!enabled);
      showAlert('Error al guardar preferencia', error.message);
    } finally {
      darkModeSwitch.disabled = false;
    }
  });
}

if (fontSizeSelect) {
  fontSizeSelect.value = currentFontSize;
  fontSizeSelect.addEventListener('change', async (e) => {
    const previousValue = currentFontSize;
    const selectedValue = allowedFontSizes.includes(e.currentTarget.value) ? e.currentTarget.value : 'normal';
    fontSizeSelect.value = selectedValue;
    applyFontSize(selectedValue);
    fontSizeSelect.disabled = true;
    try {
      await saveAppearancePreference('tamano_letra', selectedValue);
      currentFontSize = selectedValue;
    } catch (error) {
      fontSizeSelect.value = previousValue;
      applyFontSize(previousValue);
      showAlert('Error al guardar preferencia', error.message);
    } finally {
      fontSizeSelect.disabled = false;
    }
  });
}

if (motionPreferenceToggle) {
  motionPreferenceToggle.checked = animationsDisabled;
  motionPreferenceToggle.addEventListener('change', async () => {
    const disabled = motionPreferenceToggle.checked;
    applyMotionPreference(disabled);
    motionPreferenceToggle.disabled = true;
    try {
      await saveAppearancePreference('desactivar_animaciones', disabled);
      animationsDisabled = disabled;
    } catch (error) {
      motionPreferenceToggle.checked = !disabled;
      applyMotionPreference(!disabled);
      showAlert('Error al guardar preferencia', error.message);
    } finally {
      motionPreferenceToggle.disabled = false;
    }
  });
}

if (changePasswordButton) {
  changePasswordButton.addEventListener("click", async (e) => {
    e.preventDefault();
    const currentPassword = currentPasswordInput.value;
    const newPassword = newPasswordInput.value;
    const confirmPassword = confirmPasswordInput.value;

    if (!currentPassword || !newPassword || !confirmPassword) {
      showAlert("Campos incompletos", "Por favor completa todos los campos de contraseña");
      return;
    }

    if (newPassword !== confirmPassword) {
      showAlert("Error", "Las nuevas contraseñas no coinciden");
      return;
    }

    if (newPassword.length < 8) {
      showAlert("Error", "La nueva contraseña debe tener al menos 8 caracteres");
      return;
    }

    if (currentPassword === newPassword) {
      showAlert("Error", "La nueva contraseña no puede ser igual a la actual");
      return;
    }

    try {
      const response = await fetch('/principal/api/change-password/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({ currentPassword, newPassword, confirmPassword }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        showAlert("Error", data.error || "No se pudo cambiar la contraseña");
        return;
      }
      showProfileSuccess("Contraseña cambiada correctamente.");
      currentPasswordInput.value = "";
      newPasswordInput.value = "";
      confirmPasswordInput.value = "";
    } catch (error) {
      showAlert("Error", "Error al cambiar la contraseña: " + error);
    }
  });
}

if (profileForm && saveButton) {
  profileForm.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && event.target instanceof HTMLInputElement) {
      event.preventDefault();
    }
  });

  saveButton.addEventListener('click', async () => {
    if (!profileForm.reportValidity()) return;
    saveButton.disabled = true;
    try {
      const response = await fetch('/principal/api/update-profile/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({
          nombre: nombreInput.value.trim(),
          email: emailInput.value.trim(),
          telefono: telefonoInput.value.trim(),
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        showAlert("Error", data.error || "No se pudieron guardar los cambios");
        return;
      }
      showProfileSuccess("Cambios del perfil guardados correctamente.");
      if (data.email && data.email.toLowerCase() !== currentUser) {
        setTimeout(() => window.location.reload(), 2600);
      }
    } catch (error) {
      showAlert("Error", "Error al guardar los cambios: " + error);
    } finally {
      saveButton.disabled = false;
    }
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
if (document.body.dataset.showInitialGuide === 'true') {
  if (securityTips && !securityTips.classList.contains('hidden') && securityTipsClose) {
    securityTipsClose.addEventListener('click', () => openTutorialPrompt('inicio'), { once: true });
  } else {
    openTutorialPrompt('inicio');
  }
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
