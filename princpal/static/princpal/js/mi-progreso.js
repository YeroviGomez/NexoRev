(() => {
  const root = document.getElementById('patientProgressView');
  const dataElement = document.getElementById('patient-progress-data');
  if (!root || !dataElement) return;

  let progress;
  try {
    progress = JSON.parse(dataElement.textContent || '{}');
  } catch (error) {
    console.error('No se pudieron cargar los datos de progreso.', error);
    return;
  }

  const byId = (id) => document.getElementById(id);
  const setText = (id, value) => {
    const element = byId(id);
    if (element) element.textContent = String(value);
  };
  const percentage = (value) => `${Math.max(0, Math.min(100, Number(value) || 0))}%`;
  const formatDate = (value) => value
    ? new Intl.DateTimeFormat('es-SV', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value))
    : 'Aún no hay sesiones';

  const updateBar = (trackId, barId, value) => {
    const safeValue = Math.max(0, Math.min(100, Number(value) || 0));
    const track = byId(trackId);
    if (track) track.setAttribute('aria-valuenow', String(safeValue));
    const bar = byId(barId);
    if (bar) bar.style.width = percentage(safeValue);
  };

  const updateStages = (stage, label) => {
    setText('patientStageLabel', label || 'Etapa inicial');
    const stages = [...root.querySelectorAll('.patient-stage-line li')];
    const currentIndex = stages.findIndex((item) => item.dataset.stage === stage);
    stages.forEach((item, index) => {
      item.classList.toggle('is-complete', currentIndex >= 0 && index < currentIndex);
      item.classList.toggle('is-current', index === currentIndex);
      item.setAttribute('aria-current', index === currentIndex ? 'step' : 'false');
    });
  };

  const renderGoals = (data) => {
    const list = byId('patientGoalsList');
    list.replaceChildren();
    if (!data.goals.length) {
      const empty = document.createElement('li');
      empty.className = 'patient-progress-empty';
      empty.textContent = 'Tu fisioterapeuta aún no ha registrado objetivos.';
      list.append(empty);
    } else {
      data.goals.forEach((goal) => {
        const item = document.createElement('li');
        item.className = goal.completed ? 'is-complete' : 'is-pending';
        const icon = document.createElement('span');
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = goal.completed ? '✓' : '○';
        const name = document.createElement('span');
        name.textContent = goal.name;
        const status = document.createElement('small');
        status.textContent = goal.completed ? 'Completado' : 'En progreso';
        item.append(icon, name, status);
        list.append(item);
      });
    }
    setText('patientGoalsCount', `${data.goalCompleted} de ${data.goalTotal}`);
    setText('patientGoalsPercent', percentage(data.components.goals));
  };

  const renderRoutines = (data) => {
    const list = byId('patientRoutinesList');
    list.replaceChildren();
    if (!data.routines.length) {
      const empty = document.createElement('li');
      empty.className = 'patient-progress-empty';
      empty.textContent = 'Aún no tienes rutinas asignadas. Cuando tu fisioterapeuta te asigne una, aparecerá aquí.';
      list.append(empty);
      return;
    }

    data.routines.forEach((routine) => {
      const item = document.createElement('li');
      item.className = routine.completed ? 'is-complete' : 'is-pending';
      const name = document.createElement('span');
      name.textContent = routine.title;
      const date = document.createElement('time');
      date.dateTime = routine.date;
      date.textContent = new Intl.DateTimeFormat('es-SV', {
        day: 'numeric', month: 'short',
      }).format(new Date(`${routine.date}T12:00:00`));
      const status = document.createElement('small');
      status.textContent = routine.completed ? 'Completada' : 'Pendiente';
      item.append(name, date, status);
      list.append(item);
    });
  };

  const drawChart = (history) => {
    const svg = byId('patientRecoveryChart');
    const namespace = 'http://www.w3.org/2000/svg';
    const makeElement = (name, attributes = {}, text = '') => {
      const element = document.createElementNS(namespace, name);
      Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
      if (text) element.textContent = text;
      return element;
    };
    const width = 720;
    const height = 250;
    const left = 42;
    const right = 18;
    const top = 18;
    const bottom = 42;
    const plotHeight = height - top - bottom;
    const plotWidth = width - left - right;
    const points = [...history]
      .filter((point) => point && Number.isFinite(Number(point.avance)) && point.fecha)
      .sort((first, second) => new Date(first.fecha) - new Date(second.fecha));
    svg.replaceChildren();
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

    [0, 25, 50, 75, 100].forEach((tick) => {
      const y = top + plotHeight - (tick / 100) * plotHeight;
      svg.append(
        makeElement('line', { x1: left, y1: y, x2: width - right, y2: y, class: 'patient-chart-grid' }),
        makeElement('text', { x: left - 8, y: y + 4, 'text-anchor': 'end', class: 'patient-chart-label' }, `${tick}%`),
      );
    });

    if (!points.length) {
      svg.append(makeElement('text', {
        x: width / 2, y: height / 2, 'text-anchor': 'middle', class: 'patient-chart-empty',
      }, 'El historial aparecerá cuando se registre tu progreso.'));
      return;
    }
    const times = points.map((point) => new Date(point.fecha).getTime());
    const firstTime = Math.min(...times);
    const span = Math.max(Math.max(...times) - firstTime, 1);
    const coordinates = points.map((point, index) => ({
      x: points.length === 1 ? left + plotWidth / 2 : left + ((times[index] - firstTime) / span) * plotWidth,
      y: top + plotHeight - (Math.max(0, Math.min(100, Number(point.avance))) / 100) * plotHeight,
      point,
    }));
    const line = coordinates.map(({ x, y }) => `${x},${y}`).join(' ');
    svg.append(
      makeElement('polyline', { points: line, class: 'patient-chart-line' }),
      ...coordinates.map(({ x, y, point }) => {
        const circle = makeElement('circle', { cx: x, cy: y, r: 5, class: 'patient-chart-point' });
        circle.append(makeElement('title', {}, `${point.avance}% · ${formatDate(point.fecha)}`));
        return circle;
      }),
    );

    [coordinates[0], coordinates[coordinates.length - 1]].forEach(({ x, point }, index) => {
      const label = formatDate(point.fecha);
      svg.append(makeElement('text', {
        x, y: height - 12,
        'text-anchor': index ? 'end' : 'start',
        class: 'patient-chart-label',
      }, label));
    });
  };

  const render = (data) => {
    setText('patientRecoveryPercent', data.recoveryPercent);
    updateBar('patientRecoveryTrack', 'patientRecoveryBar', data.recoveryPercent);
    setText('recoveryGoalsPercent', percentage(data.components.goals));
    setText('recoverySessionsPercent', percentage(data.components.sessions));
    setText('recoveryRoutinesPercent', percentage(data.components.routines));
    setText('recoveryEvaluationsPercent', percentage(data.components.evaluations));
    updateStages(data.stage, data.stageLabel);

    setText('patientSessionsCompleted', data.sessionsCompleted);
    setText('patientSessionsPlanned', data.sessionsPlanned);
    setText('patientRoutinesCompleted', data.routinesCompleted);
    setText('patientRoutinesAssigned', data.routinesAssigned);
    setText('patientActivityStreak', data.streak);
    setText('patientLastSession', formatDate(data.lastSession));

    if (data.dailyHasAssignments) {
      setText('patientDailySummary', `${data.dailyRoutinesCompleted} de ${data.dailyRoutinesAssigned} rutinas completadas`);
      setText('patientDailyPercent', percentage(data.dailyPercent));
      setText('patientDailyNote', data.dailyPendingAssignments
        ? `Te quedan ${data.dailyPendingAssignments} rutinas por completar.`
        : '¡Completaste todas tus rutinas asignadas para hoy!');
      updateBar('patientDailyTrack', 'patientDailyBar', data.dailyPercent);
    } else {
      setText('patientDailySummary', 'No tienes rutinas asignadas para hoy.');
      setText('patientDailyPercent', '—');
      setText('patientDailyNote', 'Cuando tu fisioterapeuta programe una rutina, verás aquí tu avance diario.');
      updateBar('patientDailyTrack', 'patientDailyBar', 0);
    }

    renderGoals(data);
    renderRoutines(data);
    drawChart(data.progressHistory);
  };

  render(progress);

  let refreshing = false;
  const refreshProgress = async () => {
    if (refreshing) return;
    refreshing = true;
    try {
      const response = await fetch(root.dataset.refreshUrl, {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      });
      if (!response.ok) throw new Error(`No se pudo actualizar el progreso (${response.status}).`);
      const data = await response.json();
      if (!data.success || !data.progress) throw new Error(data.error || 'La respuesta de progreso no es válida.');
      progress = data.progress;
      render(progress);
      setText('patientProgressUpdated', 'Actualizado ahora');
    } catch (error) {
      console.error('No se pudo actualizar Mi Progreso.', error);
      setText('patientProgressUpdated', 'No se pudo actualizar');
    } finally {
      refreshing = false;
    }
  };

  window.setInterval(refreshProgress, 60000);
})();
