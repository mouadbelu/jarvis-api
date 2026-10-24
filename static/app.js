'use strict';
const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('jarvis_token') || '';
let toastTimer = null;
let lastBriefing = null;
const speechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

function notify(message) {
  $('toast').textContent = message;
  $('toast').classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('toast').classList.remove('show'), 4000);
}
function status(text) { $('auth-state').textContent = text; }
function page(name) {
  document.querySelectorAll('.view').forEach(el => el.classList.toggle('active', el.id === name));
  document.querySelectorAll('.bottom button').forEach(b => {
    const active = b.dataset.page === name;
    b.classList.toggle('active', active);
    if (active) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  });
  if (name === 'chat') $('messages').scrollTop = $('messages').scrollHeight;
  if (name === 'mail') loadMail().catch(() => {});
  if (name === 'settings') loadMemory().catch(() => {});
}
async function api(path, options={}) {
  const headers = Object.assign({'Accept':'application/json'}, options.body ? {'Content-Type':'application/json'} : {}, token ? {'Authorization':'Bearer ' + token} : {});
  let r;
  try { r = await fetch(path, Object.assign({}, options, {headers})); }
  catch (_) { throw new Error('Connessione non disponibile. Controlla internet o Railway.'); }
  let result;
  try { result = await r.json(); } catch (_) { result = {}; }
  if (!r.ok) {
    let reason = typeof result.detail === 'string' ? result.detail : 'Errore ' + r.status;
    if (r.status === 401) { $('connection').classList.remove('ok'); status('Token non valido.'); }
    throw new Error(reason);
  }
  return result;
}
function info(el, text) { el.textContent = text; }
function textEmail(msg) {
  const box=document.createElement('article'); box.className='mail-item';
  const title=document.createElement('b'); title.textContent=(msg.from || 'Mittente sconosciuto') + ' · ' + (msg.subject || '(senza oggetto)');
  const excerpt=document.createElement('p'); excerpt.textContent=msg.snippet || 'Nessuna anteprima';
  box.append(title,excerpt); return box;
}
function renderEmails(target, messages, emptyText) {
  target.replaceChildren();
  if (!messages.length) { const p=document.createElement('p'); p.className='muted'; p.textContent=emptyText; target.append(p); }
  else messages.forEach(m => target.append(textEmail(m)));
}
async function check() {
  const publicConfig = await api('/api/config');
  if (!publicConfig.access_ready) { $('mode').textContent='Configura la chiave di accesso su Railway'; return; }
  if (!token) { $('mode').textContent='Apri Impostazioni per accedere'; return; }
  try {
    await api('/api/history');
    $('connection').classList.add('ok');
    $('mode').textContent=publicConfig.ai_ready ? 'Pronto ad assisterti' : 'Configura un provider AI su Railway';
    status('Accesso autorizzato.');
    await Promise.allSettled([loadBriefing(),loadHistory()]);
  } catch (e) { notify(e.message); }
}
async function loadBriefing() {
  if (!token) { notify('Prima accedi dalle Impostazioni.'); return; }
  const b=await api('/api/briefing'); lastBriefing=b;
  $('clock').textContent=b.time;
  $('date-note').textContent=b.date;
  $('unread').textContent=b.unread === null ? '—' : String(b.unread);
  $('mail-note').textContent=b.unread === null ? 'Collega Gmail' : 'Messaggi non letti';
  renderEmails($('home-mail'),b.messages || [],b.mail_error || (b.gmail_connected ? 'Nessun messaggio non letto recente.' : 'Collega Gmail per mostrare le email.'));
}
function addBubble(role, content) {
  const b=document.createElement('div'); b.className='bubble '+(role === 'user' ? 'user' : 'assistant'); b.textContent=content;
  $('messages').append(b); $('messages').scrollTop=$('messages').scrollHeight; return b;
}
async function loadHistory() {
  if (!token) return;
  const h=await api('/api/history'); $('messages').replaceChildren();
  if (!h.messages.length) addBubble('assistant','Ciao! Sono Jarvis. Da cosa iniziamo?');
  else h.messages.forEach(m => addBubble(m.role,m.content));
}
function speak(text) {
  if (!window.speechSynthesis) { notify('Sintesi vocale non disponibile.'); return; }
  window.speechSynthesis.cancel();
  const utterance=new SpeechSynthesisUtterance(text); utterance.lang='it-IT'; utterance.rate=1.05;
  window.speechSynthesis.speak(utterance);
}
$('chat-form').addEventListener('submit',async e => {
  e.preventDefault();
  const message=$('chat-input').value.trim(); if (!message) return;
  if (!token) { page('settings'); notify('Accedi prima di usare Jarvis.'); return; }
  $('chat-input').value=''; addBubble('user',message);
  document.body.classList.add('thinking'); $('neural-status').textContent='Sto elaborando la tua richiesta…';
  const pending=addBubble('assistant','Sto elaborando…'); $('send').disabled=true;
  try { const r=await api('/api/chat',{method:'POST',body:JSON.stringify({text:message})}); pending.textContent=r.reply; if ($('voice-out').checked) speak(r.reply); }
  catch(err) { pending.textContent='Non sono riuscito a rispondere: '+err.message; }
  finally { $('send').disabled=false; document.body.classList.remove('thinking'); $('neural-status').textContent='In attesa del tuo messaggio'; }
});
$('mic').addEventListener('click',() => {
  if (!speechRecognition) { notify('Dettatura non supportata da questo browser. Puoi usare il microfono della tastiera iPhone.'); return; }
  const recognition=new speechRecognition(); recognition.lang='it-IT'; recognition.interimResults=false; recognition.maxAlternatives=1;
  recognition.onresult=e => { $('chat-input').value=e.results[0][0].transcript; $('chat-input').focus(); notify('Testo dettato: controlla e premi invio.'); };
  recognition.onerror=e => notify('Microfono: '+e.error);
  try { recognition.start(); notify('Sto ascoltando...'); } catch { notify('Microfono non disponibile.'); }
});
$('clear-chat').addEventListener('click',async () => {
  if (!confirm('Cancellare la cronologia della conversazione? Le memorie salvate restano.')) return;
  try { await api('/api/history',{method:'DELETE'}); await loadHistory(); notify('Chat cancellata.'); }
  catch(e) { notify(e.message); }
});
$('open-chat').onclick=() => page('chat');
$('refresh').onclick=() => loadBriefing().catch(e=>notify(e.message));
$('speak-brief').onclick=() => {
  if (!lastBriefing) { notify('Carica prima il briefing.'); return; }
  let text='Buongiorno. Sono Jarvis. Oggi è il '+lastBriefing.date+'. Sono le '+lastBriefing.time+'. ';
  if (lastBriefing.unread !== null) text+='Hai '+lastBriefing.unread+' email non lette.';
  else text+='Gmail non è ancora collegato.';
  speak(text);
};
$('save-access').addEventListener('click',async () => {
  token=$('access').value.trim();
  if (token.length < 24) { notify('Token troppo corto. Deve avere almeno 24 caratteri.'); return; }
  sessionStorage.setItem('jarvis_token',token); $('access').value='';
  await check();
});
$('logout').onclick=() => {
  token=''; sessionStorage.removeItem('jarvis_token');
  $('connection').classList.remove('ok'); status('Sessione chiusa su questo dispositivo.');
  $('messages').replaceChildren(); $('home-mail').replaceChildren(); $('mail-list').replaceChildren();
  $('unread').textContent='—'; $('mode').textContent='Accesso necessario'; notify('Disconnesso.');
};
async function loadMemory() {
  if (!token) return;
  try {
    const result=await api('/api/memory'); const list=$('memory-list'); list.replaceChildren();
    for (const [key,value] of Object.entries(result.memories)) {
      const row=document.createElement('div'); row.className='mail-item';
      const b=document.createElement('b'); b.textContent=key;
      const p=document.createElement('p'); p.textContent=value;
      const del=document.createElement('button'); del.className='text-btn'; del.textContent='Elimina';
      del.onclick=async () => { if (!confirm('Eliminare questa memoria?')) return; try { await api('/api/memory/'+encodeURIComponent(key),{method:'DELETE'}); await loadMemory(); } catch(e){notify(e.message);} };
      row.append(b,p,del); list.append(row);
    }
  } catch(e) { notify(e.message); }
}
$('save-memory').onclick=async () => {
  const key=$('memory-key').value.trim(), value=$('memory-value').value.trim();
  if (!key || !value) { notify('Inserisci sia il nome che il testo della memoria.'); return; }
  try { await api('/api/memory',{method:'PUT',body:JSON.stringify({key,value})}); $('memory-key').value=''; $('memory-value').value=''; await loadMemory(); notify('Memoria salvata.'); }
  catch(e) { notify(e.message); }
};
async function loadMail() {
  if (!token) return;
  try {
    const state=await api('/api/gmail/status');
    $('gmail-state').textContent=state.connected ? 'Connesso' : state.configured ? 'Pronto per il collegamento' : 'OAuth non configurato su Railway';
    $('gmail-connect').textContent=state.connected ? 'Scollega' : 'Collega';
    if (!state.connected) { renderEmails($('mail-list'),[], 'Collega Gmail per leggere la posta.'); return; }
    const inbox=await api('/api/gmail/inbox');
    renderEmails($('mail-list'),inbox.messages || [], 'Non risultano email non lette nelle ultime 8.');
  } catch(e) { notify(e.message); }
}
$('gmail-connect').onclick=async () => {
  try {
    const st=await api('/api/gmail/status');
    if (st.connected) {
      if (!confirm('Scollegare Gmail? Il token salvato sul server sarà eliminato.')) return;
      await api('/api/gmail/disconnect',{method:'POST'}); await loadMail(); notify('Gmail scollegato.'); return;
    }
    const auth=await api('/api/gmail/connect',{method:'POST'});
    if (!auth.url.startsWith('https://accounts.google.com/')) throw new Error('URL di autorizzazione non valido.');
    window.location.assign(auth.url);
  } catch(e) { notify(e.message); }
};
$('load-mail').onclick=() => loadMail();
$('draft-form').addEventListener('submit',async e => {
  e.preventDefault();
  const payload={to:$('mail-to').value.trim(),subject:$('mail-subject').value.trim(),body:$('mail-body').value.trim()};
  try {
    const prepared=await api('/api/gmail/prepare',{method:'POST',body:JSON.stringify(payload)});
    const preview=prepared.preview;
    const message='QUESTA EMAIL NON È ANCORA STATA INVIATA.\n\nA: '+preview.to+'\nOggetto: '+preview.subject+'\n\n'+preview.body+'\n\nVuoi inviarla adesso?';
    if (!confirm(message)) { notify('Invio annullato. Nessuna email inviata.'); return; }
    const sent=await api('/api/gmail/send',{method:'POST',body:JSON.stringify({draft_id:prepared.draft_id,confirmation:'INVIA'})});
    if (sent.sent) { notify('Email inviata con Gmail.'); $('draft-form').reset(); }
  } catch(err) { notify(err.message); }
});
document.querySelectorAll('.bottom button').forEach(b => b.onclick=()=>page(b.dataset.page));
$('today').textContent=new Intl.DateTimeFormat('it-IT',{weekday:'long',day:'numeric',month:'long'}).format(new Date()).toUpperCase();
const hour=new Date().getHours(); $('greeting').innerHTML=(hour<12?'Buongiorno':hour<18?'Buon pomeriggio':'Buonasera')+'<span class="accent">.</span>';
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(()=>{});
if (new URLSearchParams(location.search).get('gmail') === 'connected') { page('mail'); history.replaceState({},'', '/'); notify('Gmail collegato.'); }
check().catch(e=>notify(e.message));
