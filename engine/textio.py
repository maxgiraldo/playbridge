"""Text protocol so an LLM can sit at the table."""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.cards import (
    DISPLAY_SUIT_ORDER,
    Card,
    action_to_label,
    sort_hand,
)
from engine.notation import card_san, parse_san, seated_san

if TYPE_CHECKING:
    from engine.game import Game

SYSTEM_PROMPT = """You are playing bridge. Reply with exactly one legal token.

The language is chess-style and deterministic. One token, one action.
English is illegal (not "play ace of spades" or "one heart").

Cards (lowercase suit): As  Th  2c  Kd
Bids (uppercase strain): 1C 1D 1H 1S 1NT 4H 3NT
Calls: P  X  XX
MiniBridge only: *h  #9

Seated forms: NAs  W3s  N1S  EP  WX

On your turn send only a token from Legal.
"""


def format_card(card) -> str:
    return card_san(card)


def format_hand(cards) -> str:
    groups = []
    for suit in DISPLAY_SUIT_ORDER:
        in_suit = [card for card in sort_hand(cards) if card.suit == suit]
        if not in_suit:
            continue
        groups.append(" ".join(card_san(card) for card in in_suit))
    return "  ".join(groups) if groups else "(empty)"


def observation_text(game: Game, viewer: str | None = None) -> str:
    actor = viewer or game.controller()
    lines = [
        f"You are sitting {actor}. Controller this turn: {game.controller()} (cards from {game.to_act}).",
        f"Phase: {game.phase}.",
    ]
    if game.contract_label():
        lines.append(
            f"Contract: {game.goal}{game.trump} by {game.declarer}. Dummy is {game.dummy}."
        )
        lines.append(f"Tricks so far: NS {game.tricks_ns}, EW {game.tricks_ew}.")
    else:
        lines.append(
            f"HCP: N {game.hcp.get('N', 0)}, E {game.hcp.get('E', 0)}, "
            f"S {game.hcp.get('S', 0)}, W {game.hcp.get('W', 0)}."
        )
        if game.phase == "auction":
            lines.append(f"Dealer {game.dealer}. Vulnerability {game.vulnerability}.")
        elif game.declarer:
            lines.append(f"Declarer will be {game.declarer}; dummy {game.dummy}.")

    visible = game.visible_hands(viewer=actor)
    for seat in ("S", "N", "E", "W"):
        cards = visible.get(seat)
        if cards is None:
            lines.append(f"{seat} hand: hidden ({len(game.hands.get(seat, []))} cards)")
        else:
            rebuilt = [Card(suit=item["suit"], rank=item["rank"]) for item in cards]
            tag = " (dummy)" if seat == game.dummy else ""
            lines.append(f"{seat}{tag} hand: {format_hand(rebuilt)}")

    sheet = game.scoresheet()
    if sheet:
        lines.append("Scoresheet:")
        lines.append(sheet)
    if game.current_trick:
        plays = " ".join(seated_san(seat, card.id) for seat, card in game.current_trick)
        lines.append(f"Current trick: {plays}")
    elif game.phase == "play":
        lines.append("Current trick: empty (you may lead).")

    labels = [action_to_label(action) for action in game.legal_actions()]
    lines.append("Legal: " + " ".join(labels) if labels else "Legal: none (deal over)")
    if game.phase == "auction":
        lines.append("Reply with one call from Legal (1H, 1NT, P, X, XX).")
    elif game.phase == "select_trump":
        lines.append("Reply with one of Legal (*c *d *h *s *n).")
    elif game.phase == "select_goal":
        lines.append("Reply with one of Legal (#7 .. #13).")
    elif game.phase == "play":
        lines.append("Reply with one card token from Legal.")
    elif game.phase == "deal_over":
        result = game.deal_result or {}
        lines.append(f"Deal over. {result}")
    return "\n".join(lines)


def parse_action_text(text: str) -> int:
    """Parse a single SAN token. English phrases are rejected."""
    raw = text.strip().strip("`").splitlines()[0].strip() if text else ""
    parsed = parse_san(raw)
    if parsed is None:
        raise ValueError(f"not SAN: {text!r}. Use As, 1H, 1NT, P, X.")
    return parsed


def prompt_payload(game: Game) -> dict:
    labels = [action_to_label(action) for action in game.legal_actions()]
    return {
        "system": SYSTEM_PROMPT,
        "user": observation_text(game),
        "legal_actions": game.legal_actions(),
        "legal_action_labels": labels,
        "phase": game.phase,
        "to_act": game.to_act,
        "controller": None if game.phase == "deal_over" else game.controller(),
        "done": game.phase == "deal_over",
    }
