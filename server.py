"""Penny: a silent bookkeeper for the chats women already run their businesses in."""
import os
import re
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import db  # noqa: E402
import engine  # noqa: E402
import seed  # noqa: E402
import sendblue  # noqa: E402

app = FastAPI(title="Penny")
STATIC = Path(__file__).parent / "static"
db.init()

DEMO_CHATS = {"jess": "Jess", "priya": "Priya", "dana": "Dana"}
for cid, name in DEMO_CHATS.items():
    db.ensure_chat(cid, name)
if not db.events() and not db.events("pending"):  # fresh database: open with a lived-in business
    seed.baseline()

VERB = {"order": "booking", "payment": "payment", "expense": "expense", "refund": "refund"}


def money(x):
    return f"${x:,.0f}" if float(x).is_integer() else f"${x:,.2f}"


def notify(text, event_id=None):
    """Penny -> owner: shows in the web UI and texts the owner's iPhone via Sendblue."""
    db.add_feed("ledger", text, event_id)
    sendblue.text_owner(text + ("\n\nReply YES to log, NO to skip, or a corrected amount." if event_id else ""))


_lock = threading.Lock()


def process_message(chat_id, client_name, msg_id, image_b64=None, image_type="image/png", image_url=None):
    with _lock:  # one message at a time, in order
        _process(chat_id, client_name, msg_id, image_b64, image_type, image_url)


def _process(chat_id, client_name, msg_id, image_b64, image_type, image_url):
    # history up to and including this message, even if newer ones have arrived since
    history = [m for m in db.recent_messages(chat_id, 60) if m["id"] <= msg_id][-30:]
    try:
        result = engine.extract(history, client_name, image_b64, image_type, image_url)
    except Exception as e:  # keep the demo alive if one call fails
        print("extract failed:", e)
        return
    source_id = history[-1]["id"]
    for ev in result.events:
        if ev.confidence < 0.5:
            continue
        who = ev.client or client_name
        eid = db.add_event(chat_id, who, ev.type, ev.amount, ev.description, ev.due,
                           ev.confidence, source_id)
        prep = "from" if ev.type == "payment" else "for" if ev.type == "order" else "-"
        notify(f"Log {money(ev.amount)} {VERB[ev.type]} {prep} {who}: "
               f"{ev.description}{f' (due {ev.due})' if ev.due else ''}?", eid)
    if result.question_for_owner:
        notify(result.question_for_owner)


class ChatMessage(BaseModel):
    sender: str
    text: str = ""
    image_b64: str | None = None
    image_type: str = "image/png"


class EditBody(BaseModel):
    amount: float | None = None


class AskBody(BaseModel):
    text: str


@app.get("/")
def landing():
    return FileResponse(STATIC / "landing.html")


@app.get("/coin.svg")
def coin():
    return FileResponse(STATIC / "coin.svg", media_type="image/svg+xml")


@app.get("/demo")
def demo():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def state():
    return {
        "chats": {c["id"]: {"client": c["client_name"], "messages": db.recent_messages(c["id"], 200)}
                  for c in db.chats()},
        "feed": db.feed(),
        "balances": db.balances(),
        "totals": totals(),
    }


@app.post("/api/chats/{chat_id}/messages")
def post_message(chat_id: str, body: ChatMessage, bg: BackgroundTasks):
    client_name = DEMO_CHATS.get(chat_id, chat_id.title())
    db.ensure_chat(chat_id, client_name)
    msg_id = db.add_message(chat_id, body.sender, body.text, has_image=bool(body.image_b64))
    bg.add_task(process_message, chat_id, client_name, msg_id, body.image_b64, body.image_type)
    return {"ok": True}


@app.post("/api/events/{event_id}/confirm")
def confirm(event_id: int, body: EditBody | None = None):
    db.set_event_status(event_id, "confirmed", body.amount if body else None)
    ev = db.get_event(event_id)
    bal = next((b for b in db.balances() if b["client"] == ev["client"]), None)
    msg = f"✓ Logged {money(ev['amount'])} {VERB[ev['type']]}."
    if bal and ev["type"] in ("order", "payment"):
        msg += (f" {ev['client']} owes {money(bal['owed'])}." if bal["owed"] > 0
                else f" {ev['client']} is all paid up.")
    notify(msg)
    return {"ok": True}


@app.post("/api/events/{event_id}/reject")
def reject(event_id: int):
    db.set_event_status(event_id, "rejected")
    notify("Got it, skipped.")
    return {"ok": True}


@app.post("/api/ask")
def ask(body: AskBody):
    db.add_feed("owner", body.text)
    try:
        reply = engine.answer(body.text, db.balances(), db.events())
    except Exception as e:
        print("answer failed:", e)
        reply = "Sorry, I couldn't check that right now."
    notify(reply)
    return {"reply": reply}


@app.post("/api/reset")
def reset():
    db.reset()
    for cid, name in DEMO_CHATS.items():
        db.ensure_chat(cid, name)
    seed.baseline()
    return {"ok": True}


def _digits(n):
    return re.sub(r"\D", "", n or "")[-10:]


def _contacts():
    """CONTACTS=+15551234567:Jess,+15557654321:Priya  (optional, for nicer names)"""
    out = {}
    for pair in filter(None, os.getenv("CONTACTS", "").split(",")):
        num, _, name = pair.partition(":")
        out[_digits(num)] = name.strip()
    return out


def _name(number):
    if _digits(number) == _digits(os.getenv("OWNER_PHONE")):
        return engine.OWNER
    return _contacts().get(_digits(number)) or f"Client {_digits(number)[-4:]}"


def handle_owner_dm(text):
    """Owner texting Penny directly: confirm/skip/correct the latest pending item, or ask a question."""
    pending = db.events("pending")
    t = text.strip().lower().rstrip("!.")
    amount = re.fullmatch(r"\$?(\d+(?:\.\d+)?)", t)
    if pending and (t in ("yes", "y", "ok", "yep", "log it", "👍", "no", "n", "skip", "nope") or amount):
        db.add_feed("owner", text)
    if pending and t in ("yes", "y", "ok", "yep", "log it", "👍"):
        confirm(pending[-1]["id"])
    elif pending and t in ("no", "n", "skip", "nope"):
        reject(pending[-1]["id"])
    elif pending and amount:
        confirm(pending[-1]["id"], EditBody(amount=float(amount.group(1))))
    else:
        ask(AskBody(text=text))


@app.post("/webhook/imessage")
async def imessage_webhook(request: Request, bg: BackgroundTasks):
    """Sendblue 'receive' webhook. Set this URL in the Sendblue dashboard."""
    p = await request.json()
    if p.get("is_outbound"):
        return {"ok": True}
    sender_num = p.get("from_number") or p.get("number") or ""
    sender = _name(sender_num)
    text = p.get("content") or ""
    image_url = p.get("media_url") or None
    group_id = p.get("group_id") or ""

    if not group_id and sender == engine.OWNER:  # private chat: owner <-> Penny
        bg.add_task(handle_owner_dm, text)
        return {"ok": True}

    others = [n for n in p.get("participants", [])
              if _digits(n) not in (_digits(os.getenv("OWNER_PHONE")), _digits(p.get("sendblue_number")))]
    client_name = _name(others[0]) if others else sender
    chat_id = group_id or _digits(sender_num)
    db.ensure_chat(chat_id, client_name)
    msg_id = db.add_message(chat_id, sender, text, has_image=bool(image_url))
    bg.add_task(process_message, chat_id, client_name, msg_id, None, "image/png", image_url)
    return {"ok": True}


# ---------- lender report ----------

def totals():
    evs = db.events()
    since = (datetime.now() - timedelta(days=7)).isoformat()
    week = [e for e in evs if e["ts"] >= since]
    return {
        "week_income": sum(e["amount"] for e in week if e["type"] == "payment"),
        "week_expenses": sum(e["amount"] for e in week if e["type"] == "expense"),
        "owed_to_you": sum(b["owed"] for b in db.balances() if b["owed"] > 0),
    }


def report_stats():
    evs = db.events()
    weekly = defaultdict(lambda: {"income": 0.0, "expenses": 0.0})
    for e in evs:
        d = datetime.fromisoformat(e["ts"])
        wk = (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")
        if e["type"] == "payment":
            weekly[wk]["income"] += e["amount"]
        elif e["type"] in ("expense", "refund"):
            weekly[wk]["expenses"] += e["amount"]
    weeks = sorted(weekly)
    income = sum(w["income"] for w in weekly.values())
    expenses = sum(w["expenses"] for w in weekly.values())
    clients = defaultdict(int)
    for e in evs:
        if e["type"] == "order":
            clients[e["client"]] += 1
    return {
        "business": f"{engine.OWNER}'s Braids",
        "period": f"{weeks[0]} to {datetime.now():%Y-%m-%d}" if weeks else "n/a",
        "weeks": [{"week_of": w, **weekly[w], "net": weekly[w]["income"] - weekly[w]["expenses"]}
                  for w in weeks],
        "total_income": income,
        "total_expenses": expenses,
        "net_income": income - expenses,
        "avg_weekly_income": income / len(weeks) if weeks else 0,
        "weeks_with_income": sum(1 for w in weekly.values() if w["income"] > 0),
        "total_weeks": len(weeks),
        "unique_clients": len(clients),
        "repeat_clients": sum(1 for n in clients.values() if n > 1),
        "transactions_logged": len(evs),
        "outstanding_receivables": sum(b["owed"] for b in db.balances() if b["owed"] > 0),
    }


@app.get("/report", response_class=HTMLResponse)
def report():
    s = report_stats()
    try:
        summary = engine.report_summary(s)
    except Exception as e:
        print("summary failed:", e)
        summary = ""
    top = max([w["income"] for w in s["weeks"]] or [1]) or 1
    bars = "".join(
        f"<div class='bar'><span>{w['week_of'][5:]}</span><div style='width:{w['income'] / top * 100:.0f}%'></div>"
        f"<b>{money(w['income'])}</b></div>" for w in s["weeks"])
    html = (STATIC / "report.html").read_text()
    for k, v in {
        "{{business}}": s["business"], "{{period}}": s["period"], "{{summary}}": summary,
        "{{income}}": money(s["total_income"]), "{{expenses}}": money(s["total_expenses"]),
        "{{net}}": money(s["net_income"]), "{{avg}}": money(s["avg_weekly_income"]),
        "{{consistency}}": f"{s['weeks_with_income']}/{s['total_weeks']}",
        "{{clients}}": str(s["unique_clients"]), "{{repeat}}": str(s["repeat_clients"]),
        "{{txns}}": str(s["transactions_logged"]),
        "{{receivables}}": money(s["outstanding_receivables"]), "{{bars}}": bars,
        "{{generated}}": f"{datetime.now():%B %d, %Y}",
    }.items():
        html = html.replace(k, v)
    return html
