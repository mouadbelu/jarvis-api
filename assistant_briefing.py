"""Private, deterministic personal briefings for Jarvis chat.

No inbox contents are sent to any external LLM by this module. Incoming
Gmail headers and snippets are displayed as data, never interpreted as
instructions or actions.
"""
import os
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import gmail_api


def _normalize(value: str) -> str:
    value = unicodedata.normalize('NFKD', value.lower())
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    return ' '.join(re.sub(r'[^a-z0-9 ]+', ' ', value).split())


_GENERAL = {
    'dammi qualche aggiornamento', 'dammi aggiornamenti',
    'dammi degli aggiornamenti', 'hai qualche aggiornamento',
    'che novita ci sono', 'hai novita', 'novita', 'aggiornami',
    'fammi un briefing', 'fammi il briefing', 'briefing',
    'fammi un riepilogo', 'fammi il riepilogo',
    'cosa c e di nuovo', 'cosa ce di nuovo', 'buongiorno jarvis',
    'dimmi cosa e successo oggi', 'che aggiornamenti ci sono',
}
_MAIL = {
    'controlla la posta', 'controlla la mia posta', 'controllami la posta',
    'controlla le email', 'controllami le email', 'controlla le mie email',
    'leggi le email', 'leggi la posta', 'hai nuove email',
    'ho nuove email', 'ci sono nuove email',
    'quante email ho', 'quante mail ho',
    'quante email non lette ho', 'quante mail non lette ho',
    'dammi aggiornamenti sulle email', 'aggiornami sulle email',
    'novita nella posta', 'ci sono novita nella posta',
}


def classify(text: str) -> str | None:
    normalized = _normalize(text)
    if normalized in _MAIL:
        return 'mail'
    if normalized in _GENERAL:
        return 'overview'
    return None


def _safe(value: object, max_length: int) -> str:
    # Avoid control characters, log injection and extremely long mail fields.
    return ' '.join(str(value or '').split())[:max_length]


async def personal_update(store, text: str) -> str | None:
    mode = classify(text)
    if mode is None:
        return None

    try:
        today = datetime.now(ZoneInfo(os.getenv('JARVIS_TIMEZONE', 'Europe/Berlin')))
    except (ValueError, KeyError):
        today = datetime.now(ZoneInfo('Europe/Berlin'))
    now = today.strftime('%d/%m/%Y, ore %H:%M')
    lines = [f"Aggiornamento verificato alle {now}."]

    if not gmail_api.connected(store):
        lines.append("Gmail non è ancora collegato a Jarvis. Apri la sezione Posta e premi Collega per consentirmi di leggere le email.")
    else:
        try:
            result = await gmail_api.inbox(store)
            unread = int(result.get('unread', 0))
            lines.append(f"Gmail: {unread} messaggi non letti nella posta in arrivo.")
            messages = result.get('messages', [])
            if messages:
                lines.append("Ecco alcune delle email non lette più recenti:")
                for message in messages[:4]:
                    sender = _safe(message.get('from', 'Mittente sconosciuto'), 85)
                    subject = _safe(message.get('subject', 'Senza oggetto'), 130)
                    lines.append(f"• {sender}: {subject}")
            else:
                lines.append("Non risultano messaggi non letti nella ricerca della posta in arrivo.")
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            print("Personal briefing Gmail failed: " + type(exc).__name__, flush=True)
            lines.append("Gmail risulta collegato, ma la lettura non è riuscita. Apri Posta e verifica il collegamento.")

    if mode == 'overview':
        lines.append("Non ho un collegamento diretto alle chat private WhatsApp/Instagram, al calendario o alle notizie in tempo reale: non inventerò aggiornamenti su queste fonti.")
    else:
        lines.append("Posso preparare un'email, ma non ne invierò nessuna senza la tua conferma esplicita.")
    return '\n\n'.join([lines[0], '\n'.join(lines[1:])])
