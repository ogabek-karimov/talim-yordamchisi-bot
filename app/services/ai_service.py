"""Pluggable AI backend (Groq / OpenAI-compatible / Gemini / Ollama) + rate limiting."""
from __future__ import annotations

import base64
import logging
from datetime import timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AiUsage, User, utcnow

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(60.0, connect=10.0)

_LANG_INSTRUCTION = {
    "uz": "Respond in Uzbek (Latin script).",
    "ru": "Respond in Russian.",
    "en": "Respond in English.",
    "kaa": "Respond in Karakalpak (Latin script). If unsure, use simple Uzbek.",
}


class AIError(Exception):
    pass


def available() -> bool:
    return settings.ai_configured


def build_system_prompt(lang: str, mode: str) -> str:
    lang_line = _LANG_INSTRUCTION.get(lang, _LANG_INSTRUCTION["uz"])
    if mode == "explain":
        task = (
            "You are a patient exam tutor. Explain why the correct answer to this "
            "multiple-choice question is right and why the student's choice is wrong. "
            "Be concise (3-6 sentences), show the reasoning, not just the answer."
        )
    else:
        task = (
            "You are a helpful homework tutor for school and DTM/attestation exam "
            "students in Uzbekistan. Solve the problem step by step, explaining the "
            "method so the student learns. Give the final answer clearly at the end. "
            "If the problem is ambiguous, state your assumptions. Keep it focused."
        )
    format_rules = (
        "OUTPUT FORMAT — very important, the client shows plain text:\n"
        "- Do NOT use LaTeX or math delimiters. No $, no $$, no \\( \\), no backslash "
        "commands like \\cdot, \\frac, \\text, \\mathbf, \\times, \\sqrt.\n"
        "- Write math in plain form with Unicode symbols: · × ÷ ² ³ √ ≈ ≤ ≥ ° ½ π. "
        "Example: area = a · b, 3 cm², √16 = 4, 1/2.\n"
        "- Do NOT use Markdown headings (#) or bold/italic markers (**, __). "
        "Use short labels followed by a colon and plain line breaks instead.\n"
        "- Use simple '-' bullets and blank lines between steps. Keep it compact."
    )
    return f"{task}\n{lang_line}\n{format_rules}"


# --- rate limiting ------------------------------------------------
async def within_rate_limit(session: AsyncSession, user: User) -> bool:
    since = utcnow() - timedelta(hours=1)
    used = (
        await session.execute(
            select(func.count(AiUsage.id)).where(
                AiUsage.user_id == user.id, AiUsage.created_at >= since
            )
        )
    ).scalar_one()
    return int(used) < settings.ai_rate_per_hour


async def record_usage(session: AsyncSession, user: User, mode: str, tokens: int = 0) -> None:
    session.add(AiUsage(user_id=user.id, mode=mode, tokens=tokens))
    await session.flush()


# --- provider dispatch -----------------------------------------
async def complete(
    *,
    system: str,
    user_text: str,
    history: list[dict] | None = None,
    image: tuple[bytes, str] | None = None,
) -> str:
    providers = [p for p in (settings.ai_provider, settings.ai_fallback) if p]
    last_err: Exception | None = None
    for name in providers:
        try:
            return await _dispatch(name.strip().lower(), system, user_text, history or [], image)
        except Exception as exc:  # noqa: BLE001 - try next provider
            logger.warning("AI provider %s failed: %s", name, exc)
            last_err = exc
    raise AIError(str(last_err) if last_err else "no AI provider configured")


async def _dispatch(name, system, user_text, history, image):
    if name in ("groq", "openai"):
        return await _openai_compatible(system, user_text, history, image)
    if name == "gemini":
        return await _gemini(system, user_text, history, image)
    if name == "ollama":
        return await _ollama(system, user_text, history, image)
    raise AIError(f"unknown provider {name!r}")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


async def _post_json(url: str, *, headers=None, params=None, json=None, attempts: int = 3) -> dict:
    """POST returning parsed JSON, retrying transient failures (5xx / network / timeout)."""
    import asyncio

    last: Exception | None = None
    for i in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.post(url, headers=headers, params=params, json=json)
            if resp.status_code >= 500:
                last = AIError(f"{resp.status_code} {resp.text[:200]}")
            else:
                resp.raise_for_status()
                return resp.json()
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last = exc
        if i < attempts - 1:
            await asyncio.sleep(1.5 * (i + 1))
    raise AIError(str(last) if last else "request failed")


async def _openai_compatible(system, user_text, history, image) -> str:
    if not (settings.openai_api_key and settings.openai_base_url):
        raise AIError("OpenAI-compatible endpoint not configured")
    messages = [{"role": "system", "content": system}]
    messages += [{"role": h["role"], "content": h["content"]} for h in history if h.get("content")]
    if image is not None:
        raw, mime = image
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text or "Please help with this."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{_b64(raw)}"}},
                ],
            }
        )
    else:
        messages.append({"role": "user", "content": user_text})

    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    data = await _post_json(
        url,
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={"model": settings.openai_model, "messages": messages, "temperature": 0.3},
    )
    return data["choices"][0]["message"]["content"].strip()


async def _ollama(system, user_text, history, image) -> str:
    if not settings.ollama_base_url:
        raise AIError("OLLAMA_BASE_URL not configured")
    messages = [{"role": "system", "content": system}]
    messages += [{"role": h["role"], "content": h["content"]} for h in history if h.get("content")]
    user_msg: dict = {"role": "user", "content": user_text or "Please help with this."}
    if image is not None:
        user_msg["images"] = [_b64(image[0])]
    messages.append(user_msg)

    url = settings.ollama_base_url.rstrip("/") + "/api/chat"
    data = await _post_json(
        url, json={"model": settings.ollama_model, "messages": messages, "stream": False}
    )
    return (data.get("message") or {}).get("content", "").strip()


async def _gemini(system, user_text, history, image) -> str:
    if not settings.gemini_api_key:
        raise AIError("GEMINI_API_KEY not configured")
    contents = []
    for h in history:
        if not h.get("content"):
            continue
        role = "model" if h["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": h["content"]}]})
    parts: list[dict] = [{"text": user_text or "Please help with this."}]
    if image is not None:
        raw, mime = image
        parts.append({"inline_data": {"mime_type": mime, "data": _b64(raw)}})
    contents.append({"role": "user", "parts": parts})

    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.3},
    }
    # Try the configured model, then stable fallbacks — a single model can be
    # renamed by Google or temporarily overloaded ("high demand" 503s).
    candidates = list(dict.fromkeys(
        [
            settings.gemini_model,
            "gemini-flash-latest",
            "gemini-flash-lite-latest",
            "gemini-2.5-flash",
        ]
    ))
    last: Exception | None = None
    data = None
    for model in candidates:
        try:
            data = await _post_json(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent",
                params={"key": settings.gemini_api_key},
                json=body,
                attempts=2,
            )
            break
        except Exception as exc:  # noqa: BLE001 - try the next model
            logger.warning("gemini model %s failed: %s", model, exc)
            last = exc
    if data is None:
        raise AIError(str(last) if last else "gemini request failed")
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError) as exc:
        raise AIError(f"unexpected Gemini response: {data}") from exc
    # Newer models may return multiple parts (e.g. a thought part + the answer);
    # keep every visible text segment.
    text = "\n".join(p["text"] for p in parts if isinstance(p, dict) and p.get("text")).strip()
    if not text:
        raise AIError(f"empty Gemini response: {data}")
    return text
