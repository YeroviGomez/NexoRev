(() => {
  const dialog = document.getElementById('doctorFormModal');
  if (!dialog) return;

  const panels = [...dialog.querySelectorAll('[data-form-modal-panel]')];
  const title = document.getElementById('doctorFormModalTitle');
  const description = document.getElementById('doctorFormModalDescription');

  const openForm = (formName) => {
    const panel = panels.find((item) => item.dataset.formModalPanel === formName);
    if (!panel) {
      console.error(`No se encontró el formulario médico solicitado: ${formName}`);
      return;
    }

    panels.forEach((item) => { item.hidden = item !== panel; });
    title.textContent = panel.dataset.formTitle || '';
    description.textContent = panel.dataset.formDescription || '';
    if (!dialog.open) dialog.showModal();
    panel.querySelector('input:not([type="hidden"]):not(:disabled), select:not(:disabled), textarea')?.focus({
      preventScroll: true,
    });
  };

  panels.forEach((panel) => { panel.hidden = true; });

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-open-form-modal]');
    if (trigger) openForm(trigger.dataset.openFormModal);
    if (event.target === dialog) dialog.close();
    if (event.target.closest('[data-close-form-modal]')) dialog.close();
  });

  document.addEventListener('open-doctor-form-modal', (event) => {
    openForm(event.detail.formName);
  });

  dialog.addEventListener('close', () => {
    panels.forEach((panel) => { panel.hidden = true; });
  });
})();

(() => {
  const picker = document.getElementById('availablePatientsPicker');
  if (!picker) return;

  const toggle = document.getElementById('availablePatientsToggle');
  const list = document.getElementById('availablePatientsList');
  const search = document.getElementById('availablePatientsSearch');
  const status = document.getElementById('availablePatientsStatus');
  const empty = document.getElementById('availablePatientsEmpty');
  const results = document.getElementById('availablePatientsResults');
  const count = document.getElementById('availablePatientsCount');
  const pagination = document.getElementById('availablePatientsPagination');
  const previous = document.getElementById('availablePatientsPrevious');
  const next = document.getElementById('availablePatientsNext');
  const pageLabel = document.getElementById('availablePatientsPage');
  let page = 1;
  let requestController = null;
  let searchTimer = null;

  const setStatus = (message, isError = false) => {
    status.textContent = message;
    status.hidden = !message;
    status.classList.toggle('is-error', isError);
  };

  const makePatientRow = (patient) => {
    const item = document.createElement('li');
    item.className = 'available-patient-row';

    const avatar = document.createElement('span');
    avatar.className = 'available-patient-avatar';
    avatar.setAttribute('aria-hidden', 'true');
    avatar.textContent = patient.iniciales || '?';

    const details = document.createElement('div');
    details.className = 'available-patient-details';
    const name = document.createElement('strong');
    name.className = 'available-patient-name';
    name.textContent = patient.nombre;
    const attributes = document.createElement('p');
    attributes.textContent = [
      patient.edad ? `${patient.edad} años` : 'Edad no registrada',
      patient.zona_afectada || 'Zona no especificada',
      `Registro: ${patient.fecha_registro}`,
      patient.correo_enmascarado,
    ].join(' · ');
    details.append(name, attributes);

    const addButton = document.createElement('button');
    addButton.type = 'button';
    addButton.className = 'available-patient-add';
    addButton.textContent = 'Añadir a mis pacientes';
    addButton.setAttribute('aria-label', `Añadir a ${patient.nombre} a mis pacientes`);
    addButton.addEventListener('click', () => addPatient(patient, addButton));
    item.append(avatar, details, addButton);
    return item;
  };

  const loadPatients = async (requestedPage = 1) => {
    requestController?.abort();
    const termino = search.value.trim();
    if (termino && termino.length < 2) {
      requestController = null;
      results.replaceChildren();
      empty.hidden = true;
      pagination.hidden = true;
      list.setAttribute('aria-busy', 'false');
      setStatus('Escribe al menos 2 caracteres para buscar.');
      return null;
    }

    requestController = new AbortController();
    const controller = requestController;
    const url = new URL(picker.dataset.listUrl, window.location.origin);
    url.searchParams.set('q', termino);
    url.searchParams.set('page', String(requestedPage));
    list.setAttribute('aria-busy', 'true');
    results.replaceChildren();
    empty.hidden = true;
    pagination.hidden = true;
    setStatus('Cargando pacientes disponibles…');

    try {
      const response = await fetch(url, {
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'No se pudo cargar la lista.');

      page = data.page;
      count.textContent = String(data.available_count);
      data.items.forEach((patient) => results.append(makePatientRow(patient)));
      empty.textContent = data.available_count === 0
        ? 'No hay pacientes disponibles sin asignación'
        : 'No se encontraron pacientes con ese nombre.';
      empty.hidden = data.items.length > 0;
      pagination.hidden = data.results_count <= 20;
      previous.disabled = !data.has_previous;
      next.disabled = !data.has_next;
      pageLabel.textContent = `Página ${data.page}`;
      setStatus('');
      return data;
    } catch (error) {
      if (error.name === 'AbortError') return null;
      setStatus(error.message || 'No se pudo cargar la lista de pacientes.', true);
      return null;
    } finally {
      if (requestController === controller) {
        requestController = null;
        list.setAttribute('aria-busy', 'false');
      }
    }
  };

  const addPatient = async (patient, button) => {
    if (!window.confirm(`¿Añadir a ${patient.nombre} a tus pacientes?`)) return;
    button.disabled = true;
    button.textContent = 'Añadiendo…';
    const assignUrl = picker.dataset.assignUrlTemplate.replace(
      '/0/asignar/',
      `/${patient.id}/asignar/`,
    );

    try {
      const response = await fetch(assignUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          Accept: 'application/json',
          'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '',
        },
      });
      const data = await response.json();
      if (!response.ok) {
        const error = new Error(data.error || 'No se pudo añadir al paciente.');
        error.status = response.status;
        throw error;
      }

      count.textContent = String(data.available_count);
      setStatus('Paciente añadido. Actualizando tus pacientes asignados…');
      await loadPatients(page);
      window.setTimeout(() => window.location.assign('/principal/#inicio'), 650);
    } catch (error) {
      if (error.status === 409 || error.status === 404) {
        await loadPatients(page);
        setStatus(error.message, true);
      } else {
        setStatus(error.message || 'No se pudo añadir al paciente.', true);
      }
      button.disabled = false;
      button.textContent = 'Añadir a mis pacientes';
    }
  };

  toggle.addEventListener('click', () => {
    const expanded = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', String(!expanded));
    list.hidden = expanded;
    if (!expanded) loadPatients(1);
    else requestController?.abort();
  });

  search.addEventListener('input', () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => loadPatients(1), 250);
  });

  previous.addEventListener('click', () => {
    if (!previous.disabled) loadPatients(page - 1);
  });
  next.addEventListener('click', () => {
    if (!next.disabled) loadPatients(page + 1);
  });

  document.getElementById('doctorFormModal')?.addEventListener('close', () => {
    toggle.setAttribute('aria-expanded', 'false');
    list.hidden = true;
    requestController?.abort();
  });
})();
