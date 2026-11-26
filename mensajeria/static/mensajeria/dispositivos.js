(() => {
  const shell = document.getElementById('videollamadaShell');
  if (!shell) return;

  const preview = document.getElementById('videollamadaPreview');
  const camera = document.getElementById('videollamadaCamera');
  const microphone = document.getElementById('videollamadaMicrophone');
  const output = document.getElementById('videollamadaOutput');
  const outputLabel = document.getElementById('videollamadaOutputLabel');
  const meter = document.getElementById('videollamadaMicMeter');
  const status = document.getElementById('videollamadaDeviceStatus');
  const actual = document.getElementById('videollamadaDeviceActual');
  const activeCamera = document.getElementById('videollamadaActiveCamera');
  const activeMicrophone = document.getElementById('videollamadaActiveMicrophone');
  const preferenceKey = `nexorev:dispositivos:${shell.dataset.userId}`;
  const setSinkSupported = typeof HTMLMediaElement.prototype.setSinkId === 'function';
  let preferences = {};
  let stream = new MediaStream();
  let senders = {};
  let audioContext = null;
  let meterFrame = null;
  let deviceChangeHandler = null;

  try {
    preferences = JSON.parse(localStorage.getItem(preferenceKey) || '{}');
  } catch (error) {
    console.warn('No se pudieron leer las preferencias de dispositivos.', error);
  }

  const errorMessage = (error, kind) => {
    if (!window.isSecureContext || !navigator.mediaDevices) {
      return 'La cámara y el micrófono requieren HTTPS o localhost en este computador.';
    }
    if (error?.name === 'NotAllowedError' || error?.name === 'SecurityError') {
      return 'Permiso denegado. Habilita cámara y micrófono en los permisos del navegador y en la privacidad de Windows.';
    }
    if (error?.name === 'NotFoundError' || error?.name === 'DevicesNotFoundError') {
      return kind === 'video' ? 'No se encontró una cámara disponible.' : 'No se encontró un micrófono disponible.';
    }
    if (error?.name === 'NotReadableError' || error?.name === 'TrackStartError') {
      return 'Esa cámara o micrófono está en uso por otra aplicación u otro navegador; elige otro dispositivo o ciérrala.';
    }
    if (error?.name === 'OverconstrainedError' || error?.name === 'ConstraintNotSatisfiedError') {
      return 'Ese dispositivo no admite esta configuración. Prueba con el dispositivo predeterminado.';
    }
    return `No se pudo activar ${kind === 'video' ? 'la cámara' : 'el micrófono'}. ${error?.message || ''}`.trim();
  };

  const showStatus = (message, isError = false) => {
    status.textContent = message;
    status.classList.toggle('is-error', isError);
  };

  const stopTracks = (mediaStream) => {
    if (mediaStream) mediaStream.getTracks().forEach((track) => track.stop());
  };

  const selectedId = (kind) => (
    kind === 'video' ? camera.value : microphone.value
  );

  const captureTrack = async (kind, deviceId) => {
    const constraints = kind === 'video'
      ? {
        video: {
          ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
          width: { ideal: 1280 },
          height: { ideal: 720 },
          frameRate: { ideal: 30 },
        },
        audio: false,
      }
      : {
        video: false,
        audio: {
          ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
        },
      };
    let temporary;
    try {
      temporary = await navigator.mediaDevices.getUserMedia(constraints);
    } catch (error) {
      if (!deviceId || error?.name !== 'OverconstrainedError') throw error;
      const defaults = kind === 'video'
        ? {
          video: {
            width: { ideal: 1280 },
            height: { ideal: 720 },
            frameRate: { ideal: 30 },
          },
          audio: false,
        }
        : { video: false, audio: true };
      temporary = await navigator.mediaDevices.getUserMedia(defaults);
      showStatus('El dispositivo elegido no admite la configuración; se usó el predeterminado.', true);
    }
    const track = temporary.getTracks().find((item) => item.kind === kind);
    if (!track) {
      stopTracks(temporary);
      throw new DOMException('No se obtuvo una pista del tipo solicitado.', 'NotFoundError');
    }
    const select = kind === 'video' ? camera : microphone;
    const actualDeviceId = track.getSettings().deviceId;
    if ([...select.options].some((option) => option.value === actualDeviceId)) {
      select.value = actualDeviceId;
    }
    temporary.getTracks().filter((item) => item !== track).forEach((item) => item.stop());
    return track;
  };

  const refreshActualDevices = () => {
    const videoTrack = stream.getVideoTracks()[0];
    const audioTrack = stream.getAudioTracks()[0];
    activeCamera.textContent = videoTrack
      ? `${videoTrack.label || 'Cámara activa'} (${videoTrack.getSettings().deviceId || 'ID no disponible'})`
      : 'Sin cámara activa';
    activeMicrophone.textContent = audioTrack
      ? `${audioTrack.label || 'Micrófono activo'} (${audioTrack.getSettings().deviceId || 'ID no disponible'})`
      : 'Sin micrófono activo';
    actual.hidden = false;
  };

  const savePreferences = () => {
    const videoTrack = stream.getVideoTracks()[0];
    const audioTrack = stream.getAudioTracks()[0];
    preferences = {
      camera: videoTrack?.getSettings().deviceId || '',
      microphone: audioTrack?.getSettings().deviceId || '',
      output: output.value || '',
    };
    try {
      localStorage.setItem(preferenceKey, JSON.stringify(preferences));
    } catch (error) {
      showStatus('No se pudo guardar la preferencia de dispositivos en este navegador.', true);
    }
  };

  const populateSelect = (select, devices, selected, emptyLabel) => {
    const previousValue = select.value;
    select.replaceChildren();
    devices.forEach((device, index) => {
      const option = document.createElement('option');
      option.value = device.deviceId;
      option.textContent = device.label || `${emptyLabel} ${index + 1}`;
      select.append(option);
    });
    const value = devices.some((device) => device.deviceId === previousValue)
      ? previousValue
      : devices.some((device) => device.deviceId === selected)
        ? selected
        : devices[0]?.deviceId || '';
    select.value = value;
    select.disabled = devices.length <= 1;
  };

  const refreshDeviceLists = async () => {
    const devices = await navigator.mediaDevices.enumerateDevices();
    populateSelect(camera, devices.filter((device) => device.kind === 'videoinput'), preferences.camera, 'Cámara');
    populateSelect(microphone, devices.filter((device) => device.kind === 'audioinput'), preferences.microphone, 'Micrófono');
    if (setSinkSupported) {
      const outputs = devices.filter((device) => device.kind === 'audiooutput');
      populateSelect(output, outputs, preferences.output, 'Salida de audio');
      output.hidden = false;
      outputLabel.hidden = false;
    }
    return devices;
  };

  const startMeter = () => {
    if (audioContext) {
      audioContext.close();
      audioContext = null;
    }
    if (meterFrame) cancelAnimationFrame(meterFrame);
    const track = stream.getAudioTracks()[0];
    if (!track) {
      meter.value = 0;
      return;
    }
    const AudioContextConstructor = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextConstructor) return;
    audioContext = new AudioContextConstructor();
    const source = audioContext.createMediaStreamSource(new MediaStream([track]));
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    const readLevel = () => {
      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      samples.forEach((sample) => {
        const normalized = (sample - 128) / 128;
        sum += normalized * normalized;
      });
      meter.value = Math.min(Math.sqrt(sum / samples.length) * 4, 1);
      meterFrame = requestAnimationFrame(readLevel);
    };
    readLevel();
  };

  const bindTrackEnded = (track) => {
    track.addEventListener('ended', async () => {
      if (!stream.getTracks().includes(track)) return;
      const kind = track.kind;
      stream.removeTrack(track);
      refreshActualDevices();
      if (kind === 'video') {
        showStatus('La cámara se desconectó. Buscando otra cámara disponible…', true);
        try {
          const devices = await refreshDeviceLists();
          const replacement = devices.find(
            (device) => device.kind === 'videoinput' && device.deviceId !== track.getSettings().deviceId,
          );
          if (replacement) {
            await switchTrack('video', replacement.deviceId);
            showStatus('Se cambió a otra cámara.');
          } else {
            const sender = senders.video;
            if (sender) await sender.replaceTrack(null);
            preview.srcObject = stream;
            showStatus('La cámara se desconectó; la llamada puede continuar solo con audio.', true);
          }
        } catch (error) {
          preview.srcObject = stream;
          showStatus(errorMessage(error, 'video'), true);
        }
      } else {
        const sender = senders.audio;
        if (sender) sender.replaceTrack(null).catch(() => {});
        startMeter();
        showStatus('El micrófono se desconectó. Puedes continuar sin audio o elegir otro.', true);
      }
    }, { once: true });
  };

  const switchTrack = async (kind, deviceId) => {
    const oldTrack = kind === 'video'
      ? stream.getVideoTracks()[0]
      : stream.getAudioTracks()[0];
    const oldDeviceId = oldTrack?.getSettings().deviceId || '';
    if (oldTrack) {
      stream.removeTrack(oldTrack);
      oldTrack.stop();
    }
    try {
      const newTrack = await captureTrack(kind, deviceId);
      const sender = senders[kind];
      if (sender) await sender.replaceTrack(newTrack);
      stream.addTrack(newTrack);
      bindTrackEnded(newTrack);
      preview.srcObject = stream;
      if (kind === 'audio') startMeter();
      refreshActualDevices();
      savePreferences();
      return newTrack;
    } catch (error) {
      if (oldTrack) {
        try {
          const restored = await captureTrack(kind, oldDeviceId || undefined);
          const sender = senders[kind];
          if (sender) await sender.replaceTrack(restored);
          stream.addTrack(restored);
          bindTrackEnded(restored);
          preview.srcObject = stream;
          if (kind === 'audio') startMeter();
          refreshActualDevices();
        } catch (restoreError) {
          showStatus(`${errorMessage(error, kind)} No se pudo restaurar el dispositivo anterior: ${errorMessage(restoreError, kind)}`, true);
          throw error;
        }
      }
      showStatus(errorMessage(error, kind), true);
      throw error;
    }
  };

  const preparePermissionAndList = async () => {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      showStatus('Para usar cámara y micrófono necesitas HTTPS o localhost en este computador.', true);
      return false;
    }
    try {
      const temporary = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      stopTracks(temporary);
    } catch (combinedError) {
      const granted = [];
      for (const kind of ['video', 'audio']) {
        try {
          const temporary = await navigator.mediaDevices.getUserMedia(
            kind === 'video' ? { video: true, audio: false } : { video: false, audio: true },
          );
          granted.push(kind);
          stopTracks(temporary);
        } catch (error) {
          showStatus(`${kind === 'video' ? 'Cámara' : 'Micrófono'}: ${errorMessage(error, kind)} ${errorMessage(combinedError, kind)}`, true);
        }
      }
      if (!granted.length) return false;
    }
    try {
      await refreshDeviceLists();
      return true;
    } catch (error) {
      showStatus(errorMessage(error, 'video'), true);
      return false;
    }
  };

  const acquireInitialStream = async () => {
    const devices = await refreshDeviceLists();
    const availableVideo = devices.some((device) => device.kind === 'videoinput');
    const availableAudio = devices.some((device) => device.kind === 'audioinput');
    const tracks = [];
    for (const [kind, available, id] of [
      ['video', availableVideo, camera.value],
      ['audio', availableAudio, microphone.value],
    ]) {
      if (!available) continue;
      try {
        const track = await captureTrack(kind, id);
        tracks.push(track);
        bindTrackEnded(track);
      } catch (error) {
        showStatus(errorMessage(error, kind), true);
      }
    }
    stream = new MediaStream(tracks);
    preview.srcObject = stream;
    await preview.play().catch(() => {});
    startMeter();
    refreshActualDevices();
    savePreferences();
    return stream;
  };

  const open = async ({ active = false } = {}) => {
    showStatus('Solicitando permiso para mostrar las etiquetas de tus dispositivos…');
    const permitted = await preparePermissionAndList();
    if (!permitted && !active) return false;
    if (active) {
      preview.srcObject = stream;
      await preview.play().catch(() => {});
      refreshActualDevices();
      startMeter();
    } else {
      await acquireInitialStream();
    }
    return true;
  };

  camera.addEventListener('change', () => {
    if (camera.value) switchTrack('video', camera.value).catch(() => {});
  });
  microphone.addEventListener('change', () => {
    if (microphone.value) switchTrack('audio', microphone.value).catch(() => {});
  });
  output.addEventListener('change', () => {
    preferences.output = output.value;
    try {
      localStorage.setItem(preferenceKey, JSON.stringify(preferences));
    } catch (error) {
      showStatus('No se pudo guardar la preferencia de salida de audio.', true);
    }
    document.dispatchEvent(new CustomEvent('videollamada-output-changed', {
      detail: { deviceId: output.value },
    }));
  });

  deviceChangeHandler = () => {
    refreshDeviceLists().catch((error) => showStatus(errorMessage(error, 'video'), true));
  };
  if (navigator.mediaDevices?.addEventListener) {
    navigator.mediaDevices.addEventListener('devicechange', deviceChangeHandler);
  } else if (navigator.mediaDevices) {
    navigator.mediaDevices.ondevicechange = deviceChangeHandler;
  }

  const api = {
    open,
    stream: () => stream,
    registerSender(kind, sender) {
      senders[kind] = sender;
    },
    async activate() {
      if (!stream.getTracks().length) return false;
      savePreferences();
      return true;
    },
    async replace(kind, sender, deviceId) {
      senders[kind] = sender;
      return switchTrack(kind, deviceId || selectedId(kind));
    },
    async setOutput(element) {
      if (!setSinkSupported || !preferences.output) return;
      try {
        await element.setSinkId(preferences.output);
      } catch (error) {
        showStatus(`No se pudo usar la salida de audio elegida: ${errorMessage(error, 'audio')}`, true);
      }
    },
    release() {
      stopTracks(stream);
      stream = new MediaStream();
      preview.srcObject = null;
      if (audioContext) {
        audioContext.close();
        audioContext = null;
      }
      if (meterFrame) cancelAnimationFrame(meterFrame);
      meter.value = 0;
      actual.hidden = true;
      senders = {};
    },
    setStatus: showStatus,
    currentDevices() {
      return {
        camera: stream.getVideoTracks()[0],
        microphone: stream.getAudioTracks()[0],
      };
    },
  };
  window.NexoRevDevices = api;
})();
