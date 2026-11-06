"""Synthetic history so the demo opens with a lived-in business. All names and numbers are made up."""
import random
from datetime import datetime, timedelta

import db

STYLES = [("box braids", 180), ("knotless braids", 220), ("cornrows", 80), ("twists", 140),
          ("kids' braids", 70), ("touch-up", 50), ("feed-in braids", 120), ("loc retwist", 90)]
CLIENTS = ["Aisha", "Brianna", "Camila", "Destiny", "Elena", "Fatima", "Gabby",
           "Imani", "Keisha", "Lena", "Monique", "Nia"]
METHODS = ["Cash App", "Zelle", "Venmo", "cash"]
SUPPLIES = [("braiding hair, 10 packs", 45), ("edge control + mousse", 22), ("beads + cuffs", 14),
            ("rubber bands, combs", 11)]


def _ts(d, hour, minute=0):
    return d.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat(timespec="seconds")


def history(weeks=6, rng_seed=7):
    """Weeks of confirmed bookings, payments and supply runs (no chat text, just the books)."""
    rng = random.Random(rng_seed)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(weeks=weeks)
    regulars = rng.sample(CLIENTS, 5)  # these come back, like real clients do
    for day in range((today - start).days):  # stops before today; today is the live demo
        d = start + timedelta(days=day)
        if d.weekday() == 0:  # Mondays off
            continue
        busy = d.weekday() >= 4  # Fri-Sun are the busy days
        for _ in range(rng.choice([1, 2, 2, 3]) if busy else rng.choice([0, 0, 1, 1])):
            client = rng.choice(regulars) if rng.random() < .55 else rng.choice(CLIENTS)
            style, price = rng.choice(STYLES)
            method = rng.choice(METHODS)
            ts = _ts(d, rng.randint(9, 17), rng.randint(0, 59))
            db.add_event("seed", client, "order", price, style, d.strftime("%Y-%m-%d"), 1.0, None,
                         status="confirmed", ts=ts)
            deposit = 50 if price >= 120 else 0
            if deposit:
                db.add_event("seed", client, "payment", deposit, f"deposit, {method}", None, 1.0, None,
                             status="confirmed", ts=_ts(d - timedelta(days=rng.randint(2, 5)), 20))
            # a couple of older clients still owe a little; recent weeks are mostly paid
            rest = price - deposit
            if d < today - timedelta(days=10) and rng.random() < .1:
                rest = rest / 2
            db.add_event("seed", client, "payment", rest, f"{style}, {method}", None, 1.0, None,
                         status="confirmed", ts=ts)
        if d.weekday() == 3:  # Thursday supply run
            item, cost = rng.choice(SUPPLIES)
            db.add_event("seed", "Beauty supply", "expense", cost + rng.randint(0, 15), item, None,
                         1.0, None, status="confirmed", ts=_ts(d, 11))

    # Jess is a repeat client: three weeks ago she got box braids with beads (for "like last time")
    d = today - timedelta(weeks=3, days=1)
    db.add_event("seed", "Jess", "order", 195, "box braids + beads", d.strftime("%Y-%m-%d"), 1.0, None,
                 status="confirmed", ts=_ts(d, 10))
    db.add_event("seed", "Jess", "payment", 195, "box braids + beads, Cash App", None, 1.0, None,
                 status="confirmed", ts=_ts(d, 14))


def _chat(chat_id, lines, day, start_hour):
    ids = []
    for i, (sender, text) in enumerate(lines):
        ids.append(db.add_message(chat_id, sender, text, ts=_ts(day, start_hour, min(59, i * 4))))
    return ids


def _logged(chat_id, client, type_, amount, desc, due, msg_id, day, hour, note=None):
    eid = db.add_event(chat_id, client, type_, amount, desc, due, .95, msg_id,
                       status="confirmed", ts=_ts(day, hour))
    db.add_feed("penny", f"Log {desc}?", eid)
    if note:
        db.add_feed("penny", note)


def demo_chats():
    """Earlier, already-finished conversations in the demo's client chats."""
    today = datetime.now()
    two_days = today - timedelta(days=2)
    yesterday = today - timedelta(days=1)

    # Dana: twists last week, paid the deposit, still owes $90 (sets up the live script)
    last_fri = today - timedelta(days=(today.weekday() - 4) % 7 or 7)
    ids = _chat("dana", [
        ("Dana", "can I get medium twists friday?"),
        ("Maya", "yes! medium twists are $140, $50 deposit to hold the spot"),
        ("Dana", "booked! cash app'd the 50"),
    ], last_fri - timedelta(days=3), 12)
    _logged("dana", "Dana", "order", 140, "medium twists", last_fri.strftime("%Y-%m-%d"),
            ids[2], last_fri - timedelta(days=3), 12)
    _logged("dana", "Dana", "payment", 50, "deposit, Cash App", None,
            ids[2], last_fri - timedelta(days=3), 12)


    # Priya: booked, paid half by Zelle, then the rest. Fully settled.
    ids = _chat("priya", [
        ("Priya", "hey can you do cornrows for my daughter tuesday after school?"),
        ("Maya", "of course! kids cornrows are $80"),
        ("Priya", "perfect, book her 🙌 sending half now"),
        ("Priya", "sent $40 on zelle"),
        ("Maya", "got it, see you tues!"),
    ], two_days, 16)
    _logged("priya", "Priya", "order", 80, "kids' cornrows", two_days.strftime("%Y-%m-%d"),
            ids[2], two_days, 16)
    _logged("priya", "Priya", "payment", 40, "deposit, Zelle", None,
            ids[3], two_days, 16)
    ids += _chat("priya", [
        ("Priya", "she LOVES them thank you!! sending the rest now"),
        ("Priya", "zelle'd you 40"),
    ], yesterday, 18)
    _logged("priya", "Priya", "payment", 40, "rest for cornrows, Zelle", None,
            ids[-1], yesterday, 18, "Priya is all paid up 🎉")

def baseline():
    history()
    demo_chats()


if __name__ == "__main__":
    db.reset()
    baseline()
    print("seeded")
