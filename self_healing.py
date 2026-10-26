"""Safe, bounded self-healing for Jarvis.

In-process circuit breakers isolate failing AI providers and automatically probe
them again after cooldown. No database deletion, environment edits, code changes,
credential rotation or external actions are performed.
"""
from collections import deque
from datetime import datetime, timezone
import os
import sqlite3
import threading
import time


_LOCK = threading.RLock()
_PROVIDERS = ('OpenAI', 'Gemini', 'Claude')
_state = {name: {'status': 'unknown', 'failures': 0, 'until': 0.0, 'code': None}
          for name in _PROVIDERS}
_events = deque(maxlen=30)
_last_check = None
_db_ok = None


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _event(kind, message):
    # Only hardcoded descriptions from this module: no user prompts, API keys,
    # mail content, audio, raw error responses or request URLs.
    with _LOCK:
        _events.appendleft({'time': _utc(), 'kind': kind, 'message': message})


def reset_for_tests():
    """Tests only; the production process never calls this function."""
    global _last_check, _db_ok
    with _LOCK:
        for name in _PROVIDERS:
            _state[name] = {'status': 'unknown', 'failures': 0, 'until': 0.0, 'code': None}
        _events.clear()
        _last_check = None
        _db_ok = None


def may_try(name):
    with _LOCK:
        state = _state.get(name)
        if state is None:
            return False
        return time.monotonic() >= state['until']


def provider_ok(name):
    with _LOCK:
        current = _state.get(name)
        if current is None:
            return
        was_bad = current['status'] in ('cooldown', 'error')
        current.update(status='online', failures=0, until=0.0, code=None)
    if was_bad:
        _event('recovered', name + ': collegamento AI ripristinato automaticamente.')


def provider_failed(name, http_status=None, code=None):
    """Categorize without ever logging the raw provider response."""
    if name not in _state:
        return
    code = str(code or '')
    with _LOCK:
        state = _state[name]
        state['failures'] = min(20, state['failures'] + 1)
        failures = state['failures']
        if http_status in (401, 403):
            delay, label = 1800, 'credenziale o autorizzazione non valida'
        elif http_status == 429 and code in ('credit_balance_exhausted', 'insufficient_quota', 'billing_hard_limit_reached'):
            delay, label = 21600, 'credito API esaurito'
        elif http_status == 429:
            delay, label = min(900, 60 * (2 ** min(failures - 1, 4))), 'limite di richieste'
        elif http_status in (400, 404):
            delay, label = 900, 'modello o richiesta non accettata'
        else:
            delay, label = min(300, 15 * (2 ** min(failures - 1, 5))), 'errore temporaneo'
        state.update(status='cooldown', until=time.monotonic() + delay,
                     code=label)
    _event('automatic', name + ': ' + label + '; uso un provider alternativo e riprovo più tardi.')


def check_database(store):
    """Read-only check: corruption must never trigger destructive auto-repair."""
    global _last_check, _db_ok
    try:
        with store.db() as db:
            result = db.execute('PRAGMA quick_check(1)').fetchone()
        healthy = bool(result and result[0] == 'ok')
    except (sqlite3.Error, OSError):
        healthy = False
    with _LOCK:
        changed = _db_ok is not None and _db_ok != healthy
        _db_ok = healthy
        _last_check = _utc()
    if changed and healthy:
        _event('recovered', 'Archivio locale nuovamente raggiungibile.')
    elif changed and not healthy:
        _event('attention', 'Archivio locale non integro o indisponibile; dati preservati, intervento necessario.')
    return healthy


def snapshot(store=None, check_db=False):
    if store is not None and check_db:
        check_database(store)
    active = {'OpenAI': bool(os.getenv('JARVIS_OPENAI_KEY') or os.getenv('OPENAI_API_KEY')),
              'Gemini': bool(os.getenv('JARVIS_GEMINI_KEY')),
              'Claude': bool(os.getenv('JARVIS_CLAUDE_KEY'))}
    now = time.monotonic()
    with _LOCK:
        providers = {}
        for name in _PROVIDERS:
            info = _state[name]
            if not active[name]:
                state = 'non_configurato'
            elif now < info['until']:
                state = 'pausa_automatica'
            else:
                state = info['status'] if info['status'] != 'cooldown' else 'pronto_al_ritest'
            providers[name] = {'status': state, 'detail': info['code'] or '',
                               'retry_in_seconds': max(0, int(info['until'] - now)) if active[name] else 0}
        recent = list(_events)
        db_ok = _db_ok
        checked_at = _last_check
    return {'system': 'attenzione' if db_ok is False else 'operativo',
            'database': 'non_disponibile' if db_ok is False else 'ok' if db_ok else 'non_verificato',
            'last_check': checked_at, 'providers': providers, 'events': recent,
            'capabilities': {
                'safe_provider_failover': True,
                'automatic_cooldown': True,
                'periodic_database_check': True,
                'can_edit_code_or_secrets': False,
                'can_delete_or_send_without_confirmation': False,
            }}


async def monitor_database(store, interval=600):
    """Cheap independent check while the process is running, no external calls."""
    import asyncio
    while True:
        try:
            await asyncio.to_thread(check_database, store)
        except Exception:
            _event('attention', 'Controllo locale temporaneamente indisponibile.')
        await asyncio.sleep(interval)
