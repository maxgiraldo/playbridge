#!/usr/bin/env python3
"""Sit an OpenAI-compatible LLM at one or more MiniBridge seats.

  export OPENAI_API_KEY=...
  python examples/llm_bot.py --url http://127.0.0.1:8000 --game table --model gpt-4.1-mini

The bot polls GET /api/games/{id}/text and POSTs a text action when
waiting_for.kind == llm.
"""

from __future__ import annotations

import argparse
import os
import time

import httpx


def chat(base_url: str, api_key: str, model: str, system: str, user: str) -> str:
    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=45.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--game", default="table")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "gpt-4.1-mini"))
    parser.add_argument("--llm-url", default=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY"))
    args = parser.parse_args()
    if not args.api_key:
        raise SystemExit("set OPENAI_API_KEY or --api-key")

    with httpx.Client(base_url=args.url, timeout=20.0) as client:
        client.post(
            f"/api/games/{args.game}/config",
            json={"partner": "llm", "opponents": "llm", "llm_model": args.model},
        ).raise_for_status()
        while True:
            prompt = client.get(f"/api/games/{args.game}/text").json()
            waiting = prompt.get("waiting_for") or {}
            if prompt.get("done") or waiting.get("kind") != "llm":
                time.sleep(1)
                continue
            print(f"\n--- {waiting} ---\n{prompt['user']}\n")
            move = chat(args.llm_url, args.api_key, args.model, prompt["system"], prompt["user"])
            print("model:", move)
            stepped = client.post(
                f"/api/games/{args.game}/step",
                json={"action": move},
            )
            if stepped.status_code >= 400:
                print("rejected:", stepped.text)
                time.sleep(1)
                continue
            body = stepped.json()
            if body.get("done"):
                print("deal over", body.get("deal_result"))
                client.post(f"/api/games/{args.game}/reset", json={})


if __name__ == "__main__":
    main()
