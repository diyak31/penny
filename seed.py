"""Synthetic history so the lender report has a month+ of data. All names are made up."""
import random
from datetime import datetime, timedelta

import db

STYLES = [("box braids", 180), ("knotless braids", 220), ("cornrows", 80),
          ("twists", 140), ("kids' braids", 70), ("touch-up", 50)]
CLIENTS = ["Aisha", "Brianna", "Camila", "Destiny", "Elena", "Fatima", "Gabby",
           "Imani", "Keisha", "Lena", "Monique", "Nia"]
SUPPLIES = [("braiding hair, 10 packs", 45), ("edge control + gel", 18), ("beads", 12)]


def seed(weeks=6, rng_seed=7):
    rng = random.Random(rng_seed)
    start = datetime.now() - timedelta(weeks=weeks)
    for day in range(weeks * 7):
        d = start + timedelta(days=day)
        if d.weekday() == 0:  # Mondays off
            continue
        for _ in range(rng.choice([0, 1, 1, 2, 2, 3]) if d.weekday() >= 4 else rng.choice([0, 0, 1, 1])):
            client = rng.choice(CLIENTS)
            style, price = rng.choice(STYLES)
            ts = d.replace(hour=rng.randint(9, 18), minute=rng.randint(0, 59)).isoformat(timespec="seconds")
            db.add_event("seed", client, "order", price, style, d.strftime("%Y-%m-%d"), 1.0, None,
                         status="confirmed", ts=ts)
            paid = price if rng.random() > 0.12 else price / 2  # a few still owe
            db.add_event("seed", client, "payment", paid, style, None, 1.0, None,
                         status="confirmed", ts=ts)
        if d.weekday() == 3:
            item, cost = rng.choice(SUPPLIES)
            db.add_event("seed", "Beauty supply", "expense", cost + rng.randint(0, 20), item, None,
                         1.0, None, status="confirmed",
                         ts=d.replace(hour=11).isoformat(timespec="seconds"))


if __name__ == "__main__":
    db.init()
    seed()
    print("seeded")
