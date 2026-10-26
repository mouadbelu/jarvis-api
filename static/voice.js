'use strict';
// Dedicated turn-based voice conversation for Safari/iPhone and compatible browsers.
// Microphone access is requested only by the user's gesture. No background listening.
(() => {
  const $v = id => document.getElementById(id);
  const root = $v('voice');
  if (!root) return;

  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synthesis = window.speechSynthesis;
  const mic = $v('voice-mic');
  const action = $v('voice-action');
  const stateText = $v('voice-state');
  const hint = $v('voice-hint');
  const live = $v('voice-transcript');
  const answer = $v('voice-answer');
  const repeat = $v('voice-repeat');
  const stop = $v('voice-stop');
  const history = $v('voice-log');
  let recognizer = null;
  let phase = 'idle';
  let latestResponse = '';
  let cancelled = false;
  let spoken = false;
  let sequence = 0;
  let currentUtterance = null;
  let naturalAudio = null;
  let naturalUrl = null;

  let recorder = null;
  let mediaStream = null;
  let clipChunks = [];
  let clipTimer = null;
  let discardClip = false;
  let forceRecorder = false;
  const canRecord = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);

  function phaseSet(next, label, description) {
    phase = next;
    root.querySelector('.voice-console').dataset.voicePhase = next;
    stateText.textContent = label;
    hint.textContent = description;
    action.textContent = next === 'listening' ? 'Termina e invia'
      : next === 'thinking' ? 'Elaborazione in corso'
      : next === 'speaking' ? 'Interrompi e parla'
      : 'Tocca per parlare';
    mic.setAttribute('aria-label', action.textContent);
    mic.disabled = next === 'thinking' || next === 'unsupported';
    stop.disabled = next === 'idle' || next === 'unsupported';
  }

  function stopAudio() {
    spoken = false;
    if (naturalAudio) { try { naturalAudio.pause(); naturalAudio.removeAttribute('src'); } catch (_) {} }
    naturalAudio = null;
    if (naturalUrl) URL.revokeObjectURL(naturalUrl);
    naturalUrl = null;
    if (synthesis) {
      try { synthesis.cancel(); } catch (_) {}
    }
    currentUtterance = null;
  }


  function releaseMicrophone() {
    clearTimeout(clipTimer);
    clipTimer = null;
    if (mediaStream) {
      mediaStream.getTracks().forEach(track => track.stop());
      mediaStream = null;
    }
  }

  function cancelRecorder() {
    discardClip = true;
    if (recorder && recorder.state !== 'inactive') {
      try { recorder.stop(); } catch (_) {}
    }
    recorder = null;
    clipChunks = [];
    releaseMicrophone();
  }

  function cancelRecognition() {
    cancelled = true;
    const active = recognizer;
    recognizer = null;
    if (active) {
      try { active.abort(); } catch (_) {}
    }
  }

  function stopVoice() {
    sequence += 1; // Discard late UI updates, without pretending to cancel server work.
    cancelRecognition();
    cancelRecorder();
    stopAudio();
    if (phase !== 'unsupported') phaseSet('idle', 'In pausa', 'Premi il microfono quando vuoi riprendere.');
  }

  function addTurn(role, value) {
    const p = document.createElement('p');
    p.className = 'voice-turn ' + (role === 'assistant' ? 'voice-turn-ai' : 'voice-turn-user');
    const who = document.createElement('strong');
    who.textContent = role === 'assistant' ? 'JARVIS' : 'TU';
    const text = document.createElement('span');
    text.textContent = value;
    p.append(who, text);
    history.prepend(p);
    while (history.children.length > 8) history.lastElementChild.remove();
  }

  async function speakResponse(value) {
    // Gemini neural TTS first; built-in Siri voice only if server synthesis fails.
    stopAudio();
    const speechSeq = sequence;
    phaseSet('speaking', 'Preparo una voce naturale', 'Jarvis sta generando la risposta vocale…');
    try {
      const reply = await fetch('/api/voice/speak', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Accept': 'audio/wav', 'Content-Type': 'application/json', 'X-Jarvis-Request': '1'},
        body: JSON.stringify({text: value.slice(0, 1100), voice: 'Orus'})
      });
      if (!reply.ok) throw new Error('Neural TTS not available');
      const blob = await reply.blob();
      if (speechSeq !== sequence || !root.classList.contains('active')) return;
      naturalUrl = URL.createObjectURL(blob);
      const audio = new Audio(naturalUrl);
      naturalAudio = audio;
      audio.onended = () => {
        if (naturalAudio !== audio) return;
        stopAudio();
        phaseSet('idle', 'Risposta completata', 'Premi il microfono quando vuoi continuare.');
      };
      audio.onerror = () => {
        if (naturalAudio !== audio) return;
        stopAudio();
        speakBrowserResponse(value);
      };
      await audio.play();
      phaseSet('speaking', 'Jarvis sta parlando con voce AI', 'Puoi interrompere la risposta.');
    } catch (_) {
      if (speechSeq === sequence && root.classList.contains('active')) {
        stopAudio();
        speakBrowserResponse(value);
      }
    }
  }

  function speakBrowserResponse(value) {
    if (!synthesis || typeof window.SpeechSynthesisUtterance !== 'function') {
      phaseSet('idle', 'Risposta pronta', 'Lettura vocale non disponibile in questo browser.');
      return;
    }
    stopAudio();
    const utterance = new SpeechSynthesisUtterance(value.slice(0, 12000));
    utterance.lang = 'it-IT';
    utterance.rate = 1.02;
    utterance.pitch = 1;
    const voices = synthesis.getVoices ? synthesis.getVoices() : [];
    const it = voices.find(v => v.lang && v.lang.toLowerCase().startsWith('it'));
    if (it) utterance.voice = it;
    currentUtterance = utterance;
    utterance.onstart = () => {
      if (currentUtterance !== utterance) return;
      spoken = true;
      phaseSet('speaking', 'Jarvis sta parlando', 'Puoi interrompere la risposta e fare un’altra domanda.');
    };
    utterance.onend = () => {
      if (currentUtterance !== utterance) return;
      currentUtterance = null;
      spoken = false;
      phaseSet('idle', 'Risposta completata', 'Premi il microfono per continuare.');
    };
    utterance.onerror = () => {
      if (currentUtterance !== utterance) return;
      currentUtterance = null;
      spoken = false;
      phaseSet('idle', 'Risposta disponibile', 'Se non senti l’audio, premi Riascolta risposta.');
    };
    try {
      synthesis.speak(utterance);
      // Speech output is not guaranteed on every iOS browser after an async request.
      phaseSet('speaking', 'Sto leggendo la risposta', 'Se non senti nulla, usa Riascolta risposta.');
    } catch (_) {
      phaseSet('idle', 'Risposta disponibile', 'Tocca Riascolta risposta per avviare l’audio.');
    }
  }

  async function askVoice(text) {
    const requestSeq = ++sequence;
    phaseSet('thinking', 'Jarvis sta pensando', 'Sto preparando la risposta.');
    addTurn('user', text);
    answer.textContent = 'Sto preparando la risposta…';
    try {
      const data = await api('/api/chat', {
        method: 'POST', body: JSON.stringify({text, conversation: 'voice'})
      });
      if (requestSeq !== sequence || !root.classList.contains('active')) return;
      latestResponse = String(data.reply || '');
      answer.textContent = latestResponse;
      repeat.disabled = !latestResponse;
      addTurn('assistant', latestResponse || 'Non ho ricevuto una risposta.');
      if (latestResponse) speakResponse(latestResponse);
      else phaseSet('idle', 'Nessuna risposta', 'Riprova a parlare.');
    } catch (error) {
      if (requestSeq !== sequence || !root.classList.contains('active')) return;
      answer.textContent = 'Non riesco a rispondere: ' + error.message;
      phaseSet('idle', 'Richiesta non riuscita', 'Riprova con il microfono.');
    }
  }

  async function loadVoiceHistory() {
    if (!authenticated) {
      history.replaceChildren();
      return;
    }
    try {
      const result = await api('/api/history?conversation=voice');
      if (!root.classList.contains('active')) return;
      history.replaceChildren();
      const messages = (result.messages || []).slice(-8);
      // Display oldest first. addTurn prepends the newer messages.
      messages.forEach(item => addTurn(item.role, item.content));
      const lastAssistant = [...messages].reverse().find(item => item.role === 'assistant');
      if (lastAssistant) {
        latestResponse = String(lastAssistant.content || '');
        repeat.disabled = !latestResponse;
        answer.textContent = latestResponse;
      }
    } catch (_) {
      // A stale session is handled by the standard authentication screen.
    }
  }


  async function transcribeClip(blob, mime) {
    const requestSeq = ++sequence;
    phaseSet('thinking', 'Sto trascrivendo', 'Sto riconoscendo le tue parole…');
    live.textContent = 'Trascrizione in corso…';
    try {
      const response = await fetch('/api/voice/transcribe', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Accept': 'application/json', 'Content-Type': mime, 'X-Jarvis-Request': '1'},
        body: blob
      });
      let data = {};
      try { data = await response.json(); } catch (_) {}
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Errore ' + response.status);
      if (requestSeq !== sequence || !root.classList.contains('active')) return;
      const text = String(data.text || '').trim().slice(0, 3900);
      if (!text) throw new Error('Non ho riconosciuto parole. Riprova.');
      live.textContent = text;
      await askVoice(text);
    } catch (error) {
      if (requestSeq !== sequence || !root.classList.contains('active')) return;
      phaseSet('idle', 'Trascrizione non riuscita', error.message || 'Riprova a parlare.');
    }
  }

  async function beginRecordedCapture() {
    if (!canRecord) {
      phaseSet('unsupported', 'Microfono non supportato',
        'Apri Jarvis in Safari e verifica i permessi del microfono.');
      return;
    }
    cancelRecognition();
    stopAudio();
    discardClip = false;
    const captureSeq = sequence;
    phaseSet('thinking', 'Attivazione microfono', 'Consenti a Safari di accedere al microfono.');
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}});
    } catch (_) {
      phaseSet('idle', 'Permesso microfono negato', 'Consenti il microfono nelle impostazioni del sito e riprova.');
      return;
    }
    if (captureSeq !== sequence || !root.classList.contains('active')) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }
    mediaStream = stream;
    clipChunks = [];
    const types = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg'];
    const supported = types.find(type => MediaRecorder.isTypeSupported(type));
    try {
      recorder = new MediaRecorder(stream, supported ? {mimeType: supported} : {});
    } catch (_) {
      releaseMicrophone();
      phaseSet('idle', 'Registrazione non supportata', 'Questo browser non riesce a registrare audio.');
      return;
    }
    const current = recorder;
    current.ondataavailable = event => {
      if (event.data && event.data.size) clipChunks.push(event.data);
    };
    current.onerror = () => {
      if (recorder !== current) return;
      discardClip = true;
      phaseSet('idle', 'Problema col microfono', 'Riprova a registrare.');
      releaseMicrophone();
    };
    current.onstop = () => {
      if (recorder !== current) return;
      recorder = null;
      releaseMicrophone();
      if (discardClip || captureSeq !== sequence || !root.classList.contains('active')) {
        clipChunks = [];
        return;
      }
      const mime = (current.mimeType || supported || 'audio/mp4').split(';')[0].trim();
      const audio = new Blob(clipChunks, {type: mime});
      clipChunks = [];
      if (audio.size < 100) {
        phaseSet('idle', 'Audio troppo breve', 'Parla più a lungo e riprova.');
        return;
      }
      void transcribeClip(audio, mime);
    };
    try {
      current.start(250);
      live.textContent = 'Registrazione in corso…';
      phaseSet('listening', 'Ti ascolto', 'Parla normalmente, poi tocca di nuovo il microfono per inviare.');
      clipTimer = setTimeout(() => {
        if (recorder === current && current.state === 'recording') current.stop();
      }, 19000);
    } catch (_) {
      cancelRecorder();
      phaseSet('idle', 'Non riesco a registrare', 'Controlla i permessi del microfono.');
    }
  }

  function startCapture() {
    if (!authenticated) {
      page('settings');
      notify('Prima accedi a Jarvis dalle Impostazioni.');
      return;
    }
    if (!Recognition || forceRecorder) {
      void beginRecordedCapture();
      return;
    }
    if (phase === 'thinking') return;
    cancelRecognition();
    stopAudio();
    let heard = '';
    cancelled = false;
    const local = new Recognition();
    recognizer = local;
    local.lang = 'it-IT';
    local.continuous = false;
    local.interimResults = true;
    local.maxAlternatives = 1;
    live.textContent = 'Ascolto in corso…';
    phaseSet('listening', 'Ti ascolto', 'Parla normalmente. Jarvis invierà la domanda quando smetti.');
    local.onresult = event => {
      if (recognizer !== local || cancelled) return;
      const parts = Array.from(event.results || []).map(result =>
        result[0] && result[0].transcript ? result[0].transcript : '');
      heard = parts.join(' ').trim().slice(0, 3900);
      live.textContent = heard || 'Ti ascolto…';
    };
    local.onerror = event => {
      if (recognizer !== local || cancelled) return;
      cancelled = true;
      const reasons = {
        'not-allowed': 'Consenti il microfono in Safari e riprova.',
        'service-not-allowed': 'Abilita Siri e Dettatura nelle impostazioni iPhone.',
        'audio-capture': 'Nessun microfono disponibile.',
        'network': 'Il riconoscimento vocale richiede una connessione attiva.',
        'no-speech': 'Non ho rilevato parole. Riprova.',
        'language-not-supported': 'La lingua italiana non è disponibile su questo dispositivo.'
      };
      const reason = reasons[event.error] || 'Riconoscimento vocale non riuscito.';
      if (canRecord && event.error !== 'no-speech') {
        forceRecorder = true;
        phaseSet('idle', 'Modalità registrazione disponibile',
          'Il riconoscimento di Safari non funziona. Tocca di nuovo il microfono per registrare e trascrivere sul server.');
      } else {
        phaseSet('idle', 'Microfono non disponibile', reason);
      }
    };
    local.onend = () => {
      if (recognizer !== local) return;
      recognizer = null;
      if (cancelled || !root.classList.contains('active') || document.hidden) return;
      if (heard) { void askVoice(heard); return; }
      phaseSet('idle', 'Non ho sentito la domanda', 'Tocca di nuovo il microfono e parla.');
    };
    try { local.start(); }
    catch (_) {
      recognizer = null;
      cancelled = true;
      phaseSet('idle', 'Impossibile attivare il microfono',
        'Controlla i permessi di Safari e riprova.');
    }
  }

  mic.addEventListener('click', () => {
    if (phase === 'listening') {
      if (recorder && recorder.state === 'recording') {
        try { recorder.stop(); } catch (_) { cancelRecorder(); phaseSet('idle', 'In pausa', 'Riprova.'); }
      } else if (recognizer) {
        try { recognizer.stop(); } catch (_) { cancelRecognition(); phaseSet('idle', 'In pausa', 'Riprova.'); }
      }
      return;
    }
    if (phase === 'speaking') stopAudio();
    startCapture();
  });
  stop.addEventListener('click', () => stopVoice());
  repeat.addEventListener('click', () => {
    if (!latestResponse) return;
    cancelRecognition();
    speakResponse(latestResponse);
  });
  document.addEventListener('jarvis:pagechange', event => {
    if (event.detail.name !== 'voice') stopVoice();
    else void loadVoiceHistory();
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopVoice();
  });
  document.addEventListener('jarvis:logout', stopVoice);
  if (!Recognition && !canRecord) {
    phaseSet('unsupported', 'Voce non disponibile',
      'Il browser non permette riconoscimento né registrazione audio. Apri Jarvis in Safari.');
  } else {
    phaseSet('idle', 'Pronto ad ascoltarti',
      Recognition ? 'Tocca il microfono e parla a Jarvis.' : 'Tocca il microfono, parla e tocca di nuovo per inviare.');
  }
})();
