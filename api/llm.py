"""Call an OpenAI-compatible chat model to pick a MiniBridge action."""

from __future__ import annotations

import os
from typing import Any

import httpx

from engine.cards import action_to_label
from engine.game import Game
from engine.textio import parse_action_text, prompt_payload


def llm_ready(game: Game) -> bool:
    return bool(game.llm_api_key or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def _headers(game: Game) -> dict[str, str]:
    key = game.llm_api_key or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def complete_action(game: Game) -> int:
    prompt = prompt_payload(game)
    legal = set(game.legal_actions())
    messages = [
        {"role": "system", "content": prompt["system"]},
        {"role": "user", "content": prompt["user"]},
    ]
    last_error = "llm returned no legal action"
    for _ in range(2):
        content = _chat(game, messages)
        try:
            parsed = game._parse_action(parse_action_text(content))
        except ValueError as exc:
            last_error = str(exc)
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"That was not a legal action ({last_error}). "
                        f"Reply with exactly one of: {', '.join(prompt['legal_action_labels'])}"
                    ),
                }
            )
            continue
        if parsed in legal:
            return parsed
        last_error = f"{action_to_label(parsed)} is not legal now"
        messages.append({"role": "assistant", "content": content})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{last_error}. Reply with exactly one of: "
                    f"{', '.join(prompt['legal_action_labels'])}"
                ),
            }
        )
    raise RuntimeError(last_error)


def _chat(game: Game, messages: list[dict[str, str]]) -> str:
    base = game.llm_base_url.rstrip("/")
    url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    body: dict[str, Any] = {
        "model": game.llm_model,
        "messages": messages,
        "temperature": 0,
    }
    with httpx.Client(timeout=45.0) as client:
        response = client.post(url, headers=_headers(game), json=body)
        response.raise_for_status()
        data = response.json()
    return data["choices"][0]["message"]["content"]
