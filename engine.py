"""Claude-powered extraction: turns chat messages into ledger events."""
import json
from datetime import date
from typing import List, Literal, Optional

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-5-5"
OWNER = "Maya"
BUSINESS = "a home hair-braiding business"

client = anthropic.Anthropic()


class LedgerEvent(BaseModel):
    type: Literal["order", "payment", "expense", "refund"] = Field(
        description="order = a deal is agreed (client now owes the price); "
        "payment = money actually sent/received; expense = owner spent money on supplies; "
        "refund = owner returned money to client")
    client: Optional[str] = Field(description="Client name (or supplier for expenses)")
    amount: float = Field(description="Amount in dollars, as a plain number")
    description: str = Field(description="Short description, e.g. 'box braids, Sat'")
    due: Optional[str] = Field(description="Due/appointment date as YYYY-MM-DD if known")
    confidence: float = Field(description="0-1 confidence this is a real, final transaction")


class Extraction(BaseModel):
    events: List[LedgerEvent] = Field(
        description="Transactions completed by the NEWEST message. Empty if none.")
    question_for_owner: Optional[str] = Field(
        description="One short clarifying question to ask the owner privately if the "
        "newest message is ambiguous about money (else null)")


SYSTEM = f"""You are Penny, a silent bookkeeper added to the text chats of {OWNER}, who runs {BUSINESS}.
You read the chat between {OWNER} and a client and decide whether the NEWEST message completes a money event.

Rules:
- Negotiation, questions and offers are NOT events ("can you do $150?", "how much?").
- An order is logged only when both sides have clearly agreed on a price ("ok deal", "yes book me", "works for me").
  Log the full agreed total as one order (e.g. 2 x $90 = 180).
- A payment is logged when money is sent or a payment screenshot is shared. Read amounts from screenshots.
  "I'll send it later" is NOT a payment.
- Resolve references using the earlier chat ("same as last time", "half now", "the rest").
- Only log events completed by the newest message; earlier messages were already processed.
- Today is {{today}}. Convert relative dates ("Saturday") to YYYY-MM-DD.
- question_for_owner should almost always be null. Never ask about negotiations still in progress or
  payments that are only announced ("sending now"); just wait for later messages. Only ask when money
  definitely changed hands but the amount or purpose is genuinely unclear."""


def _format_history(history):
    return "\n".join(
        f"[{m['id']}] {m['sender']}: {m['text'] or ''}{' [sent a photo]' if m['has_image'] else ''}"
        for m in history)


def extract(history, client_name, image_b64=None, image_type="image/png", image_url=None) -> Extraction:
    newest = history[-1]
    text = (f"Client in this chat: {client_name}\n\nChat so far:\n{_format_history(history[:-1]) or '(empty)'}"
            f"\n\nNEWEST message:\n{newest['sender']}: {newest['text'] or ''}")
    content = []
    if image_b64:
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": image_type, "data": image_b64}})
    elif image_url:
        content.append({"type": "image", "source": {"type": "url", "url": image_url}})
    if content:
        text += "\n(The newest message includes the attached image.)"
    content.append({"type": "text", "text": text})

    resp = client.messages.parse(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM.replace("{today}", date.today().strftime("%A %Y-%m-%d")),
        messages=[{"role": "user", "content": content}],
        output_format=Extraction,
        output_config={"effort": "low"},
    )
    return resp.parsed_output


def answer(question, balances, recent_events):
    """Owner asks Penny a question in their private chat."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        output_config={"effort": "low"},
        system=f"You are Penny, {OWNER}'s friendly bookkeeper, texting her. Answer in 1-4 short "
               "lines, plain text, no markdown headers. Use only the data given; the balances "
               "are already computed correctly, never recompute them differently.",
        messages=[{"role": "user", "content":
                   f"Balances by client:\n{json.dumps(balances, indent=1)}\n\n"
                   f"Recent confirmed transactions:\n{json.dumps(recent_events[-40:], indent=1)}\n\n"
                   f"{OWNER} asks: {question}"}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


def report_summary(stats):
    """Short lender-facing narrative for the income report."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        output_config={"effort": "low"},
        system="Write a factual 3-sentence summary for a microlender about this small "
               "business's cash flow. Use only the numbers given. No hype, no markdown.",
        messages=[{"role": "user", "content": json.dumps(stats)}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")
