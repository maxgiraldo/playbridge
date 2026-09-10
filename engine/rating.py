"""Elo updates for Play vs Computer and puzzles."""

from __future__ import annotations

COMPUTER_RATINGS = {
    "beginner": 600,
    "intermediate": 1200,
    "advanced": 1600,
    "master": 2000,
}


def expected_score(rating: int, opponent: int) -> float:
    return 1.0 / (1.0 + 10 ** ((opponent - rating) / 400.0))


def elo_update(rating: int, opponent: int, score: float, k: int = 24) -> tuple[int, int]:
    """Return (new_rating, delta). score is 1 win, 0.5 draw, 0 loss."""
    delta = int(round(k * (score - expected_score(rating, opponent))))
    return rating + delta, delta
