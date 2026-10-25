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
    if (synthesis) {
      try { synthesis.cancel(); } catch (_) {}
    }
    currentUtterance = null;
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

  function speakResponse(value) {
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

  function startCapture() {
    if (!authenticated) {
      page('settings');
      notify('Prima accedi a Jarvis dalle Impostazioni.');
      return;
    }
    if (!Recognition) {
      phaseSet('unsupported', 'Riconoscimento non disponibile',
        'Apri Jarvis in Safari su iPhone. Puoi usare la dettatura della tastiera nella Chat.');
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
      phaseSet('idle', 'Microfono non disponibile', reason);
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
      if (recognizer) {
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
  if (!Recognition) {
    phaseSet('unsupported', 'Voce non disponibile',
      'Usa Safari su iPhone con Siri attivo: altri browser possono limitare il microfono.');
  } else {
    phaseSet('idle', 'Pronto ad ascoltarti', 'Tocca il microfono e parla a Jarvis.');
  }
})();
