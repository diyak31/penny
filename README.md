# 🪙 Penny

**Add her to your chats. Your texts become your receipts.**

Millions of women run informal businesses (hair braiding, home baking, cleaning, childcare) entirely
over text and Venmo/Zelle/Cash App. They keep no books, so their income is invisible to lenders and
they stay credit-invisible.

Penny joins the group chat between a business owner and her client. She stays quiet, reads the
conversation with Claude, and picks out real money events:

- **Negotiation vs. a deal:** "can you do 180?" is ignored. "ok deal" logs a booking.
- **Context:** "add beads like last time", "half now, half Thursday", "the rest Saturday".
- **Payment screenshots:** reads the amount from an image.
- **Not-yet payments:** "I'll venmo you after payday" is *not* logged.

Everything goes to the owner in a **private** chat for one-tap confirmation. She can ask
*"who owes me money?"* at any time. After a few weeks, Penny produces a **lender-ready cash-flow
report** built from transaction evidence instead of self-reported numbers.

**Today:** iMessage (bots join group chats via an iMessage API provider such as Linq or Sendblue).
**Next:** WhatsApp, where 2B+ people and most of the world's informal businesses run. The engine is
platform-agnostic.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # add your ANTHROPIC_API_KEY
.venv/bin/uvicorn server:app --reload --port 8000
```

Open http://localhost:8000 for the landing page, or http://localhost:8000/demo for the demo. Use **▶ next scripted line** to play both sides of a conversation, or type
your own. The demo opens with 6 weeks of synthetic history; **Reset demo** restores it. Open the **lender-ready report** from the books panel.

## How it works

| File | Role |
|---|---|
| `engine.py` | Claude (`claude-opus-5-5`, structured outputs) extracts events from the newest message plus chat history, answers the owner's questions, and writes the report summary |
| `db.py` | SQLite ledger. **Claude extracts; code does all the arithmetic**, so balances can't be hallucinated |
| `server.py` | FastAPI: chat API, confirmations, owner Q&A, lender report, and an `/webhook/imessage` endpoint for a live iMessage provider |
| `seed.py` | Synthetic history for the report |
| `static/` | iMessage-style demo UI and report page |

All data is synthetic. No real personal or financial information is used.
