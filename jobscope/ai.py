"""Free/optional AI backend (OpenAI-compatible).

One thin client talks to any OpenAI-compatible endpoint -- Groq (default),
Gemini's OpenAI shim, OpenRouter, local Ollama, or OpenAI. It is **off unless**
`ai.enabled` is true and a key is present (Ollama needs no key). Every caller is
written to work when this returns ``None`` -- that's the "80% logic / 20% AI"
contract. Responses are cached in the store (hash of model+system+user).
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from .config import api_key


def available(cfg: dict) -> bool:
    ai = cfg.get("ai", {})
    if not ai.get("enabled"):
        return False
    if ai.get("provider") == "ollama":
        return True  # local, no key required
    return bool(api_key(cfg))


def chat(cfg: dict, store, system: str, user: str, *, cache: bool = True,
         temperature: Optional[float] = None) -> Optional[str]:
    """Return the assistant text, or None if AI is unavailable/failed."""
    if not available(cfg):
        return None
    ai = cfg["ai"]
    model = ai.get("model", "")
    key = _cache_key(model, system, user)
    if cache and store is not None:
        hit = store.ai_cache_get(key)
        if hit is not None:
            return hit

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": ai.get("temperature", 0.3) if temperature is None else temperature,
        "max_tokens": ai.get("max_tokens", 1200),
    }
    text = _post(cfg, body)
    if text is not None and cache and store is not None:
        store.ai_cache_put(key, model, user, text)
    return text


def _post(cfg: dict, body: dict) -> Optional[str]:
    import requests
    ai = cfg["ai"]
    base = ai.get("base_url", "").rstrip("/")
    url = f"{base}/chat/completions"
    headers = {"Content-Type": "application/json"}
    k = api_key(cfg)
    if k:
        headers["Authorization"] = f"Bearer {k}"
    try:
        resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=60)
        if resp.status_code != 200:
            print(f"  [ai] {resp.status_code}: {resp.text[:160]}")
            return None
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001 - AI is always optional
        print(f"  [ai] error: {e}")
        return None


def _cache_key(model: str, system: str, user: str) -> str:
    h = hashlib.sha256()
    h.update(f"{model}\x00{system}\x00{user}".encode("utf-8"))
    return h.hexdigest()[:32]
