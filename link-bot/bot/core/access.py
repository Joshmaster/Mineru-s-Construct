"""Controle de acesso WhatsApp: admin, allow-list e pedidos pendentes."""

from __future__ import annotations

import json
import random
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "config.json"
PENDING_PATH = ROOT / ".linkbot" / "access_requests.json"


def digits(value: Any) -> str:
    return "".join(c for c in str(value or "") if c.isdigit())


def jid_user(jid: Any) -> str:
    return digits(getattr(jid, "User", "") or jid)


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def storage_path(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    raw = Path(str(cfg.get("STORAGE_PATH") or ".linkbot/data.db"))
    return raw if raw.is_absolute() else ROOT / raw


def _connect_contacts(cfg: dict | None = None) -> sqlite3.Connection:
    path = storage_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts (
            identity_key TEXT PRIMARY KEY,
            contact_uid TEXT,
            name TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            source TEXT,
            updated_at INTEGER NOT NULL
        )
        """
    )
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(contacts)").fetchall()}
    if "contact_uid" not in cols:
        conn.execute("ALTER TABLE contacts ADD COLUMN contact_uid TEXT")
    conn.execute(
        "UPDATE contacts SET contact_uid=identity_key "
        "WHERE contact_uid IS NULL OR contact_uid=''"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_uid ON contacts(contact_uid)")
    conn.commit()
    return conn


def migrate_config_contacts(cfg: dict | None = None):
    cfg = cfg or load_config()
    names = cfg.get("CONTACT_NAMES", {}) or {}
    if not names:
        return
    now = int(time.time())
    raw_admin_keys: set[str] = set()
    for item in [cfg.get("OWNER", ""), *(cfg.get("OWNER_IDS", []) or [])]:
        raw_admin_keys.update(identity_keys(item))
    with _connect_contacts(cfg) as conn:
        for key, name in names.items():
            key = identity_keys(key)[0] if identity_keys(key) else ""
            name = str(name or "").strip()[:80]
            if not key or not name:
                continue
            role = "admin" if key in raw_admin_keys else "user"
            conn.execute(
                """
                INSERT INTO contacts (identity_key, contact_uid, name, role, source, updated_at)
                VALUES (?, ?, ?, ?, 'config_migration', ?)
                ON CONFLICT(identity_key) DO NOTHING
                """,
                (key, key, name, role, now),
            )
        conn.commit()
    names_by_key = {
        (identity_keys(key)[0] if identity_keys(key) else ""): str(name or "").strip()[:80]
        for key, name in names.items()
    }
    for name in sorted(set(names_by_key.values())):
        same_contact = [key for key, item_name in names_by_key.items() if key and item_name == name]
        if len(same_contact) > 1:
            merge_contact_ids(*same_contact)


def identity_keys(*values: Any) -> list[str]:
    keys: list[str] = []
    for value in values:
        user = getattr(value, "User", None)
        raw = str(user if user is not None else (value or "")).strip()
        dig = digits(raw)
        for key in (dig, raw):
            if key and key not in keys:
                keys.append(key)
    return keys


def _expanded_keys(keys: list[str] | set[str], cfg: dict | None = None) -> set[str]:
    keys = set(keys)
    if not keys:
        return set()
    with _connect_contacts(cfg) as conn:
        placeholders = ",".join("?" for _ in keys)
        rows = conn.execute(
            f"SELECT contact_uid FROM contacts WHERE identity_key IN ({placeholders})",
            list(keys),
        ).fetchall()
        uids = {str(row["contact_uid"]) for row in rows if row["contact_uid"]}
        if not uids:
            return keys
        placeholders = ",".join("?" for _ in uids)
        alias_rows = conn.execute(
            f"SELECT identity_key FROM contacts WHERE contact_uid IN ({placeholders})",
            list(uids),
        ).fetchall()
    keys.update(str(row["identity_key"]) for row in alias_rows if row["identity_key"])
    return keys


def merge_contact_ids(*ids: Any) -> str | None:
    """Mescla número físico, ID interno e JID completo como aliases do mesmo contato."""
    keys = identity_keys(*ids)
    if not keys:
        return None
    now = int(time.time())
    with _connect_contacts() as conn:
        placeholders = ",".join("?" for _ in keys)
        rows = conn.execute(
            f"SELECT * FROM contacts WHERE identity_key IN ({placeholders})",
            keys,
        ).fetchall()
        existing_uids = [str(row["contact_uid"] or row["identity_key"]) for row in rows]
        contact_uid = existing_uids[0] if existing_uids else keys[0]
        name = next((str(row["name"]).strip() for row in rows if str(row["name"] or "").strip()), "")
        role = "admin" if any(str(row["role"]) == "admin" for row in rows) else "user"
        source = next((str(row["source"] or "") for row in rows if row["source"]), "merge")

        if existing_uids:
            placeholders = ",".join("?" for _ in existing_uids)
            conn.execute(
                f"UPDATE contacts SET contact_uid=?, role=?, updated_at=? "
                f"WHERE contact_uid IN ({placeholders})",
                [contact_uid, role, now, *existing_uids],
            )

        if name:
            for key in keys:
                conn.execute(
                    """
                    INSERT INTO contacts (identity_key, contact_uid, name, role, source, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(identity_key) DO UPDATE SET
                        contact_uid=excluded.contact_uid,
                        role=excluded.role,
                        updated_at=excluded.updated_at
                    """,
                    (key, contact_uid, name, role, source, now),
                )
        conn.commit()
    return contact_uid


def contact_record(*ids: Any) -> dict | None:
    keys = identity_keys(*ids)
    if not keys:
        return None
    with _connect_contacts() as conn:
        placeholders = ",".join("?" for _ in keys)
        row = conn.execute(
            f"SELECT * FROM contacts WHERE identity_key IN ({placeholders}) LIMIT 1",
            keys,
        ).fetchone()
        if not row:
            return None
        contact_uid = row["contact_uid"] or row["identity_key"]
        aliases = conn.execute(
            "SELECT identity_key FROM contacts WHERE contact_uid=? ORDER BY identity_key",
            (contact_uid,),
        ).fetchall()
    record = dict(row)
    record["aliases"] = [str(item["identity_key"]) for item in aliases]
    return record


def allow_keys(cfg: dict | None = None) -> set[str]:
    cfg = cfg or load_config()
    keys: set[str] = set()
    for item in cfg.get("ALLOW_FROM", []):
        keys.update(identity_keys(item))
    return _expanded_keys(keys, cfg)


def admin_keys(cfg: dict | None = None) -> set[str]:
    cfg = cfg or load_config()
    admins = []
    admins.extend(cfg.get("OWNER_IDS", []) or [])
    owner = cfg.get("OWNER", "")
    if owner:
        admins.append(owner)
    keys: set[str] = set()
    for item in admins:
        keys.update(identity_keys(item))
    return _expanded_keys(keys, cfg)


def is_allowed(*ids: Any, cfg: dict | None = None) -> bool:
    keys = _expanded_keys(identity_keys(*ids), cfg)
    return bool(keys & allow_keys(cfg))


def is_admin(*ids: Any, cfg: dict | None = None) -> bool:
    keys = _expanded_keys(identity_keys(*ids), cfg)
    return bool(keys & admin_keys(cfg))


def display_name(*ids: Any, pushname: str = "") -> str:
    record = contact_record(*ids)
    if record and str(record.get("name") or "").strip():
        return str(record["name"]).strip()
    cfg = load_config()
    names = cfg.get("CONTACT_NAMES", {}) or {}
    for key in identity_keys(*ids):
        if key in names and str(names[key]).strip():
            return str(names[key]).strip()
    if pushname and str(pushname).strip():
        return str(pushname).strip()
    for key in identity_keys(*ids):
        if key:
            return f"usuario {key}"
    return "usuario"


def has_contact_name(*ids: Any) -> bool:
    record = contact_record(*ids)
    if record and str(record.get("name") or "").strip():
        return True
    cfg = load_config()
    names = cfg.get("CONTACT_NAMES", {}) or {}
    return any(key in names and str(names[key]).strip() for key in identity_keys(*ids))


def add_allowed(*ids: Any) -> list[str]:
    cfg = load_config()
    allow = [digits(x) or str(x) for x in cfg.get("ALLOW_FROM", [])]
    added: list[str] = []
    for key in identity_keys(*ids):
        if key and key not in allow:
            allow.append(key)
            added.append(key)
    cfg["ALLOW_FROM"] = allow
    save_config(cfg)
    return added


def remove_allowed(target: Any) -> bool:
    cfg = load_config()
    keys = set(identity_keys(target))
    allow = [digits(x) or str(x) for x in cfg.get("ALLOW_FROM", [])]
    new_allow = [x for x in allow if x not in keys]
    changed = new_allow != allow
    if changed:
        cfg["ALLOW_FROM"] = new_allow
        save_config(cfg)
    return changed


def set_contact_name(name: str, *ids: Any):
    name = str(name or "").strip()[:80]
    if not name:
        return
    cfg = load_config()
    now = int(time.time())
    keys = identity_keys(*ids)
    merge_contact_ids(*keys)
    with _connect_contacts(cfg) as conn:
        placeholders = ",".join("?" for _ in keys)
        rows = conn.execute(
            f"SELECT contact_uid FROM contacts WHERE identity_key IN ({placeholders})",
            keys,
        ).fetchall() if keys else []
        contact_uid = str(rows[0]["contact_uid"]) if rows and rows[0]["contact_uid"] else (keys[0] if keys else "")
        for key in identity_keys(*ids):
            if not key:
                continue
            role = "admin" if is_admin(key, cfg=cfg) else "user"
            conn.execute(
                """
                INSERT INTO contacts (identity_key, contact_uid, name, role, source, updated_at)
                VALUES (?, ?, ?, ?, 'whatsapp', ?)
                ON CONFLICT(identity_key) DO UPDATE SET
                    contact_uid=excluded.contact_uid,
                    name=excluded.name,
                    role=excluded.role,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (key, contact_uid, name, role, now),
            )
        if contact_uid:
            conn.execute(
                "UPDATE contacts SET name=?, updated_at=? WHERE contact_uid=?",
                (name, now, contact_uid),
            )
        conn.commit()

    # Mantém compatibilidade com trechos antigos/config user2al, mas a fonte principal é o SQLite.
    names = cfg.setdefault("CONTACT_NAMES", {})
    for key in identity_keys(*ids):
        if key:
            names[key] = name
    save_config(cfg)


def load_pending() -> dict:
    if not PENDING_PATH.exists():
        return {}
    try:
        return json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_pending(data: dict):
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def pending_key(*ids: Any) -> str:
    for key in identity_keys(*ids):
        if key:
            return key
    return str(int(time.time()))


def new_code() -> str:
    return f"{random.randint(100000, 999999)}"


def normalize_code(value: Any) -> str:
    return str(value or "").strip()


def code_matches(text: str, code: Any) -> bool:
    expected = normalize_code(code)
    got = normalize_code(text)
    return bool(expected) and got.casefold() == expected.casefold()


def extract_admin_code(text: str) -> str:
    raw = str(text or "").strip()
    m = re.search(r"(?i)c[oó]digo\s*(?:e|é|:)?\s*([A-Za-z0-9_-]{3,32})", raw)
    if m:
        return m.group(1).strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{3,32}", raw):
        return raw
    return ""


def pending_waiting_admin_code() -> list[tuple[str, dict]]:
    data = load_pending()
    return [
        (key, item)
        for key, item in data.items()
        if item.get("step") == "admin_code" and not item.get("code")
    ]


def upsert_pending(key: str, **fields) -> dict:
    data = load_pending()
    item = data.get(key, {})
    item.update(fields)
    item["updated_at"] = int(time.time())
    item.setdefault("created_at", item["updated_at"])
    data[key] = item
    save_pending(data)
    return item


def find_pending_by_code_or_id(value: str) -> tuple[str, dict] | tuple[None, None]:
    data = load_pending()
    value_digits = digits(value)
    for key, item in data.items():
        if value_digits and value_digits == str(item.get("code", "")):
            return key, item
        if value in (key, item.get("sender_id"), item.get("phone"), item.get("chat_id")):
            return key, item
    return None, None


def pop_pending(key: str):
    data = load_pending()
    data.pop(key, None)
    save_pending(data)


def looks_like_code(text: str) -> bool:
    return bool(re.fullmatch(r"\s*\d{6}\s*", text or ""))
