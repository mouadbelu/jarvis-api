'use strict';
const $ = id => document.getElementById(id);
// Migrates away from browser-readable root tokens. Re-login once after upgrade.
sessionStorage.removeItem('jarvis_token');
let authenticated = false;
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
  if (name === 'settings') { loadMemory().catch(() => {}); loadEmergencyStatus().catch(() => {}); }
  if (name === 'growth') loadGrowth().catch(e => notify(e.message));
  document.dispatchEvent(new CustomEvent('jarvis:pagechange', {detail: {name}}));
}
async function api(path, options={}) {
  const method=(options.method||'GET').toUpperCase();
  const headers = Object.assign(
    {'Accept':'application/json'},
    options.body ? {'Content-Type':'application/json'} : {},
    !['GET','HEAD','OPTIONS'].includes(method) ? {'X-Jarvis-Request':'1'} : {}
  );
  let r;
  try { r = await fetch(path, Object.assign({}, options, {headers, credentials:'same-origin'})); }
  catch (_) { throw new Error('Connessione non disponibile. Controlla internet o Railway.'); }
  let result;
  try { result = await r.json(); } catch (_) { result = {}; }
  if (!r.ok) {
    let reason = typeof result.detail === 'string' ? result.detail : 'Errore ' + r.status;
    if (r.status === 401) { authenticated=false; $('connection').classList.remove('ok'); status('Sessione scaduta o accesso non valido.'); }
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
  if (!publicConfig.access_ready) {
    authenticated=false;
    $('mode').textContent='Configura la chiave di accesso su Railway';
    return;
  }
  try {
    await api('/api/auth/status');
    authenticated=true;
    $('connection').classList.add('ok');
    $('mode').textContent=publicConfig.ai_ready?'Pronto ad assisterti':'Configura un provider AI su Railway';
    status('Sessione protetta attiva.');
    await Promise.allSettled([loadBriefing(),loadHistory()]);
  } catch (_) {
    authenticated=false;
    $('connection').classList.remove('ok');
    $('mode').textContent='Apri Impostazioni per accedere';
    status('Accedi per iniziare una sessione sicura.');
  }
}
async function loadBriefing() {
  if (!authenticated) { notify('Prima accedi dalle Impostazioni.'); return; }
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
  if (!authenticated) return;
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
  if (!authenticated) { page('settings'); notify('Accedi prima di usare Jarvis.'); return; }
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
  const input=$('access');
  const value=input.value.trim();
  input.value='';
  if (value.length<24) {
    notify('Token non valido. Deve avere almeno 24 caratteri.');
    return;
  }
  try {
    await api('/api/auth/login',{method:'POST',body:JSON.stringify({token:value})});
    await check();
    if(authenticated)notify('Sessione protetta attivata. Le chiavi restano sul server.');
  } catch(e) {
    authenticated=false;
    notify(e.message);
  }
});
function clearPrivateScreen() {
  document.dispatchEvent(new Event('jarvis:logout'));
  authenticated=false;
  $('connection').classList.remove('ok');
  status('Sessione chiusa su questo dispositivo.');
  $('messages').replaceChildren();
  $('home-mail').replaceChildren();
  $('mail-list').replaceChildren();
  $('growth-missions').replaceChildren();
  $('growth-ideas').replaceChildren();
  $('growth-radar').replaceChildren();
  $('unread').textContent='—';
  $('mode').textContent='Accesso necessario';
}
$('logout').onclick=async () => {
  try {
    await api('/api/auth/logout',{method:'POST'});
    clearPrivateScreen();
    notify('Sessione revocata.');
  } catch(e) {
    notify('Impossibile confermare la disconnessione: '+e.message);
  }
};
$('logout-all').onclick=async () => {
  if(!confirm('Revocare tutte le sessioni di Jarvis su ogni dispositivo?'))return;
  try {
    await api('/api/auth/logout-all',{method:'POST'});
    clearPrivateScreen();
    notify('Tutte le sessioni sono state revocate.');
  } catch(e) {
    notify('Revoca non confermata: '+e.message);
  }
};
async function loadMemory() {
  if (!authenticated) return;
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
  if (!authenticated) return;
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

/* Personal Growth Lab. No external action happens without a user click. */
let growthLoaded=false;
function growthEl(tag, className, content) {
  const e=document.createElement(tag);
  if(className)e.className=className;
  if(content!==undefined)e.textContent=content;
  return e;
}
function growthField(id, value) {
  const el=$(id);
  if(document.activeElement!==el)el.value=value===undefined || value===null ? '' : String(value);
}
function growthIdeas(data) {
  const list=$('growth-ideas');list.replaceChildren();
  if(!data.length){
    list.append(growthEl('p','muted','Genera la prima idea. Ti darò cliente, offerta, verifica commerciale e rischi.'));
    return;
  }
  const fields=[
    ['customer','Cliente ideale'],['offer','Proposta da vendere'],
    ['revenue_test','Come testare il ricavo'],['first_test','Primi 7 giorni'],
    ['costs_and_risks','Costi e rischi']
  ];
  for(const idea of data){
    const card=growthEl('article','growth-idea');
    const label=idea.source==='ai_da_validare'?'PROPOSTA AI • DA VERIFICARE':'MODELLO • DA VERIFICARE';
    card.append(growthEl('small','',label),growthEl('h3','',idea.title||'Idea imprenditoriale'));
    const dl=growthEl('dl');
    for(const [key,title] of fields){
      dl.append(growthEl('dt','',title),growthEl('dd','',idea[key]||'Da approfondire'));
    }
    card.append(dl);list.append(card);
  }
}
function growthRender(data) {
  growthLoaded=true;
  $('growth-day').textContent='Missioni del '+data.date;
  $('growth-finished').textContent=data.done_today+'/'+data.tasks.length;
  $('growth-streak').textContent=data.streak_days;
  $('growth-all').textContent=data.completed_total;
  $('growth-progress-fill').style.width=(data.tasks.length?100*data.done_today/data.tasks.length:0)+'%';
  const list=$('growth-missions');list.replaceChildren();
  for(const task of data.tasks){
    const card=growthEl('article','growth-task'+(task.done?' done':''));
    const checkbox=growthEl('input');checkbox.type='checkbox';checkbox.checked=!!task.done;
    checkbox.setAttribute('aria-label','Completa missione '+task.category);
    const label=growthEl('label');
    label.append(growthEl('small','',task.category.toUpperCase()),document.createTextNode(task.title));
    const id='growth-'+task.id.replace(/[^a-zA-Z0-9]/g,'-');
    checkbox.id=id;label.htmlFor=id;
    checkbox.onchange=async()=>{
      checkbox.disabled=true;
      try{
        const updated=await api('/api/growth/tasks/'+encodeURIComponent(task.id),{
          method:'PATCH',body:JSON.stringify({done:checkbox.checked})
        });
        growthRender(updated);
      }catch(err){
        checkbox.checked=!checkbox.checked;checkbox.disabled=false;notify(err.message);
      }
    };
    card.append(checkbox,label);list.append(card);
  }
  if(!list.children.length)list.append(growthEl('p','muted','Missioni non disponibili.'));
  growthIdeas(data.ideas||[]);
  const radar=$('growth-radar');radar.replaceChildren();
  for(const entry of (data.radar||[])){
    const link=growthEl('a','growth-radar-item',entry.label+' ↗');
    if(/^https:\/\//.test(entry.url)){
      link.href=entry.url;link.target='_blank';link.rel='noopener noreferrer';
      radar.append(link);
    }
  }
  if(!document.activeElement || !document.activeElement.closest('#growth-profile-form')){
    growthField('growth-focus',data.profile.focus);
    growthField('growth-market',data.profile.market);
    growthField('growth-minutes',data.profile.minutes_per_day);
    growthField('growth-budget',data.profile.starting_budget_eur);
    growthField('growth-goal',data.profile.goal_90_days);
  }
}
async function loadGrowth() {
  if(!authenticated){notify('Accedi dalle Impostazioni per iniziare il Growth Lab.');return;}
  growthRender(await api('/api/growth'));
}
$('growth-reload').onclick=()=>loadGrowth().catch(err=>notify(err.message));
$('growth-profile-form').addEventListener('submit',async event=>{
  event.preventDefault();
  if(!authenticated){notify('Accedi prima dalle Impostazioni.');return;}
  const data={
    focus:$('growth-focus').value.trim(),
    market:$('growth-market').value.trim(),
    minutes_per_day:Number($('growth-minutes').value),
    starting_budget_eur:Number($('growth-budget').value),
    goal_90_days:$('growth-goal').value.trim()
  };
  try{
    await api('/api/growth/profile',{method:'PUT',body:JSON.stringify(data)});
    notify('Strategia personale salvata.');
    await loadGrowth();
  }catch(e){notify(e.message);}
});
$('growth-generate').onclick=async()=>{
  if(!authenticated){notify('Accedi prima dalle Impostazioni.');return;}
  const btn=$('growth-generate');btn.disabled=true;btn.textContent='Sto valutando un modello di business...';
  try{
    const idea=await api('/api/growth/ideas',{
      method:'POST',body:JSON.stringify({topic:$('growth-topic').value.trim()})
    });
    await loadGrowth();
    notify(idea.source==='ai_da_validare'?'Nuova proposta generata: verifica il mercato.':'Idea modello aggiunta: verifica il mercato.');
    $('growth-ideas').scrollIntoView({behavior:'smooth',block:'nearest'});
  }catch(e){notify(e.message);}
  finally{btn.disabled=false;btn.textContent='Genera una nuova idea da testare';}
};
$('growth-ask').onclick=async()=>{
  if(!authenticated){notify('Accedi prima dalle Impostazioni.');return;}
  const question=$('growth-question').value.trim();
  if(question.length<3){notify('Scrivi una domanda imprenditoriale concreta.');return;}
  const button=$('growth-ask');button.disabled=true;
  const out=$('growth-answer');out.textContent='Sto strutturando un esperimento pratico...';
  try{
    const result=await api('/api/growth/mentor',{method:'POST',body:JSON.stringify({question})});
    out.textContent=result.answer;
    if(result.mode!=='ai')notify('Guida di base: provider AI non disponibile per questa richiesta.');
  }catch(e){out.textContent='Analisi non riuscita: '+e.message;}
  finally{button.disabled=false;}
};


/* Owner-only recovery console. The independent phrase and root token never persist
   in localStorage, sessionStorage, logs or any JavaScript-readable cookie. */
function clearEmergencyInputs() {
  for (const id of ['emergency-owner','emergency-secret','emergency-secret-repeat','emergency-typed']) $(id).value='';
}
async function loadEmergencyStatus() {
  const consoleEl=$('emergency-console');
  if(!consoleEl) return;
  try {
    const info=await api('/api/emergency/status');
    consoleEl.hidden=false;
    $('emergency-state').textContent = !info.configured
      ? 'Da configurare: imposta una frase di recupero separata.'
      : info.locked ? '🔒 BLOCCO ATTIVO: accesso privato interrotto.'
      : 'Protezione proprietario attivata: Jarvis operativo.';
    $('emergency-enroll').hidden=!!info.configured;
    $('emergency-secret-repeat').parentElement.hidden=!!info.configured;
    $('emergency-unlock').hidden=!info.configured || !info.locked;
    $('emergency-lock').disabled=!info.configured || info.locked;
    $('emergency-wipe').disabled=!info.configured;
  } catch (_) {
    consoleEl.hidden=true; // Missing backend must not leave deceptive buttons visible.
  }
}
function emergencyPayload(withConfirmation=false) {
  const o={
    owner_token:$('emergency-owner').value,
    recovery_phrase:$('emergency-secret').value
  };
  if(withConfirmation) o.confirmation=$('emergency-typed').value.trim();
  return o;
}
async function emergencyCall(endpoint,payload) {
  try {
    return await api('/api/emergency/'+endpoint,{method:'POST',body:JSON.stringify(payload)});
  } finally {
    clearEmergencyInputs();
    await loadEmergencyStatus();
  }
}
$('emergency-enroll').onclick=async()=>{
  const payload=emergencyPayload();
  if(payload.recovery_phrase!==$('emergency-secret-repeat').value) {
    notify('Le due frasi di recupero non coincidono.');return;
  }
  if(!confirm('Attivare il protocollo di emergenza? Conserva la frase in un password manager: non sarà recuperabile.'))return;
  try {
    await emergencyCall('enroll',payload);
    notify('Protezione attivata. Conserva la frase fuori da Jarvis.');
  } catch(e) {notify(e.message);}
};
$('emergency-lock').onclick=async()=>{
  const payload=emergencyPayload(true);
  if(payload.confirmation!=='BLOCCA JARVIS') {
    notify('Scrivi esattamente BLOCCA JARVIS.');return;
  }
  if(!confirm('Bloccare subito tutte le funzioni private e revocare le sessioni su ogni dispositivo?'))return;
  try {
    await emergencyCall('lock',payload);
    clearPrivateScreen();
    notify('Blocco di emergenza attivo. Per riaprire usa token e frase separata.');
  } catch(e) {notify(e.message);}
};
$('emergency-unlock').onclick=async()=>{
  const payload=emergencyPayload();
  if(!confirm('Sbloccare il server Jarvis? Tutte le sessioni resteranno revocate.'))return;
  try {
    await emergencyCall('unlock',payload);
    clearPrivateScreen();
    notify('Server sbloccato. Ora effettua un nuovo accesso.');
  } catch(e) {notify(e.message);}
};
$('emergency-wipe').onclick=async()=>{
  const payload=emergencyPayload(true);
  if(payload.confirmation!=='CANCELLA TUTTO') {
    notify('Scrivi esattamente CANCELLA TUTTO.');return;
  }
  if(!confirm('ATTENZIONE: cancellare per sempre chat, memorie, dati Growth Lab e token Gmail archiviati da Jarvis?'))return;
  if(!confirm('CONFERMA FINALE: questa azione non è annullabile. Non elimina backup né credenziali di Railway/OpenAI/Google. Procedere?'))return;
  try {
    const r=await emergencyCall('wipe',payload);
    clearPrivateScreen();
    notify(r.local_data_deleted?'Dati locali cancellati. Jarvis rimane bloccato.':'Risultato incerto: controlla lo stato.');
  } catch(e) {notify('Cancellazione non confermata: '+e.message);}
};

document.querySelectorAll('.bottom button').forEach(b => b.onclick=()=>page(b.dataset.page));
$('today').textContent=new Intl.DateTimeFormat('it-IT',{weekday:'long',day:'numeric',month:'long'}).format(new Date()).toUpperCase();
const hour=new Date().getHours(); $('greeting').innerHTML=(hour<12?'Buongiorno':hour<18?'Buon pomeriggio':'Buonasera')+'<span class="accent">.</span>';
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(()=>{});
if (new URLSearchParams(location.search).get('gmail') === 'connected') { page('mail'); history.replaceState({},'', '/'); notify('Gmail collegato.'); }
check().catch(e=>notify(e.message));
