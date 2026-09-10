"""In-memory PlayBridge profile, archive, and daily puzzle."""

from __future__ import annotations

import json
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from engine.puzzles import generate_puzzle
from engine.rating import COMPUTER_RATINGS, elo_update

DATA = Path(__file__).resolve().parent.parent / "data"
DATA.mkdir(exist_ok=True)
STORE_PATH = DATA / "platform.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Platform:
    def __init__(self) -> None:
        self.profile: dict[str, Any] = {
            "name": "You",
            "rating": 1200,
            "puzzle_rating": 1200,
            "games": 0,
            "wins": 0,
            "losses": 0,
            "puzzles_solved": 0,
            "puzzle_streak": 0,
        }
        self.history: list[dict[str, Any]] = []
        self.puzzles: dict[str, dict[str, Any]] = {}
        self.daily_id: str | None = None
        self.daily_date: str | None = None
        self._load()
        self.ensure_daily()

    def _load(self) -> None:
        if not STORE_PATH.exists():
            return
        raw = json.loads(STORE_PATH.read_text())
        self.profile.update(raw.get("profile") or {})
        self.history = list(raw.get("history") or [])
        self.daily_id = raw.get("daily_id")
        self.daily_date = raw.get("daily_date")

    def save(self) -> None:
        STORE_PATH.write_text(
            json.dumps(
                {
                    "profile": self.profile,
                    "history": self.history[-80:],
                    "daily_id": self.daily_id,
                    "daily_date": self.daily_date,
                },
                indent=2,
            )
        )

    def me(self) -> dict[str, Any]:
        return {
            **self.profile,
            "win_rate": (
                round(100 * self.profile["wins"] / self.profile["games"])
                if self.profile["games"]
                else 0
            ),
            "recent": self.history[-8:][::-1],
            "daily": self.daily_summary(),
        }

    def daily_summary(self) -> dict[str, Any] | None:
        self.ensure_daily()
        puzzle = self.puzzles.get(self.daily_id or "")
        if not puzzle:
            return None
        return {
            "id": puzzle["id"],
            "kind": puzzle["kind"],
            "prompt": puzzle["prompt"],
            "date": self.daily_date,
        }

    def ensure_daily(self) -> dict[str, Any]:
        today = date.today().isoformat()
        if self.daily_date != today or not self.daily_id or self.daily_id not in self.puzzles:
            seed = int(today.replace("-", ""))
            try:
                puzzle = generate_puzzle(kind="trump", seed=seed)
            except RuntimeError:
                puzzle = generate_puzzle(kind="card", seed=seed + 1)
            self.puzzles[puzzle["id"]] = puzzle
            self.daily_id = puzzle["id"]
            self.daily_date = today
            self.save()
        return self.puzzles[self.daily_id]

    def new_puzzle(self, kind: str | None = None) -> dict[str, Any]:
        puzzle = generate_puzzle(kind=kind)
        self.puzzles[puzzle["id"]] = puzzle
        return self.public_puzzle(puzzle)

    def public_puzzle(self, puzzle: dict[str, Any]) -> dict[str, Any]:
        hidden = dict(puzzle)
        hidden.pop("answer", None)
        hidden.pop("answer_label", None)
        return hidden

    def get_puzzle(self, puzzle_id: str) -> dict[str, Any]:
        puzzle = self.puzzles.get(puzzle_id)
        if puzzle is None and self.daily_id == puzzle_id:
            puzzle = self.ensure_daily()
        if puzzle is None:
            raise KeyError(puzzle_id)
        return puzzle

    def solve_puzzle(self, puzzle_id: str, action: int) -> dict[str, Any]:
        puzzle = self.get_puzzle(puzzle_id)
        correct = int(action) == int(puzzle["answer"])
        score = 1.0 if correct else 0.0
        new_rating, delta = elo_update(self.profile["puzzle_rating"], 1400, score, k=16)
        self.profile["puzzle_rating"] = new_rating
        if correct:
            self.profile["puzzles_solved"] += 1
            self.profile["puzzle_streak"] += 1
        else:
            self.profile["puzzle_streak"] = 0
        self.save()
        return {
            "correct": correct,
            "answer": puzzle["answer"],
            "answer_label": puzzle["answer_label"],
            "hint": puzzle.get("hint"),
            "rating": new_rating,
            "rating_delta": delta,
            "streak": self.profile["puzzle_streak"],
        }

    def archive_deal(self, game_record: dict[str, Any]) -> dict[str, Any]:
        skill = game_record.get("skill") or "intermediate"
        opponent = COMPUTER_RATINGS.get(skill, 1200)
        score = 1.0 if game_record.get("won") else 0.0
        new_rating, delta = elo_update(self.profile["rating"], opponent, score, k=24)
        record = {
            "id": uuid.uuid4().hex[:10],
            "created": _now(),
            "created_ms": int(time.time() * 1000),
            "rating_before": self.profile["rating"],
            "rating_after": new_rating,
            "rating_delta": delta,
            "opponent": skill,
            "opponent_rating": opponent,
            **game_record,
        }
        self.profile["rating"] = new_rating
        self.profile["games"] += 1
        if game_record.get("won"):
            self.profile["wins"] += 1
        else:
            self.profile["losses"] += 1
        self.history.append(record)
        self.save()
        return record

    def get_game(self, game_id: str) -> dict[str, Any]:
        for item in self.history:
            if item["id"] == game_id:
                return item
        raise KeyError(game_id)


platform = Platform()
