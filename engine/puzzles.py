"""Generate MiniBridge tactics puzzles from live deals."""

from __future__ import annotations

import random
import uuid
from typing import Any

from engine.cards import NS, SUIT_SYMBOLS, action_to_label, card_from_id
from engine.game import Game
from engine.robots import choose_action, choose_trump


def _card_label(card_id: int) -> str:
    card = card_from_id(card_id)
    return f"{card.rank if card.rank != 'T' else '10'}{SUIT_SYMBOLS[card.suit]}"


def generate_card_puzzle(seed: int | None = None) -> dict[str, Any] | None:
    rng = random.Random(seed)
    for _ in range(80):
        game = Game(
            seed=rng.randint(1, 1_000_000),
            auto_robots=False,
            agent_seats=("N", "E", "S", "W"),
        )
        steps = 0
        while game.phase != "deal_over" and steps < 40:
            if (
                game.phase == "play"
                and game.to_act in NS
                and game.current_trick
                and 1 <= len(game.current_trick) <= 3
            ):
                legal = game.legal_cards(game.to_act)
                winners = [
                    card
                    for card in legal
                    if game.winner_of_plays(list(game.current_trick) + [(game.to_act, card)])
                    == game.to_act
                ]
                if len(winners) == 1 and len(legal) >= 2:
                    return _pack_card_puzzle(game, winners[0].id, seed)
            game.step(choose_action(game, "intermediate"))
            steps += 1
    return None


def generate_trump_puzzle(seed: int | None = None) -> dict[str, Any] | None:
    rng = random.Random(seed)
    for _ in range(40):
        game = Game(seed=rng.randint(1, 1_000_000), auto_robots=False)
        if game.phase != "select_trump" or game.declarer not in NS:
            continue
        answer = choose_trump(game)
        return {
            "id": uuid.uuid4().hex[:10],
            "kind": "trump",
            "prompt": "Choose the best trump for this North\u2013South pair.",
            "hint": "Look for an 8-card fit. Go notrump when the hands are balanced and strong.",
            "answer": answer,
            "answer_label": action_to_label(answer),
            "choices": [
                {"action": 52, "label": "\u2663"},
                {"action": 53, "label": "\u2666"},
                {"action": 54, "label": "\u2665"},
                {"action": 55, "label": "\u2660"},
                {"action": 56, "label": "NT"},
            ],
            "hands": {
                "N": [card.to_dict() for card in game.hands["N"]],
                "S": [card.to_dict() for card in game.hands["S"]],
            },
            "hcp": {"N": game.hcp["N"], "S": game.hcp["S"], "ns": game.hcp["N"] + game.hcp["S"]},
            "declarer": game.declarer,
        }
    return None


def _pack_card_puzzle(game: Game, answer: int, seed: int | None) -> dict[str, Any]:
    legal = [card.id for card in game.legal_cards(game.to_act)]
    return {
        "id": uuid.uuid4().hex[:10],
        "kind": "card",
        "prompt": f"Win this trick from {game.to_act}.",
        "hint": "Follow suit if you can. Trump only if you are void and need the trick.",
        "answer": answer,
        "answer_label": _card_label(answer),
        "choices": [{"action": card_id, "label": _card_label(card_id)} for card_id in legal],
        "to_act": game.to_act,
        "trump": game.trump,
        "contract": game.contract_label(),
        "current_trick": [
            {"seat": seat, "card": card.to_dict()} for seat, card in game.current_trick
        ],
        "hands": {
            "N": [card.to_dict() for card in game.hands["N"]],
            "S": [card.to_dict() for card in game.hands["S"]],
        },
        "hcp": {"N": game.hcp["N"], "S": game.hcp["S"]},
        "seed": seed,
    }


def generate_puzzle(kind: str | None = None, seed: int | None = None) -> dict[str, Any]:
    rng = random.Random(seed)
    wanted = kind or rng.choice(("card", "trump"))
    puzzle = generate_card_puzzle(seed) if wanted == "card" else generate_trump_puzzle(seed)
    if puzzle is None:
        puzzle = generate_trump_puzzle(seed) or generate_card_puzzle(seed)
    if puzzle is None:
        raise RuntimeError("could not generate a puzzle")
    return puzzle
