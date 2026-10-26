'use strict';
// Full-duplex, foreground-only conversation with Gemini Live.
// Tap "Voce" once to enter, then speak naturally. No background recording.
(() => {
  const $ = id => document.getElementById(id);
  const view = $('voice');
  const status = $('live-status');
  const exit = $('live-exit');
  if (!view || !status || !exit) return;

  let socket = null;
  let stream = null;
  let context = null;
  let microphone = null;
  let processor = null;
  let mute = null;
  let playback = new Set();
  let nextPlaybackTime = 0;
  let session = 0;
  let listening = false;
  let startupTimeout = null;
  let ending = false;
  let autoStartPending = false;

  function setStatus(message) {
    status.textContent = message;
  }
  function clearPlayback() {
    for (const src of playback) {
      try { src.stop(); } catch (_) {}
      try { src.disconnect(); } catch (_) {}
    }
    playback.clear();
    nextPlaybackTime = 0;
  }
  function cleanUp() {
    if (startupTimeout) { clearTimeout(startupTimeout); startupTimeout = null; }
    listening = false;
    clearPlayback();
    if (processor) { processor.onaudioprocess = null; try { processor.disconnect(); } catch (_) {} }
    processor = null;
    if (microphone) { try { microphone.disconnect(); } catch (_) {} }
    microphone = null;
    if (mute) { try { mute.disconnect(); } catch (_) {} }
    mute = null;
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null;
    const oldContext = context;
    context = null;
    if (oldContext && oldContext.state !== 'closed') void oldContext.close().catch(() => {});
    const oldSocket = socket;
    socket = null;
    if (oldSocket && oldSocket.readyState < WebSocket.CLOSING) {
      try { oldSocket.close(1000, 'Session ended'); } catch (_) {}
    }
    view.classList.remove('live-active');
  }
  function stopLive(message) {
    session++;
    ending = true;
    cleanUp();
    if (message) setStatus(message);
  }
  function pcm16(data, inputRate) {
    // Convert Web Audio float samples to Gemini Live 16kHz mono PCM.
    const ratio = inputRate / 16000;
    const size = Math.max(1, Math.floor(data.length / ratio));
    const buf = new ArrayBuffer(size * 2);
    const writer = new DataView(buf);
    for (let i = 0; i < size; i++) {
      const start = Math.floor(i * ratio);
      const end = Math.max(start + 1, Math.min(data.length, Math.floor((i + 1) * ratio)));
      let total = 0;
      for (let j = start; j < end; j++) total += data[j];
      const sample = Math.max(-1, Math.min(1, total / (end - start)));
      writer.setInt16(i * 2, sample < 0 ? sample * 32768 : sample * 32767, true);
    }
    return buf;
  }
  function playPcm(base64) {
    if (!context || !listening) return;
    try {
      const raw = atob(base64);
      if (raw.length < 2 || raw.length > 375000 || raw.length % 2) return;
      const frames = raw.length / 2;
      const audio = context.createBuffer(1, frames, 24000);
      const out = audio.getChannelData(0);
      for (let i = 0; i < frames; i++) {
        const lower = raw.charCodeAt(i * 2), upper = raw.charCodeAt(i * 2 + 1);
        const signed = ((upper << 8) | lower);
        out[i] = (signed & 32768 ? signed - 65536 : signed) / 32768;
      }
      // Bound playback queue, so slow devices never accumulate old dialogue.
      if (nextPlaybackTime - context.currentTime > 3.0) {
        clearPlayback();
      }
      const source = context.createBufferSource();
      source.buffer = audio;
      source.connect(context.destination);
      source.onended = () => { playback.delete(source); try { source.disconnect(); } catch (_) {} };
      const startAt = Math.max(context.currentTime + 0.04, nextPlaybackTime || 0);
      playback.add(source);
      source.start(startAt);
      nextPlaybackTime = startAt + audio.duration;
      setStatus('Jarvis sta rispondendo. Puoi interromperlo parlando.');
    } catch (_) {
      // Invalid audio frame is discarded without stopping the microphone.
    }
  }
  function displayTranscript(role, text) {
    const target = role === 'input' ? $('voice-transcript') : $('voice-answer');
    if (target && text) target.textContent = text.slice(0, 2000);
  }
  function handleEvent(ev) {
    let message;
    try { message = JSON.parse(ev.data); } catch (_) { return; }
    if (message.ready) { setStatus('Ti ascolto. Parla normalmente, senza premere nulla.'); return; }
    if (message.error) {
      stopLive('Live non disponibile: ' + message.error + ' Tocca il microfono per la modalità classica.');
      return;
    }
    if (message.interrupted) {
      clearPlayback();
      setStatus('Ti ascolto.');
    }
    if (message.input) displayTranscript('input', message.input);
    if (message.output) displayTranscript('output', message.output);
    if (message.audio) playPcm(message.audio);
    if (message.turnComplete) {
      // Continue listening: no mic reactivation or send button needed.
      setStatus('Ti ascolto. Puoi continuare a parlare.');
    }
  }
  function foreground() {
    return !document.hidden && view.classList.contains('active') && authenticated;
  }
  async function startLive() {
    if (autoStartPending || listening || !foreground()) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.WebSocket || !(window.AudioContext || window.webkitAudioContext)) {
      setStatus('Audio continuo non supportato: usa il microfono della modalità classica.');
      return;
    }
    const current = ++session;
    ending = false;
    autoStartPending = true;
    setStatus('Attivo il microfono e la connessione vocale…');
    try {
      // Must be created/resumed during the tap that opens Voce on iOS Safari.
      context = new (window.AudioContext || window.webkitAudioContext)({latencyHint: 'interactive'});
      const resumePromise = context.resume();
      const mediaPromise = navigator.mediaDevices.getUserMedia({
        audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true}
      });
      await resumePromise;
      const media = await mediaPromise;
      if (current !== session || !foreground()) {
        media.getTracks().forEach(t => t.stop());
        return;
      }
      stream = media;
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      socket = new WebSocket(protocol + '//' + location.host + '/api/live/voice');
      const currentSocket = socket;
      socket.onmessage = evt => { if (current === session) handleEvent(evt); };
      socket.onerror = () => {
        if (current === session) setStatus('Connessione audio in errore. Verifico il collegamento…');
      };
      socket.onclose = () => {
        if (current === session && !ending) {
          stopLive('Sessione Live chiusa. Per continuare usa la modalità vocale classica o rientra in Voce.');
        }
      };
      socket.onopen = () => {
        if (current !== session || !foreground() || currentSocket !== socket) return;
        if (startupTimeout) { clearTimeout(startupTimeout); startupTimeout = null; }
        microphone = context.createMediaStreamSource(stream);
        processor = context.createScriptProcessor(2048, 1, 1);
        // Processor needs to be connected for processing on Safari. Its output
        // is silent and cannot feed back into speakers.
        mute = context.createGain();
        mute.gain.value = 0;
        microphone.connect(processor);
        processor.connect(mute);
        mute.connect(context.destination);
        processor.onaudioprocess = event => {
          if (current !== session || !listening || !socket || socket.readyState !== WebSocket.OPEN) return;
          if (socket.bufferedAmount > 128000) return;
          const mono = event.inputBuffer.getChannelData(0);
          const pcm = pcm16(mono, context.sampleRate);
          if (pcm.byteLength <= 16384) socket.send(pcm);
        };
        listening = true;
        view.classList.add('live-active');
        setStatus('Microfono attivo. Ti ascolto…');
      };
      startupTimeout = setTimeout(() => {
        if (current === session && !listening) stopLive('Impossibile collegarsi in tempo. Usa il microfono classico.');
      }, 14000);
    } catch (_) {
      if (current === session) stopLive('Autorizza il microfono in Safari per avviare la conversazione continua.');
    } finally {
      autoStartPending = false;
    }
  }
  exit.addEventListener('click', () => { stopLive('Microfono disattivato.'); page('home'); });
  document.addEventListener('jarvis:pagechange', ev => {
    if (ev.detail.name === 'voice') {
      // The navigation tap is the user gesture for Web Audio on iPhone.
      void startLive();
    } else if (listening || autoStartPending || socket || stream) {
      stopLive('Microfono disattivato quando esci da Voce.');
    }
  });
  document.addEventListener('jarvis:logout', () => stopLive('Sessione terminata.'));
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopLive('Microfono spento: Jarvis non ascolta in background.');
  });
  window.addEventListener('pagehide', () => stopLive('Sessione terminata.'));
})();
