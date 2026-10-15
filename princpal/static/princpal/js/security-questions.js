(() => {
  const form = document.getElementById('securityQuestionsForm');
  const list = document.getElementById('securityQuestionList');
  const optionsData = document.getElementById('security-question-options');
  const configuredData = document.getElementById('security-question-data');
  const feedback = document.getElementById('securityQuestionsFeedback');
  const addButton = document.getElementById('addSecurityQuestion');
  const saveButton = document.getElementById('saveSecurityQuestions');
  if (!form || !list || !optionsData || !configuredData || !feedback || !addButton || !saveButton) return;

  let predefined = [];
  let configured = [];
  try {
    predefined = JSON.parse(optionsData.textContent || '[]');
    configured = JSON.parse(configuredData.textContent || '[]');
  } catch (error) {
    console.error('No se pudieron cargar las preguntas de seguridad.', error);
    feedback.textContent = 'No se pudieron cargar tus preguntas. Actualiza la página e inténtalo nuevamente.';
    feedback.classList.add('is-error');
    feedback.hidden = false;
    return;
  }

  const showFeedback = (message, isError = false) => {
    feedback.textContent = message;
    feedback.classList.toggle('is-error', isError);
    feedback.hidden = false;
  };

  const createQuestionRow = (question = null) => {
    const row = document.createElement('fieldset');
    row.className = 'security-question-row';

    const legend = document.createElement('legend');
    legend.textContent = 'Pregunta de seguridad';

    const typeLabel = document.createElement('label');
    typeLabel.textContent = 'Tipo de pregunta';
    const typeSelect = document.createElement('select');
    typeSelect.required = true;
    typeSelect.className = 'security-question-type';
    typeSelect.add(new Option('Seleccionar de la lista', 'predefined'));
    typeSelect.add(new Option('Crear pregunta personalizada', 'custom'));
    typeLabel.append(typeSelect);

    const predefinedLabel = document.createElement('label');
    predefinedLabel.textContent = 'Pregunta predefinida';
    const predefinedSelect = document.createElement('select');
    predefinedSelect.required = true;
    predefinedSelect.className = 'security-question-predefined';
    predefinedSelect.add(new Option('Selecciona una pregunta', ''));
    predefined.forEach((item) => predefinedSelect.add(new Option(item.question, item.key)));
    predefinedLabel.append(predefinedSelect);

    const customLabel = document.createElement('label');
    customLabel.textContent = 'Tu pregunta personalizada';
    const customInput = document.createElement('input');
    customInput.type = 'text';
    customInput.maxLength = 255;
    customInput.minLength = 10;
    customInput.placeholder = 'Escribe una pregunta de al menos 10 caracteres';
    customInput.className = 'security-question-custom';
    customLabel.append(customInput);

    const answerLabel = document.createElement('label');
    answerLabel.textContent = 'Respuesta';
    const answerInput = document.createElement('input');
    answerInput.type = 'password';
    answerInput.required = true;
    answerInput.maxLength = 1024;
    answerInput.autocomplete = 'off';
    answerInput.placeholder = 'Escribe o renueva tu respuesta';
    answerInput.className = 'security-question-answer';
    answerLabel.append(answerInput);

    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.className = 'security-question-remove';
    removeButton.textContent = 'Quitar pregunta';
    removeButton.addEventListener('click', () => {
      if (list.querySelectorAll('.security-question-row').length <= 2) {
        showFeedback('Mantén al menos dos preguntas de seguridad configuradas.', true);
        return;
      }
      row.remove();
      showFeedback('Pregunta quitada. Guarda los cambios para actualizar tu configuración.');
    });

    const updateType = () => {
      const isCustom = typeSelect.value === 'custom';
      predefinedLabel.hidden = isCustom;
      customLabel.hidden = !isCustom;
      predefinedSelect.required = !isCustom;
      predefinedSelect.disabled = isCustom;
      customInput.required = isCustom;
      customInput.disabled = !isCustom;
    };
    typeSelect.addEventListener('change', updateType);

    if (question) {
      if (question.is_custom) {
        typeSelect.value = 'custom';
        customInput.value = question.question;
      } else {
        const match = predefined.find((item) => item.question === question.question);
        if (match) predefinedSelect.value = match.key;
        else {
          typeSelect.value = 'custom';
          customInput.value = question.question;
        }
      }
    }
    updateType();

    row.append(legend, typeLabel, predefinedLabel, customLabel, answerLabel, removeButton);
    list.append(row);
    return row;
  };

  configured.forEach((question) => createQuestionRow(question));
  if (list.childElementCount < 2) {
    while (list.childElementCount < 2) createQuestionRow();
  }

  addButton.addEventListener('click', () => {
    createQuestionRow();
    showFeedback('Completa la nueva pregunta y su respuesta antes de guardar.');
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const rows = [...list.querySelectorAll('.security-question-row')];
    if (rows.length < 2) {
      showFeedback('Configura al menos dos preguntas de seguridad.', true);
      return;
    }

    const questions = [];
    for (const row of rows) {
      const type = row.querySelector('.security-question-type').value;
      const answer = row.querySelector('.security-question-answer').value;
      if (!answer.trim()) {
        showFeedback('Cada pregunta requiere una respuesta.', true);
        row.querySelector('.security-question-answer').focus();
        return;
      }
      if (type === 'custom') {
        const question = row.querySelector('.security-question-custom').value.trim();
        if (question.length < 10) {
          showFeedback('Las preguntas personalizadas deben tener al menos 10 caracteres.', true);
          row.querySelector('.security-question-custom').focus();
          return;
        }
        questions.push({ type, question, answer });
      } else {
        const key = row.querySelector('.security-question-predefined').value;
        if (!key) {
          showFeedback('Selecciona una pregunta de la lista.', true);
          row.querySelector('.security-question-predefined').focus();
          return;
        }
        questions.push({ type, key, answer });
      }
    }

    saveButton.disabled = true;
    saveButton.textContent = 'Guardando…';
    try {
      const response = await fetch(form.dataset.url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value,
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ questions }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || 'No se pudieron guardar las preguntas.');

      rows.forEach((row) => {
        row.querySelector('.security-question-answer').value = '';
        row.querySelector('.security-question-answer').placeholder = 'Respuesta actualizada; vuelve a escribirla para cambiarla';
      });
      showFeedback(data.message);
    } catch (error) {
      showFeedback(error.message || 'No se pudieron guardar las preguntas. Inténtalo nuevamente.', true);
    } finally {
      saveButton.disabled = false;
      saveButton.textContent = 'Guardar preguntas';
    }
  });
})();
