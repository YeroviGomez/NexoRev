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

sidebarToggle.addEventListener("click", () => {
  document.body.classList.toggle("sidebar-collapsed");
});

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

tutorialPrev.addEventListener("click", () => {
  if (tutorialIndex > 0) {
    tutorialIndex -= 1;
    renderTutorial();
  }
});

tutorialNext.addEventListener("click", () => {
  if (tutorialIndex === tutorialSteps.length - 1) {
    closeTutorial();
    return;
  }

  tutorialIndex += 1;
  renderTutorial();
});

tutorialClose.addEventListener("click", closeTutorial);
tutorialSkip.addEventListener("click", closeTutorial);
openTutorial.addEventListener("click", openTutorialModal);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !tutorialOverlay.classList.contains("hidden")) {
    closeTutorial();
  }
});

renderTutorial();
