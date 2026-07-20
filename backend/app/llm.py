"""
Shared LLM helper — uses Groq's free API (OpenAI-compatible, no billing
required, no credit card) instead of Gemini. Gemini was dropped because
every Google Cloud project tested returned `429 ... limit: 0` for the
free tier unless billing was enabled, which the user explicitly does not
want to set up.

Get a free key (instant signup, no card) at https://console.groq.com/keys
"""

import json
import logging

import httpx

from app import config

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def chat(system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not configured")

    payload = {
        "model": config.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    resp = httpx.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def clean_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def chat_json(system_prompt: str, user_prompt: str) -> dict:
    raw = chat(system_prompt, user_prompt, json_mode=True)
    return json.loads(clean_json(raw))
