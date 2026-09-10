#!/usr/bin/env python3
"""Play random legal moves against the MiniBridge HTTP API.

Usage:
  python examples/random_agent.py
  python examples/random_agent.py --url http://127.0.0.1:8000 --deals 20
"""

from __future__ import annotations

import argparse
import random

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Random MiniBridge learning client")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--deals", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    with httpx.Client(base_url=args.url, timeout=10.0) as client:
        created = client.post("/api/games", json={"seed": args.seed, "auto_robots": True})
        created.raise_for_status()
        game_id = created.json()["id"]
        rewards = []

        for deal in range(args.deals):
            if deal:
                client.post(f"/api/games/{game_id}/reset").raise_for_status()
            done = False
            deal_reward = 0.0
            while not done:
                obs = client.get(f"/api/games/{game_id}/observation").json()
                legal = obs["legal_actions"]
                if not legal:
                    break
                action = rng.choice(legal)
                stepped = client.post(
                    f"/api/games/{game_id}/step",
                    json={"action": action},
                )
                stepped.raise_for_status()
                body = stepped.json()
                deal_reward = body.get("reward", 0.0)
                done = body.get("done", False)
            rewards.append(deal_reward)
            print(f"deal {deal + 1}: reward={deal_reward:+.2f} score={body['score']}")

        print(f"mean reward: {sum(rewards) / len(rewards):+.2f}")
        path = client.get(f"/api/games/{game_id}/trajectory")
        path.raise_for_status()
        print(f"trajectory steps: {path.json()['steps']}")


if __name__ == "__main__":
    main()
