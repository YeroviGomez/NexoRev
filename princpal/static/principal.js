function saveDarkModePreference(isDark) {
  localStorage.setItem('nexorev_dark_mode', String(isDark));
}

function setDarkMode(enabled) {
  document.documentElement.classList.toggle('dark-mode', enabled);
  if (document.body) {
    document.body.classList.toggle('dark-mode', enabled);
  }
}

function applyStoredTheme() {
  try {
    const localValue = localStorage.getItem('nexorev_dark_mode');
    if (localValue !== null) {
      setDarkMode(localValue === 'true');
    }
  } catch (e) {
    console.warn('No se pudo leer localStorage para modo oscuro', e);
  }
}

function initDarkModeToggle() {
  const darkModeSwitch = document.querySelector('.preference-row:first-of-type .mini-switch input');
  if (!darkModeSwitch) {
    return;
  }

  applyStoredTheme();
  darkModeSwitch.checked = document.documentElement.classList.contains('dark-mode');

  darkModeSwitch.addEventListener('change', (event) => {
    const modoOscuroActivo = event.target.checked;
    setDarkMode(modoOscuroActivo);
    saveDarkModePreference(modoOscuroActivo);
  });
}

document.addEventListener('DOMContentLoaded', initDarkModeToggle);
