(() => {
  const root = document.getElementById('dashboardView');
  const dataElement = document.getElementById('dashboard-patient-data');
  if (!root || !dataElement) return;

  const byId = (id) => document.getElementById(id);
  const patientFilter = byId('dashboardPatientFilter');
  const statusFilter = byId('dashboardStatusFilter');
  const dateFrom = byId('dashboardDateFrom');
  const dateTo = byId('dashboardDateTo');
  const sortSelect = byId('dashboardSort');
  const patientRows = byId('dashboardPatientRows');
  const pendingRows = byId('dashboardPendingSessions');
  const rescheduleRows = byId('dashboardRescheduleRequests');
  const rescheduleEmpty = byId('dashboardRescheduleRequestsEmpty');
  const rescheduleData = byId('dashboard-reschedule-request-data');
  const routineTemplateDataElement = byId('routine-template-data');
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const colors = ['#119b72', '#3b82f6', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#ec4899', '#84cc16'];
  let patients = [];
  let rescheduleRequests = [];
  let routineTemplates = {};
  let refreshing = false;
  let profilePatientId = '';

  try {
    patients = JSON.parse(dataElement.textContent || '[]');
  } catch (error) {
    console.error('No se pudieron leer los datos del dashboard médico.', error);
  }
  try {
    rescheduleRequests = JSON.parse(rescheduleData?.textContent || '[]');
  } catch (error) {
    console.error('No se pudieron leer las solicitudes de reagendamiento.', error);
  }
  try {
    routineTemplates = JSON.parse(routineTemplateDataElement?.textContent || '{}');
  } catch (error) {
    console.error('No se pudieron leer las plantillas de rutina.', error);
  }

  const svgElement = (name, attributes = {}, text = '') => {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text) node.textContent = text;
    return node;
  };

  const formatNumber = (value) => Number(value).toLocaleString('es-SV', {
    maximumFractionDigits: 1,
  });

  const formatDate = (date) => date
    ? new Intl.DateTimeFormat('es-SV', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(date))
    : 'Sin registro';
  const formatDateTime = (date) => date
    ? new Intl.DateTimeFormat('es-SV', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(new Date(date))
    : 'Sin registro';

  const withinDateRange = (date) => {
    if (!date) return false;
    const key = date.slice(0, 10);
    return (!dateFrom.value || key >= dateFrom.value) && (!dateTo.value || key <= dateTo.value);
  };

  const patientEvaluations = (patient) => {
    const records = patient.evaluations.length
      ? patient.evaluations
      : patient.diagnosisPain !== null && patient.diagnosisDate
        ? [{ date: patient.diagnosisDate, pain: patient.diagnosisPain, metric: '', value: null, unit: '' }]
        : [];
    return records.filter((record) => withinDateRange(record.date));
  };

  const filteredPatients = () => patients
    .filter((patient) => patientFilter.value === 'all' || String(patient.id) === patientFilter.value)
    .filter((patient) => statusFilter.value === 'all'
      || (statusFilter.value === 'finished' ? patient.state === 'finalizado' : patient.state !== 'finalizado'))
    .map((patient) => ({
      ...patient,
      visibleProgress: patient.progressHistory
        .filter((point) => withinDateRange(point.fecha))
        .at(-1)?.avance ?? (dateFrom.value || dateTo.value ? null : patient.progress),
      visibleSessions: patient.sessions.filter((session) => withinDateRange(session.scheduledDate || session.date)),
      visibleEvaluations: patientEvaluations(patient),
      visibleGoals: patient.goals.filter((goal) => !dateTo.value || goal.createdAt.slice(0, 10) <= dateTo.value),
    }));

  const currentGoalValue = (patient, goal) => patient.visibleEvaluations
    .filter((evaluation) => evaluation.metric.trim().toLocaleLowerCase('es-SV') === goal.metric.trim().toLocaleLowerCase('es-SV')
      && evaluation.value !== null
      && evaluation.unit.trim().toLocaleLowerCase('es-SV') === goal.unit.trim().toLocaleLowerCase('es-SV'))
    .at(-1);

  const goalResults = (records) => records.flatMap((patient) => patient.visibleGoals.map((goal) => {
    const current = currentGoalValue(patient, goal);
    return {
      patient,
      goal,
      current,
      completed: Boolean(current && (goal.direction === 'menor'
        ? current.value <= goal.target
        : current.value >= goal.target)),
    };
  }));

  const updateSelectOptions = () => {
    const selectedPatient = patientFilter.value;
    patientFilter.replaceChildren(new Option('Todos los pacientes', 'all'));
    patients.forEach((patient) => patientFilter.add(new Option(patient.name, String(patient.id))));
    if (patients.some((patient) => String(patient.id) === selectedPatient)) {
      patientFilter.value = selectedPatient;
    }
    document.querySelectorAll('.dashboard-form [name="patient_id"]').forEach((select) => {
      const selected = profilePatientId || select.value;
      select.replaceChildren(new Option('Selecciona un paciente', ''));
      patients.forEach((patient) => select.add(new Option(patient.name, String(patient.id))));
      if (patients.some((patient) => String(patient.id) === selected)) select.value = selected;
      select.disabled = Boolean(profilePatientId) || patients.length === 0;
      select.closest('label')?.classList.toggle('profile-patient-selector', Boolean(profilePatientId));
      if (select.form?.id === 'sessionForm') {
        updateSessionGoalOptions(select.value, select.form.elements.namedItem('objetivo_terapeutico'));
      }
    });
  };

  const updateSessionGoalOptions = (patientId, goalSelect) => {
    const selectedRecord = patients.find((patient) => String(patient.id) === patientId);
    const goals = selectedRecord?.goals || [];
    goalSelect.replaceChildren(new Option(
      goals.length ? 'Selecciona un objetivo' : 'Este paciente aún no tiene objetivos',
      '',
    ));
    goals.forEach((goal) => goalSelect.add(new Option(goal.name, String(goal.id))));
    goalSelect.disabled = goals.length === 0;
  };

  const setProfilePatient = (patientId, patientName) => {
    profilePatientId = patientId || '';
    const context = byId('dashboardProfileContext');
    context.hidden = !profilePatientId;
    byId('dashboardProfilePatientName').textContent = patientName || '';
    root.classList.toggle('has-locked-profile-patient', Boolean(profilePatientId));
    updateSelectOptions();
    document.querySelectorAll('.dashboard-form [name="patient_id"]').forEach((select) => {
      select.dispatchEvent(new Event('change'));
    });
  };

  document.addEventListener('patient-profile-open', (event) => {
    setProfilePatient(event.detail.patientId, event.detail.patientName);
  });
  document.addEventListener('patient-profile-exit', () => setProfilePatient('', ''));
  document.addEventListener('patient-profile-action', (event) => {
    if (!profilePatientId) return;
    document.querySelector(`[data-nav="dashboard"]`)?.click();
    const form = byId(event.detail.formName);
    form?.scrollIntoView({
      behavior: document.documentElement.dataset.motion === 'off' ? 'auto' : 'smooth',
      block: 'center',
    });
    form?.querySelector('input:not([type="hidden"]), select:not([name="patient_id"]), textarea')?.focus({
      preventScroll: true,
    });
  });
  byId('dashboardProfileUnlock')?.addEventListener('click', () => {
    setProfilePatient('', '');
  });

  const drawDonut = (svgId, legendId, completed, total, completedLabel, pendingLabel) => {
    const svg = byId(svgId);
    const legend = byId(legendId);
    svg.replaceChildren();
    legend.replaceChildren();
    svg.setAttribute('viewBox', '0 0 180 180');
    const radius = 60;
    const circumference = 2 * Math.PI * radius;
    const percent = total ? Math.round((completed / total) * 100) : 0;
    svg.append(
      svgElement('circle', { cx: 90, cy: 90, r: radius, fill: 'none', stroke: '#e8edf0', 'stroke-width': 18 }),
      svgElement('circle', {
        cx: 90, cy: 90, r: radius, fill: 'none', stroke: '#14a477', 'stroke-width': 18,
        'stroke-dasharray': `${circumference * percent / 100} ${circumference}`,
        'stroke-linecap': 'round', transform: 'rotate(-90 90 90)',
      }),
      svgElement('text', { x: 90, y: 87, 'text-anchor': 'middle', class: 'donut-value' }, `${percent}%`),
      svgElement('text', { x: 90, y: 109, 'text-anchor': 'middle', class: 'donut-caption' }, `${completed} de ${total}`),
    );
    [
      { label: completedLabel, count: completed, className: 'legend-completed' },
      { label: pendingLabel, count: Math.max(total - completed, 0), className: 'legend-pending' },
    ].forEach((item) => {
      const line = document.createElement('div');
      line.className = 'donut-legend-item';
      const swatch = document.createElement('span');
      swatch.className = item.className;
      const label = document.createElement('span');
      label.textContent = item.label;
      const count = document.createElement('strong');
      count.textContent = String(item.count);
      line.append(swatch, label, count);
      legend.append(line);
    });
  };

  const drawPainChart = (records) => {
    const svg = byId('painChart');
    const legend = byId('painLegend');
    svg.replaceChildren();
    legend.replaceChildren();
    const datedRecords = records.map((patient) => ({
      ...patient,
      points: patient.visibleEvaluations.map((evaluation) => ({
        date: new Date(evaluation.date),
        pain: evaluation.pain,
      })).sort((left, right) => left.date - right.date),
    })).filter((patient) => patient.points.length);
    const width = 720;
    const height = 270;
    const left = 48;
    const right = 20;
    const top = 20;
    const bottom = 38;
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    if (!datedRecords.length) {
      svg.append(svgElement('text', { x: width / 2, y: height / 2, 'text-anchor': 'middle', class: 'chart-empty-label' }, 'Sin evaluaciones en este período'));
      return;
    }

    const times = datedRecords.flatMap((patient) => patient.points.map((point) => point.date.getTime()));
    const minimumTime = Math.min(...times);
    const maximumTime = Math.max(...times);
    const timeSpan = maximumTime - minimumTime;
    for (let pain = 0; pain <= 10; pain += 2) {
      const y = top + plotHeight - (pain / 10) * plotHeight;
      svg.append(
        svgElement('line', { x1: left, y1: y, x2: width - right, y2: y, class: 'chart-grid-line' }),
        svgElement('text', { x: left - 12, y: y + 4, 'text-anchor': 'end', class: 'chart-axis-label' }, pain),
      );
    }
    const dateFormatter = new Intl.DateTimeFormat('es-SV', {
      day: '2-digit', month: '2-digit', year: 'numeric',
    });
    datedRecords.forEach((patient, index) => {
      const color = colors[index % colors.length];
      const coordinates = patient.points.map((point, pointIndex) => ({
        x: timeSpan ? left + ((point.date.getTime() - minimumTime) / timeSpan) * plotWidth
          : left + (datedRecords.length > 1 ? pointIndex * plotWidth : plotWidth / 2),
        y: top + plotHeight - (point.pain / 10) * plotHeight,
      }));
      svg.append(svgElement('polyline', {
        points: coordinates.map((point) => `${point.x},${point.y}`).join(' '),
        fill: 'none', stroke: color, 'stroke-width': 3, 'stroke-linejoin': 'round', 'stroke-linecap': 'round',
      }));
      coordinates.forEach((point, pointIndex) => svg.append(svgElement('circle', {
        cx: point.x, cy: point.y, r: 4.5, fill: color, stroke: '#fff', 'stroke-width': 2,
      }, `${patient.name}: EVA ${patient.points[pointIndex].pain}, ${dateFormatter.format(patient.points[pointIndex].date)}`)));
      const label = document.createElement('span');
      label.className = 'chart-legend-item';
      label.style.setProperty('--legend-color', color);
      label.textContent = patient.name;
      legend.append(label);
    });
    const firstDate = new Date(minimumTime);
    const lastDate = new Date(maximumTime);
    svg.append(
      svgElement('text', { x: left, y: height - 7, class: 'chart-axis-label' }, dateFormatter.format(firstDate)),
      svgElement('text', { x: width - right, y: height - 7, 'text-anchor': 'end', class: 'chart-axis-label' }, dateFormatter.format(lastDate)),
    );
  };

  const drawProgressChart = (records) => {
    const svg = byId('progressChart');
    svg.replaceChildren();
    const ordered = [...records].sort((left, right) => (right.visibleProgress ?? -1) - (left.visibleProgress ?? -1)
      || left.name.localeCompare(right.name, 'es'));
    const width = 720;
    const rowHeight = 38;
    const top = 16;
    const height = Math.max(ordered.length * rowHeight + 30, 100);
    const labelWidth = 170;
    const barWidth = width - labelWidth - 72;
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    if (!ordered.length) {
      svg.append(svgElement('text', { x: width / 2, y: height / 2, 'text-anchor': 'middle', class: 'chart-empty-label' }, 'Sin pacientes para mostrar'));
      return;
    }
    ordered.forEach((patient, index) => {
      const y = top + index * rowHeight;
      const progress = Math.max(0, Math.min(100, patient.visibleProgress ?? 0));
      svg.append(
        svgElement('text', { x: labelWidth - 12, y: y + 17, 'text-anchor': 'end', class: 'chart-row-label' }, patient.name),
        svgElement('rect', { x: labelWidth, y, width: barWidth, height: 16, rx: 8, class: 'chart-bar-track' }),
        svgElement('rect', { x: labelWidth, y, width: barWidth * progress / 100, height: 16, rx: 8, fill: '#16a477' }),
        svgElement('text', { x: labelWidth + barWidth + 10, y: y + 14, class: 'chart-bar-value' }, patient.visibleProgress === null ? '—' : `${progress}%`),
      );
    });
  };

  const drawComparisonChart = (goals) => {
    const svg = byId('comparisonChart');
    svg.replaceChildren();
    const width = 900;
    const rowHeight = 48;
    const labelWidth = 230;
    const plotWidth = 450;
    const top = 16;
    const height = Math.max(goals.length * rowHeight + 24, 90);
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    if (!goals.length) {
      svg.append(svgElement('text', { x: width / 2, y: height / 2, 'text-anchor': 'middle', class: 'chart-empty-label' }, 'Agrega objetivos y evaluaciones clínicas para comparar'));
      return;
    }
    goals.forEach(({ patient, goal, current }, index) => {
      const y = top + index * rowHeight;
      const currentValue = current ? current.value : 0;
      const ratio = goal.target > 0 ? currentValue / goal.target
        : currentValue === 0 ? 1 : currentValue;
      const maxRatio = Math.max(ratio, 1);
      const scaledTargetWidth = plotWidth / maxRatio;
      const scaledCurrentWidth = Math.min(ratio, maxRatio) * scaledTargetWidth;
      const completed = current && (goal.direction === 'menor' ? currentValue <= goal.target : currentValue >= goal.target);
      const currentColor = completed ? '#16a477' : '#f59e0b';
      svg.append(
        svgElement('text', { x: labelWidth - 12, y: y + 20, 'text-anchor': 'end', class: 'chart-row-label' }, `${patient.name} · ${goal.name}`),
        svgElement('rect', { x: labelWidth, y, width: plotWidth, height: 10, rx: 5, class: 'chart-bar-track' }),
        svgElement('rect', { x: labelWidth, y, width: scaledCurrentWidth, height: 10, rx: 5, fill: currentColor }),
        svgElement('rect', { x: labelWidth, y: y + 15, width: plotWidth, height: 10, rx: 5, class: 'chart-bar-track' }),
        svgElement('rect', { x: labelWidth, y: y + 15, width: scaledTargetWidth, height: 10, rx: 5, fill: '#8b9aa5' }),
        svgElement('text', { x: labelWidth + plotWidth + 12, y: y + 9, class: 'chart-comparison-value' }, `Actual: ${current ? formatNumber(current.value) : 'Sin dato'} ${goal.unit}`),
        svgElement('text', { x: labelWidth + plotWidth + 12, y: y + 25, class: 'chart-comparison-value' }, `Meta: ${formatNumber(goal.target)} ${goal.unit}`),
      );
    });
  };

  const renderTable = (records, goals) => {
    patientRows.replaceChildren();
    const sorted = [...records];
    const isSessionDue = (session) => new Date(session.scheduledDate || session.date) <= new Date();
    const attendanceSessions = (patient) => patient.visibleSessions.filter(isSessionDue);
    const lastCompletedDate = (patient) => attendanceSessions(patient)
      .filter((session) => session.completed)
      .reduce((latest, session) => !latest || session.date > latest ? session.date : latest, '');
    const sessionCounts = (patient) => attendanceSessions(patient).reduce(
      (count, session) => count + Number(session.completed),
      0,
    );
    const sortValue = sortSelect.value;
    sorted.sort((left, right) => {
      if (sortValue === 'progress_asc') return (left.visibleProgress ?? 101) - (right.visibleProgress ?? 101)
        || left.name.localeCompare(right.name, 'es');
      if (sortValue === 'sessions_desc') return sessionCounts(right) - sessionCounts(left) || left.name.localeCompare(right.name, 'es');
      if (sortValue === 'sessions_asc') return sessionCounts(left) - sessionCounts(right) || left.name.localeCompare(right.name, 'es');
      if (sortValue === 'last_session_desc') return lastCompletedDate(right).localeCompare(lastCompletedDate(left))
        || left.name.localeCompare(right.name, 'es');
      return (right.visibleProgress ?? -1) - (left.visibleProgress ?? -1) || left.name.localeCompare(right.name, 'es');
    });

    const latestPain = (patient) => patient.visibleEvaluations.at(-1);
    sorted.forEach((patient) => {
      const completed = sessionCounts(patient);
      const total = attendanceSessions(patient).length;
      const lastSession = lastCompletedDate(patient);
      const pain = latestPain(patient);
      const row = document.createElement('tr');
      const name = document.createElement('th');
      name.scope = 'row';
      name.textContent = patient.name;
      const progress = document.createElement('td');
      const progressWrap = document.createElement('div');
      progressWrap.className = 'table-progress';
      const track = document.createElement('span');
      track.className = 'table-progress-track';
      const fill = document.createElement('span');
      fill.className = 'table-progress-fill';
      fill.style.width = `${Math.min(100, patient.visibleProgress ?? 0)}%`;
      track.append(fill);
      const percent = document.createElement('strong');
      percent.textContent = patient.visibleProgress === null ? 'Sin registro' : `${patient.visibleProgress}%`;
      progressWrap.append(track, percent);
      progress.append(progressWrap);
      const painCell = document.createElement('td');
      painCell.textContent = pain ? `${pain.pain} / 10` : 'Sin registro';
      if (pain) painCell.className = pain.pain >= 7 ? 'pain-critical' : pain.pain >= 4 ? 'pain-warning' : 'pain-positive';
      const sessions = document.createElement('td');
      sessions.textContent = `${completed} / ${total}`;
      const last = document.createElement('td');
      last.textContent = lastSession ? formatDate(lastSession) : 'Sin sesiones realizadas';
      row.append(name, progress, painCell, sessions, last);
      patientRows.append(row);
    });

    const pending = records.flatMap((patient) => patient.visibleSessions
      .filter((session) => session.status === 'programada')
      .map((session) => ({ patient, session })))
      .sort((left, right) => left.session.scheduledDate.localeCompare(right.session.scheduledDate));
    pendingRows.replaceChildren();
    pending.forEach(({ patient, session }) => {
      const row = document.createElement('tr');
      const patientName = document.createElement('th');
      patientName.scope = 'row';
      patientName.textContent = patient.name;
      const objective = document.createElement('td');
      objective.textContent = session.objective;
      const date = document.createElement('td');
      date.textContent = formatDateTime(session.scheduledDate);
      const status = document.createElement('td');
      status.textContent = 'Programada';
      const actionCell = document.createElement('td');
      const form = document.createElement('form');
      form.method = 'post';
      form.action = root.dataset.completeUrl.replace('/0/', `/${session.id}/`);
      form.className = 'session-complete-form';
      const csrf = document.createElement('input');
      csrf.type = 'hidden';
      csrf.name = 'csrfmiddlewaretoken';
      csrf.value = document.querySelector('meta[name="csrf-token"]')?.content || '';
      form.append(csrf);
      const addStatusButton = (value, label) => {
        const button = document.createElement('button');
        button.type = 'submit';
        button.name = 'estado';
        button.value = value;
        button.className = 'session-complete-button';
        button.textContent = label;
        form.append(button);
      };
      if (new Date(session.scheduledDate) <= new Date()) {
        addStatusButton('completada', 'Marcar completada');
        addStatusButton('no_asistio', 'No asistió');
      }
      if (session.status === 'programada') {
        addStatusButton('cancelada', 'Cancelar');
      }
      actionCell.append(form);
      row.append(patientName, objective, date, status, actionCell);
      pendingRows.append(row);
    });
    byId('dashboardEmpty').hidden = sorted.length > 0;
    byId('dashboardSessionsEmpty').hidden = pending.length > 0;
    byId('dashboardPatientCount').textContent = `${sorted.length} ${sorted.length === 1 ? 'paciente' : 'pacientes'}`;
  };

  const renderRoutineFeedback = (records) => {
    const tbody = byId('dashboardRoutineFeedback');
    const empty = byId('dashboardRoutineFeedbackEmpty');
    if (!tbody || !empty) return;
    const feedback = records.flatMap((patient) => (patient.routineFeedback || [])
      .filter((item) => withinDateRange(item.date))
      .map((item) => ({ ...item, patientName: patient.name })))
      .sort((left, right) => right.date.localeCompare(left.date));
    tbody.replaceChildren();
    feedback.forEach((item) => {
      const row = document.createElement('tr');
      [
        item.patientName,
        item.routine,
        item.dateDisplay,
        item.pain === null ? '—' : `${item.pain} / 10`,
        item.difficulty || '—',
        item.comment || '—',
      ].forEach((value, index) => {
        const cell = index === 0 ? document.createElement('th') : document.createElement('td');
        if (index === 0) cell.scope = 'row';
        cell.textContent = value;
        row.append(cell);
      });
      tbody.append(row);
    });
    empty.hidden = feedback.length > 0;
  };

  const renderRescheduleRequests = () => {
    if (!rescheduleRows || !rescheduleEmpty) return;
    rescheduleRows.replaceChildren();
    rescheduleRequests.forEach((request) => {
      const row = document.createElement('tr');
      const patientCell = document.createElement('th');
      patientCell.scope = 'row';
      const patientName = document.createElement('span');
      patientName.className = 'request-patient-name';
      patientName.textContent = request.patient;
      const sessionName = document.createElement('span');
      sessionName.className = 'request-session-name';
      sessionName.textContent = request.session;
      patientCell.append(patientName, sessionName);
      row.append(patientCell);
      [request.current_date, request.requested_date, request.reason].forEach((value, index) => {
        const cell = document.createElement('td');
        if (index === 2) cell.className = 'reschedule-reason-cell';
        cell.textContent = value;
        row.append(cell);
      });
      const actions = document.createElement('td');
      const controls = document.createElement('div');
      controls.className = 'reschedule-review-actions';
      const alternative = document.createElement('input');
      alternative.type = 'datetime-local';
      alternative.setAttribute('aria-label', 'Fecha alternativa propuesta');
      alternative.min = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
        .toISOString().slice(0, 16);
      const alternativeLabel = document.createElement('label');
      alternativeLabel.textContent = 'Proponer otra fecha';
      alternativeLabel.append(alternative);
      const response = document.createElement('input');
      response.type = 'text';
      response.maxLength = 1000;
      response.placeholder = 'Respuesta opcional';
      response.setAttribute('aria-label', 'Respuesta al paciente');
      const responseLabel = document.createElement('label');
      responseLabel.textContent = 'Respuesta al paciente';
      responseLabel.append(response);
      const approve = document.createElement('button');
      approve.type = 'button';
      approve.dataset.requestId = String(request.id);
      approve.dataset.requestAction = 'aprobar';
      approve.textContent = 'Aprobar';
      const reject = document.createElement('button');
      reject.type = 'button';
      reject.dataset.requestId = String(request.id);
      reject.dataset.requestAction = 'rechazar';
      reject.textContent = 'Rechazar';
      const propose = document.createElement('button');
      propose.type = 'button';
      propose.dataset.requestId = String(request.id);
      propose.dataset.requestAction = 'proponer';
      propose.textContent = 'Proponer fecha';
      const buttons = document.createElement('div');
      buttons.className = 'reschedule-review-buttons';
      buttons.append(approve, reject, propose);
      controls.append(alternativeLabel, responseLabel, buttons);
      actions.append(controls);
      row.append(actions);
      rescheduleRows.append(row);
    });
    rescheduleEmpty.hidden = rescheduleRequests.length > 0;
    const count = byId('rescheduleRequestCount');
    if (count) {
      count.textContent = `${rescheduleRequests.length} pendiente${rescheduleRequests.length === 1 ? '' : 's'}`;
    }
  };

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('button[data-request-action]');
    if (!button || !button.closest('#dashboardView, #doctorRecordView')) return;
    const controls = button.closest('.reschedule-review-actions');
    const alternative = controls.querySelector('input[type="datetime-local"]');
    const responseInput = controls.querySelector('input[type="text"]');
    if (button.dataset.requestAction === 'proponer' && !alternative.value) {
      alternative.focus();
      return;
    }
    button.disabled = true;
    const body = new URLSearchParams({
      accion: button.dataset.requestAction,
      respuesta: responseInput.value,
      fecha_alternativa: alternative.value,
    });
    try {
      const url = root.dataset.rescheduleReviewUrl
        .replace('/0/revisar/', `/${button.dataset.requestId}/revisar/`);
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '',
          'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        },
        body,
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || 'No se pudo actualizar la solicitud.');
      window.location.reload();
    } catch (error) {
      button.disabled = false;
      window.alert(error instanceof Error ? error.message : String(error));
    }
  });

  const render = () => {
    const records = filteredPatients();
    const goals = goalResults(records);
    const sessions = records.flatMap((patient) => patient.visibleSessions);
    const dueSessions = sessions.filter((session) => new Date(session.scheduledDate || session.date) <= new Date());
    const completedSessions = dueSessions.filter((session) => session.completed).length;
    const currentPain = records.map((patient) => patient.visibleEvaluations.at(-1)?.pain).filter(Number.isFinite);
    const painAverage = currentPain.length
      ? currentPain.reduce((total, pain) => total + pain, 0) / currentPain.length
      : null;
    const completedGoals = goals.filter((goal) => goal.completed).length;
    const progressValues = records.map((patient) => patient.visibleProgress).filter(Number.isFinite);
    const progressAverage = progressValues.length
      ? progressValues.reduce((total, progress) => total + progress, 0) / progressValues.length
      : 0;
    const activePatients = records.filter((patient) => patient.state !== 'finalizado').length;

    byId('kpiActivePatients').textContent = String(activePatients);
    byId('kpiProgress').textContent = progressValues.length ? formatNumber(progressAverage) : '—';
    byId('kpiPain').textContent = painAverage === null ? '—' : formatNumber(painAverage);
    const painKpi = byId('kpiPain').closest('.dashboard-kpi');
    painKpi.classList.toggle('kpi-pain-positive', painAverage !== null && painAverage < 4);
    painKpi.classList.toggle('kpi-pain-critical', painAverage !== null && painAverage >= 7);
    byId('kpiGoals').textContent = String(goals.length ? Math.round((completedGoals / goals.length) * 100) : 0);
    byId('kpiGoalCount').textContent = `${completedGoals} de ${goals.length}`;

    const chartPatients = records.map((patient) => ({ ...patient, visibleEvaluations: patient.visibleEvaluations }));
    drawPainChart(chartPatients);
    drawDonut('goalsChart', 'goalsLegend', completedGoals, goals.length, 'Completados', 'Pendientes');
    drawDonut('sessionsChart', 'sessionsLegend', completedSessions, dueSessions.length, 'Atendidas', 'Programadas vencidas');
    drawProgressChart(records);
    drawComparisonChart(goals);
    renderTable(records, goals);
    renderRoutineFeedback(records);
    renderRescheduleRequests();
  };

  document.querySelectorAll('.dashboard-form [name="patient_id"]').forEach((patientSelect) => {
    const form = patientSelect.form;
    patientSelect.addEventListener('change', () => {
      form.action = form.dataset.actionTemplate.replace('/0/', `/${patientSelect.value}/`);
      if (form.id === 'sessionForm') {
        updateSessionGoalOptions(
          patientSelect.value,
          form.elements.namedItem('objetivo_terapeutico'),
        );
      }
    });
    form.addEventListener('submit', (event) => {
      if (!patientSelect.value) {
        event.preventDefault();
        patientSelect.setCustomValidity('Selecciona un paciente asignado.');
        patientSelect.reportValidity();
      }
    });
    patientSelect.addEventListener('input', () => patientSelect.setCustomValidity(''));
  });

  const routineForm = byId('routineForm');
  const routineTemplateSelect = byId('routineTemplateSelect');
  const doseList = byId('routineDoseList');
  const scheduleSummary = byId('routineScheduleSummary');
  const assignmentMessage = byId('routineAssignmentMessage');
  const routineStart = routineForm.elements.namedItem('fecha_inicio');
  const routineEnd = routineForm.elements.namedItem('fecha_fin');
  const dayCheckboxes = [...routineForm.querySelectorAll('[name="dias_semana"]')];
  const formatLocalDate = (value) => {
    const [year, month, day] = value.split('-');
    return `${day}/${month}/${year}`;
  };
  const updateScheduleSummary = () => {
    const selectedDays = dayCheckboxes
      .filter((checkbox) => checkbox.checked)
      .map((checkbox) => Number(checkbox.value));
    const start = routineStart.value;
    const end = routineEnd.value;
    if (!start || !end || !selectedDays.length) {
      scheduleSummary.textContent = 'Selecciona fechas y días para ver el número de sesiones.';
      routineEnd.setCustomValidity('');
      return;
    }
    if (end < start) {
      routineEnd.setCustomValidity('La fecha de fin no puede ser anterior a la fecha de inicio.');
      scheduleSummary.textContent = 'La fecha de fin no puede ser anterior a la fecha de inicio.';
      return;
    }
    routineEnd.setCustomValidity('');
    const [startYear, startMonth, startDay] = start.split('-').map(Number);
    const [endYear, endMonth, endDay] = end.split('-').map(Number);
    const current = new Date(startYear, startMonth - 1, startDay);
    const last = new Date(endYear, endMonth - 1, endDay);
    let count = 0;
    while (current <= last) {
      const weekday = (current.getDay() + 6) % 7;
      if (selectedDays.includes(weekday)) count += 1;
      current.setDate(current.getDate() + 1);
    }
    scheduleSummary.textContent = `${count} sesiones entre ${formatLocalDate(start)} y ${formatLocalDate(end)}`;
  };
  const renderRoutineExercises = () => {
    doseList.replaceChildren();
    const template = routineTemplates[routineTemplateSelect.value];
    if (!template || !template.active || !template.exercises.length) {
      const empty = document.createElement('p');
      empty.className = 'routine-dose-empty';
      empty.textContent = template && !template.active
        ? 'Esta plantilla está desactivada y no se puede asignar.'
        : 'Selecciona una plantilla con ejercicios para indicar la dosis.';
      doseList.append(empty);
      return;
    }
    template.exercises.forEach((exercise) => {
      const card = document.createElement('section');
      card.className = 'routine-exercise-card';
      const title = document.createElement('h4');
      title.textContent = exercise.title;
      const fields = document.createElement('div');
      fields.className = 'routine-exercise-dose-row';
      const field = (labelText, suffix, type, value, placeholder) => {
        const label = document.createElement('label');
        label.textContent = labelText;
        const input = document.createElement(type === 'textarea' ? 'textarea' : 'input');
        input.name = `ejercicio_${exercise.id}_${suffix}`;
        if (type !== 'textarea') input.type = type;
        if (type === 'number') {
          input.min = suffix === 'series' || suffix === 'duracion' ? '1' : '0';
          if (value !== '') input.value = value;
          if (suffix === 'series') input.required = true;
        } else if (value) {
          input.value = value;
        }
        input.placeholder = placeholder;
        label.append(input);
        return label;
      };
      fields.append(
        field('Series', 'series', 'number', '3', 'Ej. 3'),
        field('Repeticiones', 'repeticiones', 'text', '10', 'Ej. 10 por lado'),
        field('Duración (minutos)', 'duracion', 'number', '', 'Ej. 15'),
      );
      const notes = field(
        'Notas del médico',
        'notas',
        'textarea',
        '',
        'Ej. Detener si el dolor supera 5/10',
      );
      card.append(title, fields, notes);
      doseList.append(card);
    });
  };

  const updateRoutineAction = () => {
    const patientSelect = routineForm.elements.namedItem('patient_id');
    if (patientSelect.value) {
      routineForm.action = routineForm.dataset.actionTemplate.replace('/0/', `/${patientSelect.value}/`);
    }
  };
  routineForm.elements.namedItem('patient_id').addEventListener('change', updateRoutineAction);
  routineTemplateSelect.addEventListener('change', renderRoutineExercises);
  [routineStart, routineEnd].forEach((input) => {
    input.min = root.dataset.today;
    input.addEventListener('input', updateScheduleSummary);
    input.addEventListener('change', updateScheduleSummary);
  });
  dayCheckboxes.forEach((checkbox) => checkbox.addEventListener('change', updateScheduleSummary));
  document.querySelectorAll('[data-weekday-preset]').forEach((button) => {
    button.addEventListener('click', () => {
      const presets = {
        weekdays: [0, 1, 2, 3, 4],
        alternate: [0, 2, 4],
        all: [0, 1, 2, 3, 4, 5, 6],
      };
      const days = presets[button.dataset.weekdayPreset];
      dayCheckboxes.forEach((checkbox) => {
        checkbox.checked = days.includes(Number(checkbox.value));
      });
      updateScheduleSummary();
    });
  });
  routineForm.addEventListener('input', (event) => {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
      event.target.setCustomValidity('');
    }
  });
  routineForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    assignmentMessage.hidden = true;
    assignmentMessage.classList.remove('is-error');
    const patientSelect = routineForm.elements.namedItem('patient_id');
    if (!patientSelect.value) {
      patientSelect.setCustomValidity('Selecciona un paciente asignado.');
      patientSelect.reportValidity();
      return;
    }
    if (!routineTemplateSelect.value || !routineTemplates[routineTemplateSelect.value]?.active
      || !routineTemplates[routineTemplateSelect.value]?.exercises.length) {
      routineTemplateSelect.setCustomValidity('Selecciona una plantilla activa que tenga ejercicios.');
      routineTemplateSelect.reportValidity();
      return;
    }
    if (!dayCheckboxes.some((checkbox) => checkbox.checked)) {
      window.alert('Selecciona al menos un día de la semana.');
      return;
    }
    updateScheduleSummary();
    if (routineEnd.validationMessage) {
      routineEnd.reportValidity();
      return;
    }
    for (const card of doseList.querySelectorAll('.routine-exercise-card')) {
      const repetitions = card.querySelector('[name$="_repeticiones"]');
      const duration = card.querySelector('[name$="_duracion"]');
      repetitions.setCustomValidity(
        !repetitions.value.trim() && (!duration.value || Number(duration.value) <= 0)
          ? 'Indica repeticiones o una duración mayor que 0.'
          : '',
      );
      if (!card.querySelector('[name$="_series"]').reportValidity()
        || !repetitions.reportValidity()
        || !duration.reportValidity()) return;
    }

    try {
      const response = await fetch(routineForm.action, {
        method: 'POST',
        headers: { Accept: 'application/json' },
        body: new FormData(routineForm),
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || 'No se pudo asignar la rutina.');
      window.alert(data.message);
      routineForm.reset();
      routineTemplateSelect.dispatchEvent(new Event('change'));
      updateScheduleSummary();
      updateRoutineAction();
    } catch (error) {
      assignmentMessage.textContent = error instanceof Error ? error.message : String(error);
      assignmentMessage.classList.add('is-error');
      assignmentMessage.hidden = false;
    }
  });

  const templateForm = byId('routineTemplateForm');
  const templateIdInput = byId('routineTemplateId');
  const templateNameInput = byId('routineTemplateName');
  const templateDescriptionInput = byId('routineTemplateDescription');
  const templateSaveButton = byId('routineTemplateSave');
  const templateCancelButton = byId('routineTemplateCancel');
  const videoCheckboxes = [...templateForm.querySelectorAll('[name="video_ids"]')];
  const clearTemplateEditor = () => {
    templateForm.reset();
    templateIdInput.value = '';
    templateSaveButton.textContent = 'Guardar plantilla';
    templateCancelButton.hidden = true;
    videoCheckboxes.forEach((checkbox) => {
      checkbox.checked = false;
      checkbox.closest('.routine-video-option').querySelector('.routine-video-order input').disabled = true;
    });
  };
  videoCheckboxes.forEach((checkbox) => {
    checkbox.addEventListener('change', () => {
      checkbox.closest('.routine-video-option').querySelector('.routine-video-order input').disabled = !checkbox.checked;
    });
  });
  document.querySelectorAll('[data-edit-template]').forEach((button) => {
    button.addEventListener('click', () => {
      const templateId = button.dataset.editTemplate;
      const template = routineTemplates[templateId];
      if (!template) return;
      clearTemplateEditor();
      templateIdInput.value = templateId;
      templateNameInput.value = template.name;
      templateDescriptionInput.value = template.description || '';
      template.exercises.forEach((exercise) => {
        const checkbox = videoCheckboxes.find((item) => item.value === exercise.video_id);
        if (!checkbox) return;
        checkbox.checked = true;
        const orderInput = checkbox.closest('.routine-video-option').querySelector('.routine-video-order input');
        orderInput.disabled = false;
        orderInput.value = String(exercise.order);
      });
      templateSaveButton.textContent = 'Guardar cambios';
      templateCancelButton.hidden = false;
      templateNameInput.focus();
    });
  });
  templateCancelButton.addEventListener('click', clearTemplateEditor);

  [patientFilter, statusFilter, dateFrom, dateTo, sortSelect].forEach((filter) => filter.addEventListener('change', render));
  byId('dashboardReset').addEventListener('click', () => {
    patientFilter.value = 'all';
    statusFilter.value = 'all';
    dateFrom.value = '';
    dateTo.value = '';
    sortSelect.value = 'progress_desc';
    render();
  });

  const updatePatients = (nextPatients) => {
    patients = nextPatients;
    updateSelectOptions();
    render();
  };

  updateSelectOptions();
  document.querySelectorAll('.dashboard-form [name="patient_id"]').forEach((patientSelect) => {
    patientSelect.dispatchEvent(new Event('change'));
  });
  routineTemplateSelect.dispatchEvent(new Event('change'));
  updateScheduleSummary();
  render();

  window.setInterval(async () => {
    if (refreshing) return;
    refreshing = true;
    try {
      const response = await fetch(root.dataset.refreshUrl, {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      });
      if (!response.ok) throw new Error(`No se pudo actualizar el dashboard (${response.status}).`);
      const data = await response.json();
      if (!Array.isArray(data.patients)) throw new Error('La respuesta de datos del dashboard no es válida.');
      if (Array.isArray(data.pending_reschedule_requests)) {
        rescheduleRequests = data.pending_reschedule_requests;
      }
      updatePatients(data.patients);
    } catch (error) {
      console.error('Error al actualizar los datos clínicos del dashboard.', error);
    } finally {
      refreshing = false;
    }
  }, 60000);
})();
