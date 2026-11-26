(() => {
  const shell = document.getElementById('videollamadaShell');
  if (!shell || !window.NexoRevDevices) return;

  const role = shell.dataset.userRole;
  const setupDialog = document.getElementById('videollamadaSetup');
  const activeDialog = document.getElementById('videollamadaActive');
  const incomingNotice = document.getElementById('videollamadaIncoming');
  const globalStatus = document.getElementById('videollamadaGlobalStatus');
  const incomingName = document.getElementById('videollamadaIncomingName');
  const incomingCountdown = document.getElementById('videollamadaIncomingCountdown');
  const setupCountdown = document.getElementById('videollamadaSetupCountdown');
  const setupConfirm = document.getElementById('videollamadaSetupConfirm');
  const setupCancel = document.getElementById('videollamadaSetupCancel');
  const setupTitle = document.getElementById('videollamadaSetupTitle');
  const setupDescription = document.getElementById('videollamadaSetupDescription');
  const activeStatus = document.getElementById('videollamadaStatus');
  const peerName = document.getElementById('videollamadaPeerName');
  const localVideo = document.getElementById('videollamadaLocalVideo');
  const remoteVideo = document.getElementById('videollamadaRemoteVideo');
  const noRemote = document.getElementById('videollamadaNoRemote');
  const localCameraOff = document.getElementById('videollamadaLocalCameraOff');
  const remoteCameraOff = document.getElementById('videollamadaRemoteCameraOff');
  const localMicOff = document.getElementById('videollamadaLocalMicOff');
  const remoteMicOff = document.getElementById('videollamadaRemoteMicOff');
  const localAvatar = document.getElementById('videollamadaLocalAvatar');
  const localInitials = document.getElementById('videollamadaLocalInitials');
  const remoteAvatar = document.getElementById('videollamadaRemoteAvatar');
  const remoteInitials = document.getElementById('videollamadaRemoteInitials');
  const micButton = document.getElementById('videollamadaToggleMic');
  const cameraButton = document.getElementById('videollamadaToggleCamera');
  const activeStage = activeDialog.querySelector('.videollamada-video-stage');
  const devices = window.NexoRevDevices;
  let socket = null;
  let reconnectDelay = 1000;
  let reconnectTimer = null;
  let signalingStatusTimer = null;
  let countdownTimer = null;
  let disconnectTimer = null;
  let setupMode = null;
  let pendingIncoming = null;
  let activeCall = null;
  let connectionId = null;
  const pendingSignals = [];
  let peerConnection = null;
  let peerConnectionCreation = null;
  let remoteStream = new MediaStream();
  let remoteVideoTrackReceived = false;
  let remoteCameraActive = null;
  let remoteMicrophoneActive = null;
  let pendingCandidates = [];
  let restartAttempted = false;

  const showNotice = (message, isError = false) => {
    globalStatus.textContent = message;
    globalStatus.classList.toggle('is-error', isError);
    globalStatus.hidden = !message;
  };

  const showSignalingStatus = (message, isError = false) => {
    if (signalingStatusTimer) window.clearTimeout(signalingStatusTimer);
    showNotice(message, isError);
    if (!isError && message) {
      signalingStatusTimer = window.setTimeout(() => {
        if (socket?.readyState === WebSocket.OPEN && !activeCall) showNotice('');
        signalingStatusTimer = null;
      }, 3000);
    }
  };

  const showError = (message) => {
    devices.setStatus(message, true);
    showNotice(message, true);
  };

  const initialsFor = (name) => (name || '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toLocaleUpperCase())
    .join('') || 'NR';

  const setProfile = (image, initials, name, url) => {
    initials.textContent = initialsFor(name);
    initials.hidden = false;
    image.hidden = true;
    image.onerror = () => {
      image.hidden = true;
      initials.hidden = false;
    };
    image.onload = () => {
      image.hidden = false;
      initials.hidden = true;
    };
    if (url) image.src = url;
    else image.removeAttribute('src');
  };

  const updateLocalMediaIndicators = () => {
    const videoTrack = devices.stream().getVideoTracks()[0];
    const audioTrack = devices.stream().getAudioTracks()[0];
    const cameraEnabled = Boolean(videoTrack?.enabled);
    const microphoneEnabled = Boolean(audioTrack?.enabled);
    localVideo.hidden = !cameraEnabled;
    localCameraOff.hidden = cameraEnabled;
    localMicOff.hidden = microphoneEnabled;
    cameraButton.setAttribute('aria-pressed', String(!cameraEnabled));
    cameraButton.textContent = cameraEnabled ? 'Apagar cámara' : 'Activar cámara';
    micButton.setAttribute('aria-pressed', String(!microphoneEnabled));
    micButton.textContent = microphoneEnabled ? 'Silenciar micrófono' : 'Activar micrófono';
  };

  const updateRemoteMediaIndicators = () => {
    const cameraDisabled = remoteCameraActive === false;
    remoteVideo.hidden = cameraDisabled;
    remoteCameraOff.hidden = !cameraDisabled;
    noRemote.hidden = cameraDisabled || remoteVideoTrackReceived;
    remoteMicOff.hidden = remoteMicrophoneActive !== false;
  };

  const publishMediaState = () => {
    if (!activeCall?.id || activeCall.state !== 'en_curso') return;
    const videoTrack = devices.stream().getVideoTracks()[0];
    const audioTrack = devices.stream().getAudioTracks()[0];
    send({
      tipo: 'estado_medios',
      llamada_id: activeCall.id,
      camara_activa: Boolean(videoTrack?.enabled),
      microfono_activo: Boolean(audioTrack?.enabled),
    });
  };

  const send = (payload) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      if (['offer', 'answer', 'ice'].includes(payload.tipo) && activeCall) {
        if (pendingSignals.length < 128) {
          pendingSignals.push(payload);
          return true;
        }
        showError('La señalización está temporalmente saturada; espera o vuelve a intentar.');
        return false;
      }
      showError('La señalización no está conectada. Espera a que se reconecte.');
      return false;
    }
    socket.send(JSON.stringify(payload));
    return true;
  };

  const stopCountdown = () => {
    if (countdownTimer) window.clearInterval(countdownTimer);
    countdownTimer = null;
    incomingCountdown.textContent = '';
    setupCountdown.textContent = '';
    setupCountdown.hidden = true;
  };

  const startCountdown = (expiresAt) => {
    stopCountdown();
    const expires = new Date(expiresAt).getTime();
    const update = () => {
      const remaining = Math.max(0, Math.ceil((expires - Date.now()) / 1000));
      const text = `La invitación vence en ${remaining} segundos.`;
      incomingCountdown.textContent = text;
      setupCountdown.textContent = text;
      setupCountdown.hidden = setupDialog.open ? false : true;
      if (!remaining) {
        stopCountdown();
        pendingIncoming = null;
        incomingNotice.hidden = true;
        if (activeCall) releaseCall({ keepStatus: true });
        else devices.release();
        showError('La invitación venció. Puedes solicitar otra llamada.');
      }
    };
    update();
    countdownTimer = window.setInterval(update, 1000);
  };

  const setActiveStatus = (text, state = '') => {
    activeStatus.textContent = text;
    activeStatus.dataset.state = state;
  };

  const sendEndForSetup = () => {
    if (!activeCall?.id) return;
    if (activeCall.initiator && activeCall.state === 'sonando') {
      send({ tipo: 'cancelar', llamada_id: activeCall.id });
    } else if (!activeCall.initiator && ['sonando', 'preparando'].includes(activeCall.state)) {
      send({ tipo: 'rechazar', llamada_id: activeCall.id });
    }
  };

  const releaseCall = ({ keepStatus = false } = {}) => {
    if (disconnectTimer) window.clearTimeout(disconnectTimer);
    disconnectTimer = null;
    if (peerConnection) {
      peerConnection.onicecandidate = null;
      peerConnection.ontrack = null;
      peerConnection.onconnectionstatechange = null;
      peerConnection.oniceconnectionstatechange = null;
      peerConnection.close();
      peerConnection = null;
    }
    pendingCandidates = [];
    pendingSignals.length = 0;
    devices.release();
    localVideo.srcObject = null;
    localVideo.hidden = false;
    remoteVideo.srcObject = null;
    remoteVideo.hidden = false;
    remoteStream = new MediaStream();
    remoteVideoTrackReceived = false;
    remoteCameraActive = null;
    remoteMicrophoneActive = null;
    localCameraOff.hidden = true;
    remoteCameraOff.hidden = true;
    localMicOff.hidden = true;
    remoteMicOff.hidden = true;
    noRemote.hidden = false;
    activeCall = null;
    pendingIncoming = null;
    incomingNotice.hidden = true;
    stopCountdown();
    if (activeDialog.open) activeDialog.close();
    if (setupDialog.open) setupDialog.close();
    setupMode = null;
    if (!keepStatus) devices.setStatus('');
  };

  const openSetup = async (mode, call = null) => {
    setupMode = mode;
    setupTitle.textContent = mode === 'accept'
      ? 'Comprueba tus dispositivos para unirte'
      : mode === 'settings'
        ? 'Ajustes de dispositivos'
        : 'Prepara tus dispositivos';
    setupDescription.textContent = mode === 'accept'
      ? `Videollamada entrante de ${call?.peerName || 'tu contacto'}.`
      : mode === 'settings'
        ? 'Selecciona los dispositivos que quieres usar en esta llamada.'
        : 'Comprueba la cámara y el micrófono antes de iniciar.';
    setupConfirm.textContent = mode === 'accept'
      ? 'Unirme'
      : mode === 'settings'
        ? 'Listo'
        : 'Iniciar llamada';
    if (!setupDialog.open) setupDialog.showModal();
    if (mode === 'accept' && call?.expiresAt) startCountdown(call.expiresAt);
    const ready = await devices.open({ active: mode === 'settings' });
    if (!ready) {
      showError('No se pudieron preparar los dispositivos. Puedes volver a intentar o cancelar.');
    }
    return ready;
  };

  const openCallWindow = (name, statusText) => {
    peerName.textContent = name || 'Videollamada';
    setActiveStatus(statusText);
    localVideo.srcObject = devices.stream();
    setProfile(localAvatar, localInitials, shell.dataset.userName, shell.dataset.userAvatar);
    setProfile(remoteAvatar, remoteInitials, activeCall?.peerName, activeCall?.peerAvatar);
    updateLocalMediaIndicators();
    updateRemoteMediaIndicators();
    if (!activeDialog.open) activeDialog.showModal();
  };

  const fetchIceServers = async () => {
    const response = await fetch(shell.dataset.iceUrl, {
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'No se pudieron obtener los servidores ICE.');
    return data.iceServers || [];
  };

  const sendDescription = (type, description) => {
    if (!activeCall?.id) return;
    send({ tipo: type, llamada_id: activeCall.id, description });
  };

  const makeOffer = async (iceRestart = false) => {
    if (!peerConnection || !activeCall?.initiator) return;
    const offer = await peerConnection.createOffer(iceRestart ? { iceRestart: true } : undefined);
    await peerConnection.setLocalDescription(offer);
    sendDescription('offer', peerConnection.localDescription.toJSON());
  };

  const flushCandidates = async () => {
    if (!peerConnection?.remoteDescription) return;
    const candidates = pendingCandidates;
    pendingCandidates = [];
    for (const candidate of candidates) {
      await peerConnection.addIceCandidate(candidate);
    }
  };

  const createPeerConnection = async () => {
    const callId = activeCall?.id;
    if (peerConnectionCreation) {
      if (peerConnectionCreation.callId === callId) {
        return peerConnectionCreation.promise;
      }
      await peerConnectionCreation.promise.catch(() => {});
      if (activeCall?.id !== callId) return;
      return createPeerConnection();
    }
    if (peerConnection) return;

    let connection = null;
    const promise = (async () => {
      const iceServers = await fetchIceServers();
      if (!activeCall || activeCall.id !== callId) {
        throw new Error('La llamada ya terminó.');
      }

      connection = new RTCPeerConnection({ iceServers });
      peerConnection = connection;
      if (activeCall.initiator) {
        const senders = new Map();
        for (const kind of ['video', 'audio']) {
          const transceiver = connection.addTransceiver(kind, {
            direction: 'sendrecv',
          });
          senders.set(kind, transceiver.sender);
          devices.registerSender(kind, transceiver.sender);
        }
        for (const track of devices.stream().getTracks()) {
          await senders.get(track.kind).replaceTrack(track);
        }
      }
      if (activeCall?.id !== callId) {
        throw new Error('La llamada ya terminó.');
      }
      connection.onicecandidate = (event) => {
        if (event.candidate && activeCall?.id === callId) {
          send({
            tipo: 'ice',
            llamada_id: callId,
            candidate: event.candidate.toJSON(),
          });
        }
      };
      connection.ontrack = (event) => {
        const tracks = event.streams[0]?.getTracks() || [event.track];
        for (const track of tracks) {
          if (!remoteStream.getTracks().includes(track)) remoteStream.addTrack(track);
          if (track.kind === 'video') remoteVideoTrackReceived = true;
        }
        remoteVideo.srcObject = remoteStream;
        updateRemoteMediaIndicators();
        remoteVideo.play().catch(() => {});
        devices.setOutput(remoteVideo);
      };
      connection.onconnectionstatechange = () => {
        if (peerConnection !== connection) return;
        const state = connection.connectionState;
        if (state === 'connected') {
          setActiveStatus('Conectado');
        } else if (state === 'connecting') {
          setActiveStatus('Conectando…');
        } else if (state === 'disconnected') {
          setActiveStatus('Reconectando…', 'reconnecting');
          scheduleIceRestart();
        } else if (state === 'failed') {
          setActiveStatus('Sin conexión; intentando restablecer…', 'disconnected');
          scheduleIceRestart();
        }
      };
      connection.oniceconnectionstatechange = () => {
        if (
          peerConnection === connection
          && connection.iceConnectionState === 'disconnected'
        ) scheduleIceRestart();
      };
    })();
    peerConnectionCreation = { callId, promise };

    try {
      await promise;
    } catch (error) {
      if (connection && peerConnection === connection) {
        connection.close();
        peerConnection = null;
      }
      if (activeCall?.id === callId) {
        devices.registerSender('video', null);
        devices.registerSender('audio', null);
      }
      throw error;
    } finally {
      if (peerConnectionCreation?.promise === promise) {
        peerConnectionCreation = null;
      }
    }
  };

  const scheduleIceRestart = () => {
    if (disconnectTimer || restartAttempted) return;
    disconnectTimer = window.setTimeout(async () => {
      disconnectTimer = null;
      if (!peerConnection || peerConnection.connectionState === 'connected' || restartAttempted) return;
      restartAttempted = true;
      if (!activeCall?.initiator) {
        setActiveStatus('Esperando que se restablezca la conexión…', 'reconnecting');
        return;
      }
      try {
        peerConnection.restartIce();
        await makeOffer(true);
        setActiveStatus('Reconectando…', 'reconnecting');
      } catch (error) {
        setActiveStatus('No se pudo reiniciar la conexión.', 'disconnected');
      }
    }, 2500);
  };

  const handleAccepted = async (payload) => {
    const callId = Number(payload.llamada_id);
    if (
      !activeCall?.initiator
      && activeCall?.id === callId
      && payload.aceptada_conexion
      && payload.aceptada_conexion !== connectionId
    ) {
      releaseCall({ keepStatus: true });
      showNotice('La llamada fue contestada desde otra pestaña.');
      return;
    }
    if (!activeCall || activeCall.id !== callId) {
      if (pendingIncoming?.id === callId) {
        pendingIncoming = null;
        incomingNotice.hidden = true;
        stopCountdown();
        devices.release();
        showError('La llamada fue contestada desde otra pestaña.');
      }
      return;
    }
    stopCountdown();
    activeCall.state = 'en_curso';
    restartAttempted = false;
    try {
      await createPeerConnection();
      if (activeCall?.id !== callId) return;
      openCallWindow(activeCall.peerName, 'Conectando…');
      publishMediaState();
      if (activeCall.initiator) await makeOffer();
    } catch (error) {
      if (activeCall?.id !== callId) return;
      showError(error.message || 'No se pudo iniciar la conexión WebRTC.');
      send({ tipo: 'colgar', llamada_id: callId });
      releaseCall();
    }
  };

  const handleSignal = async (payload) => {
    const callId = Number(payload.llamada_id);
    if (!activeCall || activeCall.id !== callId) return;
    try {
      if (payload.tipo === 'offer') {
        await createPeerConnection();
        if (activeCall?.id !== callId || !peerConnection) return;
        await peerConnection.setRemoteDescription(payload.description);
        const localTracks = new Map(
          devices.stream().getTracks().map((track) => [track.kind, track]),
        );
        for (const transceiver of peerConnection.getTransceivers()) {
          const kind = transceiver.receiver.track.kind;
          if (!['audio', 'video'].includes(kind)) continue;
          transceiver.direction = 'sendrecv';
          devices.registerSender(kind, transceiver.sender);
          await transceiver.sender.replaceTrack(localTracks.get(kind) || null);
        }
        await flushCandidates();
        const answer = await peerConnection.createAnswer();
        await peerConnection.setLocalDescription(answer);
        sendDescription('answer', peerConnection.localDescription.toJSON());
      } else if (payload.tipo === 'answer') {
        if (!peerConnection) return;
        await peerConnection.setRemoteDescription(payload.description);
        await flushCandidates();
      } else if (payload.tipo === 'ice') {
        const candidate = new RTCIceCandidate(payload.candidate);
        if (peerConnection?.remoteDescription) await peerConnection.addIceCandidate(candidate);
        else pendingCandidates.push(candidate);
      }
    } catch (error) {
      if (activeCall?.id === callId) {
        showError('No se pudo completar la señalización de la videollamada.');
      }
    }
  };

  const handlePayload = async (payload) => {
    if (!payload || typeof payload !== 'object') return;
    if (payload.tipo === 'conectado') return;
    if (payload.tipo === 'error') {
      showError(payload.mensaje || 'No se pudo procesar la videollamada.');
      if (activeCall?.state === 'invitando') releaseCall({ keepStatus: true });
      return;
    }
    if (payload.tipo === 'entrante') {
      const incomingId = Number(payload.llamada_id);
      if (pendingIncoming?.id === incomingId || activeCall?.id === incomingId) return;
      if (activeCall || pendingIncoming) {
        send({ tipo: 'rechazar', llamada_id: incomingId });
        return;
      }
      pendingIncoming = {
        id: incomingId,
        pacienteId: Number(payload.paciente_id),
        peerName: payload.iniciador_nombre,
        peerAvatar: payload.iniciador_foto || '',
        expiresAt: payload.expira_en,
      };
      incomingName.textContent = payload.iniciador_nombre || 'Un paciente o médico';
      incomingNotice.hidden = false;
      startCountdown(payload.expira_en);
      return;
    }
    if (payload.tipo === 'sonando') {
      if (!activeCall) {
        send({ tipo: 'cancelar', llamada_id: Number(payload.llamada_id) });
        return;
      }
      activeCall.id = Number(payload.llamada_id);
      activeCall.state = 'sonando';
      activeCall.peerName = payload.destinatario_nombre || activeCall.peerName;
      activeCall.peerAvatar = payload.destinatario_foto || activeCall.peerAvatar || '';
      activeCall.expiresAt = payload.expira_en;
      openCallWindow(activeCall.peerName, 'Llamando…');
      startCountdown(payload.expira_en);
      return;
    }
    if (payload.tipo === 'aceptada') {
      await handleAccepted(payload);
      return;
    }
    if (payload.tipo === 'estado_medios') {
      if (activeCall?.id !== Number(payload.llamada_id)) return;
      remoteCameraActive = payload.camara_activa;
      remoteMicrophoneActive = payload.microfono_activo;
      updateRemoteMediaIndicators();
      return;
    }
    if (['offer', 'answer', 'ice'].includes(payload.tipo)) {
      await handleSignal(payload);
      return;
    }
    if (payload.tipo === 'ocupado') {
      showError('La otra persona ya está en una llamada.');
      releaseCall();
      return;
    }
    if (payload.tipo === 'rechazada' || payload.tipo === 'cancelada' || payload.tipo === 'terminada') {
      const reason = payload.motivo;
      const message = payload.tipo === 'rechazada'
        ? 'La llamada fue rechazada.'
        : payload.tipo === 'cancelada'
          ? 'La llamada fue cancelada.'
          : reason === 'perdida'
            ? 'Llamada perdida.'
            : reason === 'acceso_revocado'
              ? 'La llamada terminó porque cambió la asignación del médico.'
              : reason === 'desconexion'
                ? 'La llamada terminó porque no se pudo restablecer la conexión.'
                : 'La videollamada finalizó.';
      releaseCall({ keepStatus: true });
      showNotice(message);
      return;
    }
  };

  const connectSocket = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket = new WebSocket(`${protocol}//${window.location.host}${shell.dataset.signalingPath}`);
    socket.addEventListener('open', () => {
      reconnectDelay = 1000;
      if (activeCall?.id) setActiveStatus('Señalización reconectada; verificando la llamada…');
      else showSignalingStatus('Señalización de videollamada conectada.');
      while (pendingSignals.length && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(pendingSignals.shift()));
      }
    });
    socket.addEventListener('message', (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.tipo === 'conectado') connectionId = payload.conexion_id || null;
        handlePayload(payload);
      } catch (error) {
        showError('Se recibió una señalización inválida.');
      }
    });
    socket.addEventListener('close', (event) => {
      if (event.code === 4401 || event.code === 4403) {
        showError('No tienes acceso a la videollamada.');
        releaseCall({ keepStatus: true });
        return;
      }
      showSignalingStatus(
        `Señalización desconectada (código ${event.code}). Reintentando…`,
        true,
      );
      if (activeCall) setActiveStatus('Reconectando señalización…', 'reconnecting');
      reconnectTimer = window.setTimeout(connectSocket, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 30000);
    });
    socket.addEventListener('error', () => {
      showSignalingStatus(
        'No se pudo abrir la señalización de videollamada; se reintentará.',
        true,
      );
      if (activeCall) setActiveStatus('Sin conexión de señalización.', 'disconnected');
    });
  };

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-call-paciente-id]');
    if (!button || button.disabled) return;
    const patientId = Number(button.dataset.callPacienteId);
    if (!patientId) return;
    if (activeCall || pendingIncoming) {
      showError('Termina la llamada actual antes de iniciar otra.');
      return;
    }
    activeCall = {
      id: null,
      pacienteId: patientId,
      peerName: button.dataset.callPeerName || 'Paciente',
      initiator: true,
      state: 'preparando',
    };
    openSetup('invite').catch((error) => showError(error.message));
  });

  document.getElementById('videollamadaAccept').addEventListener('click', () => {
    if (!pendingIncoming) return;
    activeCall = {
      id: pendingIncoming.id,
      pacienteId: pendingIncoming.pacienteId,
      peerName: pendingIncoming.peerName,
      peerAvatar: pendingIncoming.peerAvatar,
      expiresAt: pendingIncoming.expiresAt,
      initiator: false,
      state: 'preparando',
    };
    openSetup('accept', activeCall).catch((error) => showError(error.message));
  });

  document.getElementById('videollamadaReject').addEventListener('click', () => {
    if (!pendingIncoming) return;
    send({ tipo: 'rechazar', llamada_id: pendingIncoming.id });
    pendingIncoming = null;
    incomingNotice.hidden = true;
    stopCountdown();
  });

  setupConfirm.addEventListener('click', async () => {
    if (setupMode === 'settings') {
      setupDialog.close();
      return;
    }
    const ready = await devices.activate();
    if (!ready) {
      showError('Activa al menos una cámara o un micrófono, o cancela para volver a intentarlo.');
      return;
    }
    if (setupMode === 'invite') {
      activeCall.state = 'invitando';
      openCallWindow(activeCall.peerName, 'Iniciando llamada…');
      if (!send({ tipo: 'invitar', paciente_id: activeCall.pacienteId })) {
        releaseCall({ keepStatus: true });
        return;
      }
    } else if (setupMode === 'accept' && activeCall) {
      pendingIncoming = null;
      incomingNotice.hidden = true;
      activeCall.state = 'sonando';
      openCallWindow(activeCall.peerName, 'Uniéndote a la llamada…');
      if (!send({ tipo: 'aceptar', llamada_id: activeCall.id })) {
        releaseCall({ keepStatus: true });
        return;
      }
    }
    setupDialog.close();
    if (activeCall?.expiresAt) startCountdown(activeCall.expiresAt);
  });

  setupCancel.addEventListener('click', () => {
    if (setupMode === 'accept' && activeCall) sendEndForSetup();
    if (setupMode === 'invite' && activeCall?.id) sendEndForSetup();
    if (setupMode !== 'settings') {
      releaseCall();
      return;
    }
    setupDialog.close();
  });
  setupDialog.addEventListener('close', () => {
    if (setupMode !== 'settings' && activeCall?.state === 'preparando') {
      if (setupMode === 'accept') sendEndForSetup();
      releaseCall();
    }
  });

  document.getElementById('videollamadaSettings').addEventListener('click', () => {
    openSetup('settings', activeCall).catch((error) => showError(error.message));
  });
  document.getElementById('videollamadaHangup').addEventListener('click', () => {
    if (activeCall?.id) send({ tipo: 'colgar', llamada_id: activeCall.id });
    releaseCall({ keepStatus: true });
    showNotice('Videollamada finalizada.');
  });

  micButton.addEventListener('click', () => {
    const tracks = devices.stream().getAudioTracks();
    if (!tracks.length) {
      showError('No hay un micrófono activo.');
      return;
    }
    const enabled = !tracks[0].enabled;
    tracks.forEach((track) => { track.enabled = enabled; });
    updateLocalMediaIndicators();
    publishMediaState();
  });

  cameraButton.addEventListener('click', () => {
    const tracks = devices.stream().getVideoTracks();
    if (!tracks.length) {
      showError('No hay una cámara activa.');
      return;
    }
    const enabled = !tracks[0].enabled;
    tracks.forEach((track) => { track.enabled = enabled; });
    updateLocalMediaIndicators();
    publishMediaState();
  });

  document.getElementById('videollamadaFullscreen').addEventListener('click', async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await activeStage.requestFullscreen();
    } catch (error) {
      showError('El navegador no permitió activar la pantalla completa.');
    }
  });

  document.addEventListener('videollamada-output-changed', (event) => {
    if (typeof remoteVideo.setSinkId === 'function') {
      remoteVideo.setSinkId(event.detail.deviceId).catch(() => {
        showError('No se pudo cambiar la salida de audio.');
      });
    }
  });

  if (role === 'doctor') {
    document.addEventListener('mensajeria-conversacion-abierta', (event) => {
      const button = document.getElementById('mensajeriaVideoCall');
      if (!button) return;
      button.dataset.callPacienteId = String(event.detail.pacienteId);
      button.dataset.callPeerName = event.detail.nombre || 'Paciente';
      button.disabled = !event.detail.pacienteId;
      button.title = button.disabled
        ? 'El paciente debe tener una cuenta vinculada.'
        : `Iniciar videollamada con ${event.detail.nombre}`;
    });
  }

  connectSocket();
  window.addEventListener('beforeunload', () => {
    if (reconnectTimer) window.clearTimeout(reconnectTimer);
    if (signalingStatusTimer) window.clearTimeout(signalingStatusTimer);
    if (countdownTimer) window.clearInterval(countdownTimer);
    if (peerConnection) peerConnection.close();
    devices.release();
    if (socket) socket.close();
  }, { once: true });
})();
