(() => {
  const page = document.querySelector('.mensajeria-page') || document.body;
  if (!page.dataset.userId) return;

  const userId = Number(page.dataset.userId);
  const userRole = page.dataset.role;
  const patientIdFromPage = page.dataset.pacienteId ? Number(page.dataset.pacienteId) : null;
  const messageList = document.getElementById('mensajeriaMessageList');
  const chatContent = document.getElementById('mensajeriaChatContent');
  const chatEmpty = document.getElementById('mensajeriaChatEmpty');
  const chatName = document.getElementById('mensajeriaChatName');
  const chatAvatar = document.getElementById('mensajeriaChatAvatar');
  const chatStatus = document.getElementById('mensajeriaChatStatus');
  const connectionStatus = document.getElementById('mensajeriaConnection');
  const conversationList = document.getElementById('mensajeriaConversationList');
  const search = document.getElementById('mensajeriaSearch');
  const compose = document.getElementById('mensajeriaCompose');
  const messageInput = document.getElementById('mensajeriaText');
  const unreadBadge = document.getElementById('mensajeriaTotalBadge');
  const sidebarBadges = document.querySelectorAll('.mensajeria-unread-badge');
  const conversations = new Map();
  const renderedMessages = new Map();
  let activePatientId = null;
  let socket = null;
  let reconnectDelay = 1000;
  let reconnectTimer = null;
  let loadingOlder = false;
  let olderCursor = null;
  let hasOlder = false;

  function apiUrl(template, id) {
    return template.replace('/0/', `/${id}/`);
  }

  function showStatus(message, isError) {
    if (!chatStatus) return;
    chatStatus.textContent = message;
    chatStatus.classList.toggle('is-error', Boolean(isError));
  }

  function setConnectionStatus(message, reconnecting) {
    if (!connectionStatus) return;
    connectionStatus.textContent = message;
    connectionStatus.classList.toggle('is-reconnecting', Boolean(reconnecting));
  }

  function updateUnread(payload) {
    if (!payload || payload.tipo !== 'no_leidos') return;
    const total = Math.max(0, Number(payload.total) || 0);
    for (const badge of sidebarBadges) {
      badge.textContent = total > 99 ? '99+' : String(total);
      badge.hidden = total === 0;
    }
    if (unreadBadge) {
      unreadBadge.textContent = total > 99 ? '99+' : String(total);
      unreadBadge.hidden = total === 0;
    }
    const counts = payload.por_conversacion || {};
    for (const [id, conversation] of conversations) {
      conversation.no_leidos = Number(counts[id]) || 0;
      updateConversationBadge(id);
    }
  }

  function updateConversationBadge(id) {
    const conversation = conversations.get(Number(id));
    const item = conversationList && conversationList.querySelector(
      `[data-paciente-id="${Number(id)}"]`,
    );
    if (!conversation || !item) return;
    const badge = item.querySelector('.mensajeria-conversation-badge');
    const count = Number(conversation.no_leidos) || 0;
    badge.textContent = count > 99 ? '99+' : String(count);
    badge.hidden = count === 0;
  }

  function formatTime(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return new Intl.DateTimeFormat('es', { hour: '2-digit', minute: '2-digit' }).format(date);
  }

  function initials(name) {
    return String(name || '')
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0])
      .join('')
      .toLocaleUpperCase('es');
  }

  function buildConversation(conversation) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'mensajeria-conversation';
    button.setAttribute('role', 'listitem');
    button.dataset.pacienteId = String(conversation.paciente_id);
    button.setAttribute('aria-pressed', 'false');

    const avatar = document.createElement('span');
    avatar.className = 'mensajeria-avatar';
    avatar.setAttribute('aria-hidden', 'true');
    avatar.textContent = initials(conversation.nombre);

    const copy = document.createElement('span');
    copy.className = 'mensajeria-conversation-copy';
    const name = document.createElement('span');
    name.className = 'mensajeria-conversation-name';
    name.textContent = conversation.nombre;
    const preview = document.createElement('span');
    preview.className = 'mensajeria-conversation-preview';
    preview.textContent = conversation.ultimo_mensaje || 'Aún no hay mensajes';
    copy.append(name, preview);

    const meta = document.createElement('span');
    meta.className = 'mensajeria-conversation-meta';
    const time = document.createElement('time');
    time.textContent = formatTime(conversation.ultimo_mensaje_fecha);
    if (conversation.ultimo_mensaje_fecha) time.dateTime = conversation.ultimo_mensaje_fecha;
    const badge = document.createElement('span');
    badge.className = 'mensajeria-conversation-badge';
    badge.setAttribute('aria-label', 'Mensajes sin leer');
    badge.hidden = true;
    meta.append(time, badge);
    button.append(avatar, copy, meta);

    button.addEventListener('click', () => openConversation(conversation.paciente_id));
    return button;
  }

  function renderConversationList() {
    if (!conversationList) return;
    conversationList.replaceChildren();
    for (const conversation of conversations.values()) {
      conversationList.append(buildConversation(conversation));
      updateConversationBadge(conversation.paciente_id);
    }
    const empty = document.getElementById('mensajeriaEmptyList');
    if (empty) empty.hidden = conversations.size > 0;
    filterConversations();
  }

  function filterConversations() {
    if (!conversationList || !search) return;
    const term = search.value.trim().toLocaleLowerCase('es');
    let visible = 0;
    for (const item of conversationList.querySelectorAll('.mensajeria-conversation')) {
      const conversation = conversations.get(Number(item.dataset.pacienteId));
      const match = !term || conversation.nombre.toLocaleLowerCase('es').includes(term);
      item.hidden = !match;
      if (match) visible += 1;
    }
    const noResults = document.getElementById('mensajeriaNoSearchResults');
    if (noResults) noResults.hidden = !term || visible > 0;
  }

  function dateLabel(value) {
    const date = new Date(value);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const difference = Math.round((today - day) / 86400000);
    if (difference === 0) return 'Hoy';
    if (difference === 1) return 'Ayer';
    return new Intl.DateTimeFormat('es', { day: 'numeric', month: 'long', year: 'numeric' }).format(date);
  }

  function createMessage(message) {
    const item = document.createElement('li');
    item.className = message.tipo_mensaje === 'sistema'
      ? 'mensajeria-system-message'
      : 'mensajeria-message';
    item.dataset.messageId = String(message.id);
    item.dataset.creadoEn = message.creado_en;
    if (message.tipo_mensaje === 'sistema') {
      item.textContent = message.texto;
      renderedMessages.set(Number(message.id), item);
      return item;
    }
    const own = Number(message.autor_id) === userId;
    if (own) item.classList.add('is-own');

    const text = document.createElement('p');
    text.className = 'mensajeria-message-text';
    text.textContent = message.texto;
    const meta = document.createElement('div');
    meta.className = 'mensajeria-message-meta';
    const time = document.createElement('time');
    time.textContent = formatTime(message.creado_en);
    time.dateTime = message.creado_en;
    meta.append(time);
    if (own) {
      const state = document.createElement('span');
      state.className = 'mensajeria-message-status';
      state.setAttribute('aria-label', message.leido_en ? 'Leído' : 'Enviado');
      state.title = message.leido_en ? 'Leído' : 'Enviado';
      state.textContent = message.leido_en ? '✓✓' : '✓';
      meta.append(state);
    }
    item.append(text, meta);
    renderedMessages.set(Number(message.id), item);
    return item;
  }

  function appendMessages(messages, prepend) {
    if (!messageList || !messages.length) return;
    let previousDate = null;
    const firstExistingMessage = prepend && messageList.querySelector(
      '.mensajeria-message, .mensajeria-system-message',
    );
    const existingFirstDate = firstExistingMessage
      ? new Date(firstExistingMessage.dataset.creadoEn).toDateString()
      : null;
    const nodes = [];
    for (const [index, message] of messages.entries()) {
      const day = new Date(message.creado_en).toDateString();
      const joiningExistingDay = (
        prepend
        && index === messages.length - 1
        && day === existingFirstDate
      );
      if (day !== previousDate && !joiningExistingDay) {
        const divider = document.createElement('li');
        divider.className = 'mensajeria-date-divider';
        divider.textContent = dateLabel(message.creado_en);
        divider.setAttribute('aria-label', dateLabel(message.creado_en));
        nodes.push(divider);
        previousDate = day;
      }
      nodes.push(createMessage(message));
    }
    if (prepend) {
      const oldHeight = messageList.scrollHeight;
      messageList.prepend(...nodes);
      messageList.scrollTop += messageList.scrollHeight - oldHeight;
    } else {
      messageList.append(...nodes);
      messageList.scrollTop = messageList.scrollHeight;
    }
  }

  async function fetchHistory(patientId, before) {
    const url = new URL(apiUrl(page.dataset.historialTemplate, patientId), window.location.origin);
    if (before) url.searchParams.set('antes', String(before));
    const response = await fetch(url, { credentials: 'same-origin' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'No se pudo cargar el historial.');
    return data;
  }

  async function markAsRead(patientId) {
    try {
      const response = await fetch(apiUrl(page.dataset.leidosTemplate, patientId), {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'X-CSRFToken': page.dataset.csrfToken,
          'X-Requested-With': 'XMLHttpRequest',
        },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'No se pudieron marcar los mensajes como leídos.');
      updateUnread(data);
    } catch (error) {
      noticeText.textContent = error.message || 'No se pudo descartar el aviso.';
      notice.setAttribute('role', 'alert');
    }
  }

  async function openConversation(patientId) {
    const conversation = conversations.get(Number(patientId));
    if (!conversation || !messageList) return;
    activePatientId = Number(patientId);
    page.classList.add('mensajeria-chat-open');
    if (chatEmpty) chatEmpty.hidden = true;
    if (chatContent) chatContent.hidden = false;
    if (chatName) chatName.textContent = conversation.nombre;
    if (chatAvatar) chatAvatar.textContent = initials(conversation.nombre);
    document.dispatchEvent(new CustomEvent('mensajeria-conversacion-abierta', {
      detail: {
        pacienteId: Number(conversation.paciente_id),
        nombre: conversation.nombre,
      },
    }));
    if (conversationList) {
      for (const item of conversationList.querySelectorAll('.mensajeria-conversation')) {
        const selected = Number(item.dataset.pacienteId) === activePatientId;
        item.classList.toggle('is-active', selected);
        item.setAttribute('aria-pressed', String(selected));
      }
    }
    messageList.replaceChildren();
    renderedMessages.clear();
    olderCursor = null;
    hasOlder = false;
    showStatus('', false);
    try {
      const data = await fetchHistory(activePatientId);
      if (activePatientId !== Number(patientId)) return;
      appendMessages(data.mensajes, false);
      olderCursor = data.siguiente_cursor;
      hasOlder = data.hay_mas;
      markAsRead(activePatientId);
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ tipo: 'abrir', paciente_id: activePatientId }));
        socket.send(JSON.stringify({ tipo: 'leer', paciente_id: activePatientId }));
      }
    } catch (error) {
      showStatus(error.message, true);
    }
  }

  async function loadOlderMessages() {
    if (!activePatientId || !hasOlder || loadingOlder || !olderCursor) return;
    loadingOlder = true;
    try {
      const data = await fetchHistory(activePatientId, olderCursor);
      appendMessages(data.mensajes, true);
      olderCursor = data.siguiente_cursor;
      hasOlder = data.hay_mas;
    } catch (error) {
      showStatus(error.message, true);
    } finally {
      loadingOlder = false;
    }
  }

  function updateLastMessage(message) {
    const conversation = conversations.get(Number(message.paciente_id));
    if (!conversation) return;
    conversation.ultimo_mensaje = message.texto;
    conversation.ultimo_mensaje_fecha = message.creado_en;
    renderConversationList();
  }

  function handleMessage(payload) {
    if (payload.tipo === 'no_leidos') {
      updateUnread(payload);
      return;
    }
    if (payload.tipo === 'mensaje') {
      updateLastMessage(payload);
      if (activePatientId === Number(payload.paciente_id)) {
        appendMessages([payload], false);
        if (Number(payload.autor_id) !== userId && socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ tipo: 'leer', paciente_id: activePatientId }));
        }
      }
      return;
    }
    if (payload.tipo === 'cambio_medico') {
      const notice = document.getElementById('medicalChangeNotice');
      const noticeText = document.getElementById('medicalChangeNoticeText');
      if (userRole === 'paciente' && notice && noticeText) {
        noticeText.textContent = `Tu médico ha cambiado. Ahora te atiende Dr. ${payload.doctor_nombre}.`;
        notice.hidden = false;
      }
      if (conversationList) loadConversations(true);
      if (Number(payload.paciente_id) === activePatientId && payload.mensaje) {
        const message = userRole === 'doctor' && payload.mensaje_medico
          ? payload.mensaje_medico
          : payload.mensaje;
        appendMessages([message], false);
        markAsRead(activePatientId);
      } else if (
        userRole === 'paciente'
        && page.classList.contains('mensajeria-page')
        && !patientIdFromPage
      ) {
        window.location.reload();
      }
      return;
    }
    if (payload.tipo === 'acceso_revocado') {
      const patientId = Number(payload.paciente_id);
      conversations.delete(patientId);
      renderConversationList();
      if (activePatientId === patientId) {
        activePatientId = null;
        if (messageList) messageList.replaceChildren();
        if (chatContent) chatContent.hidden = true;
        if (chatEmpty) chatEmpty.hidden = false;
        page.classList.remove('mensajeria-chat-open');
        showStatus('El paciente fue reasignado y ya no tienes acceso a su conversación.', true);
      }
      return;
    }
    if (payload.tipo === 'leido' && Number(payload.leido_por) !== userId) {
      if (Number(payload.paciente_id) !== activePatientId) return;
      for (const id of payload.mensajes_ids || []) {
        const item = renderedMessages.get(Number(id));
        if (!item || !item.classList.contains('is-own')) continue;
        const state = item.querySelector('.mensajeria-message-status');
        if (state) {
          state.textContent = '✓✓';
          state.setAttribute('aria-label', 'Leído');
          state.title = 'Leído';
        }
      }
      return;
    }
    if (payload.tipo === 'error') showStatus(payload.mensaje || 'No se pudo procesar el mensaje.', true);
  }

  function connectSocket() {
    if (page.dataset.enableSocket !== 'true') return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket = new WebSocket(`${protocol}//${window.location.host}/ws/mensajeria/`);
    socket.addEventListener('open', () => {
      reconnectDelay = 1000;
      setConnectionStatus('Conectado', false);
      if (activePatientId) {
        socket.send(JSON.stringify({ tipo: 'abrir', paciente_id: activePatientId }));
        socket.send(JSON.stringify({ tipo: 'leer', paciente_id: activePatientId }));
      } else if (patientIdFromPage) {
        socket.send(JSON.stringify({ tipo: 'abrir', paciente_id: patientIdFromPage }));
      }
    });
    socket.addEventListener('message', (event) => {
      try {
        handleMessage(JSON.parse(event.data));
      } catch {
        showStatus('Se recibió una respuesta inválida del servidor.', true);
      }
    });
    socket.addEventListener('close', (event) => {
      if (event.code === 4401 || event.code === 4403) {
        setConnectionStatus('Sin acceso', true);
        showStatus('Tu acceso a esta conversación ya no está disponible.', true);
        for (const control of compose ? compose.querySelectorAll('textarea, button') : []) {
          control.disabled = true;
        }
        return;
      }
      setConnectionStatus('Reconectando…', true);
      reconnectTimer = window.setTimeout(connectSocket, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 30000);
    });
    socket.addEventListener('error', () => setConnectionStatus('Reconectando…', true));
  }

  async function loadConversations(refresh = false) {
    if (!conversationList) return;
    try {
      let initial = [];
      if (refresh && page.dataset.conversacionesUrl) {
        const response = await fetch(page.dataset.conversacionesUrl, {
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'No se pudo actualizar la lista.');
        initial = data.conversaciones || [];
        conversations.clear();
      } else {
        const embedded = document.getElementById('mensajeria-conversaciones');
        if (embedded) initial = JSON.parse(embedded.textContent);
      }
      for (const conversation of initial) {
        conversations.set(Number(conversation.paciente_id), conversation);
      }
      renderConversationList();
    } catch {
      showStatus('No se pudo actualizar la lista de pacientes.', true);
    }
  }

  const notice = document.getElementById('medicalChangeNotice');
  const dismissNotice = document.getElementById('dismissMedicalChangeNotice');
  if (notice && dismissNotice) {
    dismissNotice.addEventListener('click', async () => {
      try {
        const response = await fetch(notice.dataset.dismissUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '',
            'X-Requested-With': 'XMLHttpRequest',
          },
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'No se pudo descartar el aviso.');
        notice.hidden = true;
      } catch (error) {
        showStatus(error.message, true);
      }
    });
  }

  if (search) search.addEventListener('input', filterConversations);
  if (conversationList) loadConversations();
  if (patientIdFromPage && messageList) {
    conversations.set(patientIdFromPage, { paciente_id: patientIdFromPage, nombre: chatName.textContent });
    openConversation(patientIdFromPage);
  }

  const backButton = document.getElementById('mensajeriaBackButton');
  if (backButton) {
    backButton.addEventListener('click', () => page.classList.remove('mensajeria-chat-open'));
  }
  if (messageList) {
    messageList.addEventListener('scroll', () => {
      if (messageList.scrollTop <= 24) loadOlderMessages();
    });
  }
  if (compose && messageInput) {
    compose.addEventListener('submit', (event) => {
      event.preventDefault();
      const texto = messageInput.value.trim();
      if (!texto || texto.length > 2000) {
        showStatus('Escribe un mensaje de hasta 2000 caracteres.', true);
        return;
      }
      if (!activePatientId || !socket || socket.readyState !== WebSocket.OPEN) {
        showStatus('No hay conexión. Espera a que se reconecte para enviar.', true);
        return;
      }
      socket.send(JSON.stringify({ tipo: 'enviar', paciente_id: activePatientId, texto }));
      messageInput.value = '';
      messageInput.style.height = 'auto';
      showStatus('', false);
    });
    messageInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        compose.requestSubmit();
      }
    });
    messageInput.addEventListener('input', () => {
      messageInput.style.height = 'auto';
      messageInput.style.height = `${Math.min(messageInput.scrollHeight, 128)}px`;
    });
  }

  connectSocket();
  window.addEventListener('beforeunload', () => {
    if (reconnectTimer) window.clearTimeout(reconnectTimer);
    if (socket) socket.close();
  }, { once: true });
})();
