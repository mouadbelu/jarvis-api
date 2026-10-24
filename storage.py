"""Single-user SQLite data storage. Set JARVIS_DB_PATH to a persistent volume in production."""
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone


class Store:
    def __init__(self, path=None):
        self.path = path or os.getenv('JARVIS_DB_PATH', '/tmp/jarvis.sqlite3')
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with self.db() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, conversation TEXT NOT NULL,
                    role TEXT NOT NULL, content TEXT NOT NULL, at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS messages_conversation ON messages(conversation, id);
                CREATE TABLE IF NOT EXISTS memories (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS secrets (key TEXT PRIMARY KEY, cipher TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS mail_drafts (
                    id TEXT PRIMARY KEY, recipient TEXT NOT NULL, subject TEXT NOT NULL,
                    body TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL);
            ''')

    @contextmanager
    def db(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def add_message(self, conversation, role, content):
        with self.db() as con:
            con.execute('INSERT INTO messages(conversation,role,content,at) VALUES(?,?,?,?)',
                        (conversation, role, content, datetime.now(timezone.utc).isoformat()))

    def history(self, conversation='main', limit=30):
        with self.db() as con:
            rows = con.execute('SELECT role,content,at FROM messages WHERE conversation=? ORDER BY id DESC LIMIT ?',
                               (conversation, limit)).fetchall()
        return [dict(row) for row in reversed(rows)]

    def clear_history(self, conversation='main'):
        with self.db() as con:
            con.execute('DELETE FROM messages WHERE conversation=?', (conversation,))

    def memories(self):
        with self.db() as con:
            return {row['key']: row['value'] for row in con.execute('SELECT key,value FROM memories ORDER BY key')}

    def remember(self, key, value):
        with self.db() as con:
            con.execute('INSERT INTO memories(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))

    def forget(self, key):
        with self.db() as con:
            con.execute('DELETE FROM memories WHERE key=?', (key,))

    def set_secret(self, key, cipher):
        with self.db() as con:
            con.execute('INSERT INTO secrets(key,cipher) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET cipher=excluded.cipher', (key, cipher))

    def get_secret(self, key):
        with self.db() as con:
            row = con.execute('SELECT cipher FROM secrets WHERE key=?', (key,)).fetchone()
            return row['cipher'] if row else None

    def delete_secret(self, key):
        with self.db() as con:
            con.execute('DELETE FROM secrets WHERE key=?', (key,))

    def make_draft(self, recipient, subject, body):
        draft_id = str(uuid.uuid4())
        with self.db() as con:
            con.execute('INSERT INTO mail_drafts(id,recipient,subject,body,state,created_at) VALUES(?,?,?,?,?,?)',
                        (draft_id, recipient, subject, body, 'pending', datetime.now(timezone.utc).isoformat()))
        return draft_id

    def consume_draft(self, draft_id):
        """Atomically mark a draft consumed BEFORE transmission to prevent duplicate sends.
        On an ambiguous network failure we intentionally do not reset it.
        """
        with self.db() as con:
            cur = con.execute("UPDATE mail_drafts SET state='sending' WHERE id=? AND state='pending' AND datetime(created_at) >= datetime('now','-30 minutes')", (draft_id,))
            if cur.rowcount == 0:
                return None
            row = con.execute('SELECT * FROM mail_drafts WHERE id=?', (draft_id,)).fetchone()
            return dict(row)

    def mark_sent(self, draft_id):
        with self.db() as con:
            con.execute("UPDATE mail_drafts SET state='sent' WHERE id=? AND state='sending'", (draft_id,))
