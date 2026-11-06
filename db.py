"""SQLite ledger storage. Claude extracts events; all money math happens here."""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "ledger.db"


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY, client_name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL, sender TEXT NOT NULL, text TEXT,
                has_image INTEGER DEFAULT 0, ts TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT, client TEXT, type TEXT NOT NULL,
                amount REAL NOT NULL, description TEXT, due TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                confidence REAL, source_msg_id INTEGER, ts TEXT NOT NULL
            );
            -- Penny's private thread with the owner
            CREATE TABLE IF NOT EXISTS owner_feed (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL, text TEXT NOT NULL,
                event_id INTEGER, ts TEXT NOT NULL
            );
            """
        )


def now():
    return datetime.now().isoformat(timespec="seconds")


def reset():
    DB_PATH.unlink(missing_ok=True)
    init()


def ensure_chat(chat_id, client_name):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO chats VALUES (?, ?)", (chat_id, client_name))


def add_message(chat_id, sender, text, has_image=False, ts=None):
    with conn() as c:
        cur = c.execute(
            "INSERT INTO messages (chat_id, sender, text, has_image, ts) VALUES (?,?,?,?,?)",
            (chat_id, sender, text, int(has_image), ts or now()),
        )
        return cur.lastrowid


def recent_messages(chat_id, limit=30):
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def chats():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM chats").fetchall()]


def add_event(chat_id, client, type_, amount, description, due, confidence, source_msg_id,
              status="pending", ts=None):
    with conn() as c:
        cur = c.execute(
            """INSERT INTO events (chat_id, client, type, amount, description, due, status,
               confidence, source_msg_id, ts) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (chat_id, client, type_, amount, description, due, status, confidence,
             source_msg_id, ts or now()),
        )
        return cur.lastrowid


def get_event(event_id):
    with conn() as c:
        r = c.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    return dict(r) if r else None


def set_event_status(event_id, status, amount=None):
    with conn() as c:
        if amount is not None:
            c.execute("UPDATE events SET status=?, amount=? WHERE id=?", (status, amount, event_id))
        else:
            c.execute("UPDATE events SET status=? WHERE id=?", (status, event_id))


def events(status="confirmed"):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM events WHERE status=? ORDER BY ts", (status,)).fetchall()]


def add_feed(sender, text, event_id=None):
    with conn() as c:
        c.execute("INSERT INTO owner_feed (sender, text, event_id, ts) VALUES (?,?,?,?)",
                  (sender, text, event_id, now()))


def feed():
    with conn() as c:
        rows = c.execute(
            """SELECT f.*, e.status AS event_status, e.type AS event_type, e.amount AS event_amount,
                      e.client AS event_client, e.description AS event_desc, e.due AS event_due
               FROM owner_feed f
               LEFT JOIN events e ON e.id = f.event_id ORDER BY f.id"""
        ).fetchall()
    return [dict(r) for r in rows]


def balances():
    """Per-client: total ordered, total paid, outstanding. Confirmed events only."""
    out = {}
    for e in events():
        b = out.setdefault(e["client"] or "Unknown",
                           {"client": e["client"], "ordered": 0.0, "paid": 0.0, "next_due": None})
        if e["type"] == "order":
            b["ordered"] += e["amount"]
            if e["due"]:
                b["next_due"] = e["due"]
        elif e["type"] == "payment":
            b["paid"] += e["amount"]
        elif e["type"] == "refund":
            b["paid"] -= e["amount"]
    for b in out.values():
        b["owed"] = round(b["ordered"] - b["paid"], 2)
    return sorted(out.values(), key=lambda b: -b["owed"])
