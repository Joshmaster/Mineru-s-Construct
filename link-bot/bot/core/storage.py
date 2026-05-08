"""
Storage SQLite - persiste TODOs, notas, lembretes, contadores de gamificação.

Schema simples, indexado por user_jid pra suportar mais de um usuário no futuro.
"""

import sqlite3
import time
import json
from pathlib import Path
from typing import List, Optional, Dict, Any


class Storage:
    """Camada fina sobre SQLite. Thread-safe via check_same_thread=False."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False
        )
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        c = self.conn.cursor()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_jid TEXT NOT NULL,
            text TEXT NOT NULL,
            done INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL,
            done_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_todos_user ON todos(user_jid, done);

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_jid TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_jid);

        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_jid TEXT NOT NULL,
            text TEXT NOT NULL,
            trigger_at INTEGER NOT NULL,
            recurrence TEXT,
            sent INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_rem_trigger ON reminders(sent, trigger_at);

        CREATE TABLE IF NOT EXISTS counters (
            user_jid TEXT NOT NULL,
            name TEXT NOT NULL,
            value INTEGER DEFAULT 0,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (user_jid, name)
        );

        CREATE TABLE IF NOT EXISTS kv (
            user_jid TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (user_jid, key)
        );

        CREATE TABLE IF NOT EXISTS contacts (
            identity_key TEXT PRIMARY KEY,
            contact_uid TEXT,
            name TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            source TEXT,
            updated_at INTEGER NOT NULL
        );
        """)
        cols = {row["name"] for row in c.execute("PRAGMA table_info(contacts)").fetchall()}
        if "contact_uid" not in cols:
            c.execute("ALTER TABLE contacts ADD COLUMN contact_uid TEXT")
        c.execute(
            "UPDATE contacts SET contact_uid=identity_key "
            "WHERE contact_uid IS NULL OR contact_uid=''"
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_contacts_uid ON contacts(contact_uid)")
        self.conn.commit()

    # ============ TODOs ============

    def todo_add(self, user_jid: str, text: str) -> int:
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO todos (user_jid, text, created_at) VALUES (?, ?, ?)",
            (user_jid, text, int(time.time()))
        )
        self.conn.commit()
        return c.lastrowid

    def todo_list(self, user_jid: str, include_done: bool = False) -> List[Dict]:
        c = self.conn.cursor()
        if include_done:
            c.execute(
                "SELECT * FROM todos WHERE user_jid=? ORDER BY done, id DESC",
                (user_jid,)
            )
        else:
            c.execute(
                "SELECT * FROM todos WHERE user_jid=? AND done=0 ORDER BY id DESC",
                (user_jid,)
            )
        return [dict(r) for r in c.fetchall()]

    def todo_mark_done(self, user_jid: str, todo_id: int) -> bool:
        c = self.conn.cursor()
        c.execute(
            "UPDATE todos SET done=1, done_at=? WHERE id=? AND user_jid=?",
            (int(time.time()), todo_id, user_jid)
        )
        self.conn.commit()
        return c.rowcount > 0

    def todo_delete(self, user_jid: str, todo_id: int) -> bool:
        c = self.conn.cursor()
        c.execute(
            "DELETE FROM todos WHERE id=? AND user_jid=?",
            (todo_id, user_jid)
        )
        self.conn.commit()
        return c.rowcount > 0

    # ============ Notas ============

    def note_add(self, user_jid: str, content: str, tags: str = "") -> int:
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO notes (user_jid, content, tags, created_at) VALUES (?, ?, ?, ?)",
            (user_jid, content, tags, int(time.time()))
        )
        self.conn.commit()
        return c.lastrowid

    def note_search(self, user_jid: str, query: str = "",
                    limit: int = 20) -> List[Dict]:
        c = self.conn.cursor()
        if query:
            like = f"%{query}%"
            c.execute(
                "SELECT * FROM notes WHERE user_jid=? AND "
                "(content LIKE ? OR tags LIKE ?) ORDER BY id DESC LIMIT ?",
                (user_jid, like, like, limit)
            )
        else:
            c.execute(
                "SELECT * FROM notes WHERE user_jid=? ORDER BY id DESC LIMIT ?",
                (user_jid, limit)
            )
        return [dict(r) for r in c.fetchall()]

    def note_delete(self, user_jid: str, note_id: int) -> bool:
        c = self.conn.cursor()
        c.execute(
            "DELETE FROM notes WHERE id=? AND user_jid=?",
            (note_id, user_jid)
        )
        self.conn.commit()
        return c.rowcount > 0

    # ============ Lembretes ============

    def reminder_add(self, user_jid: str, text: str,
                     trigger_at: int, recurrence: str = "") -> int:
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO reminders (user_jid, text, trigger_at, recurrence, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_jid, text, trigger_at, recurrence, int(time.time()))
        )
        self.conn.commit()
        return c.lastrowid

    def reminder_list(self, user_jid: str,
                      include_sent: bool = False) -> List[Dict]:
        c = self.conn.cursor()
        if include_sent:
            c.execute(
                "SELECT * FROM reminders WHERE user_jid=? ORDER BY trigger_at",
                (user_jid,)
            )
        else:
            c.execute(
                "SELECT * FROM reminders WHERE user_jid=? AND sent=0 "
                "ORDER BY trigger_at",
                (user_jid,)
            )
        return [dict(r) for r in c.fetchall()]

    def reminder_due(self, now_ts: int) -> List[Dict]:
        """Lembretes que devem disparar agora."""
        c = self.conn.cursor()
        c.execute(
            "SELECT * FROM reminders WHERE sent=0 AND trigger_at <= ?",
            (now_ts,)
        )
        return [dict(r) for r in c.fetchall()]

    def reminder_mark_sent(self, reminder_id: int):
        c = self.conn.cursor()
        c.execute("UPDATE reminders SET sent=1 WHERE id=?", (reminder_id,))
        self.conn.commit()

    def reminder_reschedule(self, reminder_id: int, new_trigger_at: int):
        """Pra recorrentes — re-agenda em vez de marcar enviado."""
        c = self.conn.cursor()
        c.execute(
            "UPDATE reminders SET trigger_at=? WHERE id=?",
            (new_trigger_at, reminder_id)
        )
        self.conn.commit()

    def reminder_delete(self, user_jid: str, reminder_id: int) -> bool:
        c = self.conn.cursor()
        c.execute(
            "DELETE FROM reminders WHERE id=? AND user_jid=?",
            (reminder_id, user_jid)
        )
        self.conn.commit()
        return c.rowcount > 0

    # ============ Counters (gamificação) ============

    def counter_inc(self, user_jid: str, name: str, by: int = 1) -> int:
        c = self.conn.cursor()
        now = int(time.time())
        c.execute(
            "INSERT INTO counters (user_jid, name, value, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_jid, name) DO UPDATE SET "
            "value = value + ?, updated_at = ?",
            (user_jid, name, by, now, by, now)
        )
        self.conn.commit()
        c.execute(
            "SELECT value FROM counters WHERE user_jid=? AND name=?",
            (user_jid, name)
        )
        row = c.fetchone()
        return row["value"] if row else 0

    def counter_get(self, user_jid: str, name: str) -> int:
        c = self.conn.cursor()
        c.execute(
            "SELECT value FROM counters WHERE user_jid=? AND name=?",
            (user_jid, name)
        )
        row = c.fetchone()
        return row["value"] if row else 0

    # ============ Key-Value ============

    def kv_set(self, user_jid: str, key: str, value: Any):
        c = self.conn.cursor()
        v = json.dumps(value) if not isinstance(value, str) else value
        c.execute(
            "INSERT INTO kv (user_jid, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(user_jid, key) DO UPDATE SET value = ?",
            (user_jid, key, v, v)
        )
        self.conn.commit()

    def kv_get(self, user_jid: str, key: str, default: Any = None) -> Any:
        c = self.conn.cursor()
        c.execute(
            "SELECT value FROM kv WHERE user_jid=? AND key=?",
            (user_jid, key)
        )
        row = c.fetchone()
        if row is None:
            return default
        v = row["value"]
        try:
            return json.loads(v)
        except Exception:
            return v

    def close(self):
        self.conn.close()
