"""Simple engine bidding: open, raise, overcall, or pass."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from engine.auction import is_strain_bid, last_strain_bid
from engine.cards import (
    ACTION_DOUBLE,
    ACTION_PASS,
    PARTNERS,
    SUITS,
    bid_action,
    decode_bid,
    hcp_of,
)

if TYPE_CHECKING:
    from engine.game import Game


def _balanced(lengths: dict[str, int]) -> bool:
    pattern = tuple(sorted(lengths.get(suit, 0) for suit in SUITS))
    return pattern in {(3, 3, 3, 4), (2, 3, 4, 4), (2, 3, 3, 5)}


def _longest_suits(lengths: dict[str, int]) -> list[str]:
    best = max(lengths.values()) if lengths else 0
    majors = [suit for suit in ("S", "H") if lengths.get(suit, 0) == best]
    if majors:
        return majors
    return [suit for suit in ("S", "H", "D", "C") if lengths.get(suit, 0) == best]


def _cheapest(legal: set[int], level: int, strain: str) -> int | None:
    action = bid_action(level, strain)
    return action if action in legal else None


def choose_call(game: Game) -> int:
    seat = game.to_act
    legal = set(game.legal_actions())
    if ACTION_PASS not in legal:
        return next(iter(sorted(legal)))
    hand = game.hands[seat]
    hcp = hcp_of(hand)
    lengths = Counter(card.suit for card in hand)
    last = last_strain_bid(game.auction)
    partner = PARTNERS[seat]

    if last is None:
        return _opening(hcp, lengths, legal)

    last_seat, last_action = last
    level, strain = decode_bid(last_action)
    if last_seat == partner:
        return _respond(hcp, lengths, level, strain, legal)
    if last_seat == seat:
        return ACTION_PASS
    return _compete(hcp, lengths, last_seat, level, strain, legal, partner, game)


def _opening(hcp: int, lengths: dict[str, int], legal: set[int]) -> int:
    if 15 <= hcp <= 17 and _balanced(lengths):
        nt = _cheapest(legal, 1, "NT")
        if nt is not None:
            return nt
    if hcp < 12:
        return ACTION_PASS
    if hcp >= 20 and _cheapest(legal, 2, "C"):
        # skip artificial 2C; just open one of a suit
        pass
    for suit in _longest_suits(lengths):
        if lengths[suit] >= (5 if suit in {"S", "H"} else 3):
            bid = _cheapest(legal, 1, suit)
            if bid is not None:
                return bid
    for suit in ("S", "H", "D", "C"):
        bid = _cheapest(legal, 1, suit)
        if bid is not None:
            return bid
    return ACTION_PASS


def _respond(hcp: int, lengths: dict[str, int], level: int, strain: str, legal: set[int]) -> int:
    if hcp < 6:
        return ACTION_PASS
    support = 13 if strain == "NT" else lengths.get(strain, 0)
    if strain == "NT":
        if hcp >= 10:
            return _cheapest(legal, 3, "NT") or ACTION_PASS
        if hcp >= 8:
            return _cheapest(legal, 2, "NT") or ACTION_PASS
        return ACTION_PASS
    if support >= 3:
        if hcp >= 13 and strain in {"S", "H"}:
            return _cheapest(legal, 4, strain) or ACTION_PASS
        if hcp >= 13 and strain in {"C", "D"}:
            return _cheapest(legal, 5, strain) or _cheapest(legal, 3, "NT") or ACTION_PASS
        if hcp >= 10:
            return _cheapest(legal, min(3, level + 1), strain) or ACTION_PASS
        return _cheapest(legal, min(2, level + 1), strain) or ACTION_PASS
    if hcp >= 13 and _balanced(lengths):
        return _cheapest(legal, 3, "NT") or ACTION_PASS
    if hcp >= 6:
        for suit in _longest_suits(lengths):
            if lengths[suit] >= 4:
                for try_level in (1, 2):
                    bid = _cheapest(legal, try_level, suit)
                    if bid is not None:
                        return bid
    return ACTION_PASS


def _compete(
    hcp: int,
    lengths: dict[str, int],
    opp_seat: str,
    level: int,
    strain: str,
    legal: set[int],
    partner: str,
    game: Game,
) -> int:
    if level >= 4:
        return ACTION_PASS
    partner_bid = None
    for seat, action in game.auction:
        if seat == partner and is_strain_bid(action):
            partner_bid = action
    if partner_bid is not None:
        return ACTION_PASS
    if hcp >= 12 and lengths.get(strain, 0) <= 2 and ACTION_DOUBLE in legal:
        return ACTION_DOUBLE
    if hcp >= 8:
        for suit in _longest_suits(lengths):
            if lengths[suit] >= 5 and suit != strain:
                for try_level in (1, 2):
                    bid = _cheapest(legal, try_level, suit)
                    if bid is not None:
                        return bid
    return ACTION_PASS
