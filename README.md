# JARVIS v2 · Assistente personale iPhone

Una **Progressive Web App** privata per iPhone con backend FastAPI, chat AI, voce (dove supportata dal browser), memoria persistente, briefing giornaliero, lettura di Gmail e invio di email solo dopo una conferma esplicita.

**Stato:** codice pronto per test/deploy. Non è un'app nativa dell'App Store. Non invia notifiche push, non legge WhatsApp o Instagram e non lavora autonomamente quando non è aperta. Le API di quelle piattaforme non consentono generalmente l'accesso libero ai messaggi privati.

## 1. Installazione locale

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export JARVIS_ACCESS_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export JARVIS_OPENAI_KEY="inserisci-una-chiave-valida"
export JARVIS_DB_PATH="./jarvis.sqlite3"
uvicorn main:app --reload
```

Apri `http://127.0.0.1:8000` sul computer. Per accedere dall'iPhone serve l'URL pubblico HTTPS del servizio pubblicato.

## 2. Deploy su Railway

1. Carica il progetto nella repository GitHub **mouadbelu/jarvis-api**. Per sicurezza usa prima un *branch* di test e una pull request. Non mettere segreti nei file del repository.
2. In Railway, collega la repository e usa il comando `uvicorn main:app --host 0.0.0.0 --port $PORT` come Start Command (o imposta `Procfile` equivalente).
3. Imposta le variabili segrete Railway:

| Variabile | Necessaria | Descrizione |
| --- | --- | --- |
| `JARVIS_ACCESS_TOKEN` | **Sì** | Almeno 24 caratteri casuali. Inseriscila poi nell'app in **Impostazioni**. |
| `JARVIS_OPENAI_KEY` | Per AI | API key OpenAI, in alternativa a Gemini o Claude. Il piano ChatGPT Plus **non** include crediti API. |
| `JARVIS_GEMINI_KEY` | Alternativa | API key Google Gemini, se non usi OpenAI. |
| `JARVIS_CLAUDE_KEY` | Alternativa | API key Anthropic. |
| `JARVIS_DB_PATH` | Consigliata | Es. `/data/jarvis.sqlite3`, **con volume Railway montato su `/data`**. Senza volume i dati possono sparire al riavvio. |
| `JARVIS_TIMEZONE` | Opzionale | Es. `Europe/Berlin`. |
| `JARVIS_PUBLIC_URL` | Per Gmail | URL del tuo Railway HTTPS, senza barra finale (es. `https://nome.up.railway.app`). |
| `GOOGLE_CLIENT_ID` | Per Gmail | OAuth client tipo web application. |
| `GOOGLE_CLIENT_SECRET` | Per Gmail | OAuth client secret. |
| `JARVIS_TOKEN_KEY` | Per Gmail | Chiave cifratura Fernet, generata con `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`. **Non cambiarla dopo il collegamento**, altrimenti il token Gmail non sarà leggibile. |

4. Attiva dominio HTTPS nel servizio Railway. Verifica `https://TUO-DOMINIO/health` e apri la pagina principale.
5. Su Safari iPhone apri il sito → Condividi → **Aggiungi alla schermata Home**. Poi apri Jarvis e incolla il token di accesso in Impostazioni. Il token resta solo nella sessione locale.

## 3. Collegare Gmail (facoltativo)

1. Crea un progetto su Google Cloud Console, abilita **Gmail API**.
2. Configura OAuth consent screen con il tuo account come utente di test, secondo i requisiti di Google. Per accesso esteso/produzione, Google potrebbe richiedere verifiche di app e degli scope Gmail.
3. Crea OAuth 2.0 Client ID di tipo **Web application**. Aggiungi tra gli *Authorized redirect URIs* esattamente `https://TUO-DOMINIO/api/gmail/callback`.
4. Inserisci le variabili Google e la chiave Fernet in Railway, riavvia il servizio e apri **Posta → Collega**.
5. Google mostrerà le autorizzazioni `gmail.readonly` e `gmail.send`. Puoi revocarle dal tuo account Google. **Jarvis non invia email in background**: anteprima → conferma sullo schermo → richiesta server con codice `INVIA`.

> Nota: un OAuth client in modalità *Testing* può prevedere scadenza dei refresh token e limitazioni. Se Gmail non appare, controlla il client Google e i log di Railway. Non copiare mai token OAuth in chat.

## 4. Sicurezza e limiti

- Tutti gli endpoint personali richiedono il token nell'header `Authorization: Bearer ...`. `/ask` legacy ora richiede anch'esso il token. Le API di health/config e i file statici sono pubblici.
- Nessuna API key AI o credenziale Gmail viene inviata al browser. I token OAuth Gmail sono cifrati nel database tramite Fernet.
- Le bozze Gmail non sono inviate senza doppia conferma; un tentativo di invio consumato non viene ritentato automaticamente per evitare duplicazioni in caso di errore di rete.
- La memoria conserva solo quanto aggiungi tu. Usa un volume persistente e proteggi il tuo account Railway/GitHub.
- Voice input usa Web Speech API solo se disponibile; su Safari iOS potrebbe richiedere la dettatura della tastiera. Voice output usa `speechSynthesis`.
- Notifiche push e automazioni schedulate non sono incluse in questa versione. Per riepiloghi automatici servirebbe un servizio di scheduling e una gestione permessi separata.
- Non esiste un'app con accesso indiscriminato a chat personali WhatsApp/Instagram. Sono presenti soltanto collegamenti per aprire le app.
- La PWA funziona offline soltanto come interfaccia già memorizzata, non per chat o Gmail.

## 5. Test

```bash
pip install -r requirements-dev.txt
pytest -q
```

## API principali

- `GET /health`, `GET /api/config`
- `POST /api/chat`, `GET|DELETE /api/history`
- `GET|PUT /api/memory`, `DELETE /api/memory/{key}`
- `GET /api/briefing`
- `GET /api/gmail/status`, `POST /api/gmail/connect`, `GET /api/gmail/callback`, `POST /api/gmail/disconnect`
- `GET /api/gmail/inbox`, `POST /api/gmail/prepare`, `POST /api/gmail/send`

### Migrating from v1

Old `/ask` now requires the personal token. To avoid interruptions, deploy to a staging branch/service first. The old provider credentials remain supported. The former in-memory `memory.py` is not used by this version.
