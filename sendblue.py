"""Thin Sendblue client: lets Penny text the owner over iMessage."""
import os

import httpx

BASE = os.getenv("SENDBLUE_API_BASE", "https://api.sendblue.co")


def _headers():
    return {
        "sb-api-key-id": os.getenv("SENDBLUE_API_KEY_ID", ""),
        "sb-api-secret-key": os.getenv("SENDBLUE_API_SECRET_KEY", ""),
        "Content-Type": "application/json",
    }


def enabled():
    return bool(os.getenv("SENDBLUE_API_KEY_ID") and os.getenv("SENDBLUE_API_SECRET_KEY")
                and os.getenv("OWNER_PHONE"))


def send(number, content):
    body = {"number": number, "content": content}
    if os.getenv("SENDBLUE_NUMBER"):
        body["from_number"] = os.getenv("SENDBLUE_NUMBER")
    try:
        r = httpx.post(f"{BASE}/api/send-message", json=body, headers=_headers(), timeout=20)
        if r.status_code >= 300:
            print("sendblue send failed:", r.status_code, r.text[:300])
    except httpx.HTTPError as e:
        print("sendblue send error:", e)


def text_owner(content):
    if enabled():
        send(os.environ["OWNER_PHONE"], content)
