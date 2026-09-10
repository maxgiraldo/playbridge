"""Chess-style compact notation for four-seat MiniBridge.

Chess writes a piece and a square: Nb4, Ka1.
Here the seat is the piece and the card is the square:

    NAs   North plays the ace of spades
    W3s   West plays the three of spades
    SQh   South plays the queen of hearts

When it is your turn, send only the card (like sending just Nb4):

    As  Th  2c  Kd

Contract:

    *h    trump hearts
    *n    notrump
    #9    trick goal 9

English is rejected. One token maps to one action.
"""

from __future__ import annotations

import re

from engine.cards import (
    ACTION_DOUBLE,
    ACTION_PASS,
    ACTION_PLAY_END,
    ACTION_REDOUBLE,
    SUITS,
    Card,
    action_to_label,
    bid_action,
    card_from_id,
    goal_action,
    trump_action,
)

SUIT_FROM_SAN = {
    "c": "C",
    "d": "D",
    "h": "H",
    "s": "S",
    "\u2663": "C",
    "\u2666": "D",
    "\u2665": "H",
    "\u2660": "S",
}
TRUMP_FROM_SAN = {"c": "C", "d": "D", "h": "H", "s": "S", "n": "NT", "nt": "NT"}
SEATS = ("N", "E", "S", "W")

_VERB = re.compile(r"^(play|trump|goal|bid|call)[:\s]*", re.I)
_CARD = re.compile(r"^(10|[2-9TtJjQqKkAa])([CDHScdhs\u2663\u2666\u2665\u2660])$")
_TRUMP = re.compile(r"^\*(c|d|h|s|n|nt)$", re.I)
_GOAL = re.compile(r"^#(7|8|9|10|11|12|13)$")
_BID = re.compile(r"^([1-7])(NT|C|D|H|S)$")
_BID_NT = re.compile(r"^([1-7])(N|NT)$", re.I)
_PASS = re.compile(r"^P$")
_DOUBLE = re.compile(r"^X$")
_REDOUBLE = re.compile(r"^XX$")


def card_san(card: Card) -> str:
    return f"{card.rank}{card.suit.lower()}"


def card_from_san(token: str) -> Card | None:
    match = _CARD.fullmatch(token.strip())
    if not match:
        return None
    rank = match.group(1).upper()
    if rank == "10":
        rank = "T"
    suit_key = match.group(2).lower()
    suit = SUIT_FROM_SAN.get(suit_key)
    if suit is None and match.group(2).upper() in SUITS:
        suit = match.group(2).upper()
    if suit is None:
        return None
    return Card(suit, rank)


def action_san(action: int) -> str:
    return action_to_label(action)


def seated_san(seat: str, action: int) -> str:
    if 0 <= action < ACTION_PLAY_END:
        return f"{seat.upper()}{card_san(card_from_id(action))}"
    return f"{seat.upper()}{action_san(action)}"


def _parse_token(raw: str) -> int | None:
    if not raw:
        return None
    if raw[0] in "NESWnesw" and len(raw) > 1:
        rest = raw[1:]
        parsed = _parse_body(rest)
        if parsed is not None:
            return parsed
    return _parse_body(raw)


def _parse_body(raw: str) -> int | None:
    if _PASS.fullmatch(raw) or raw == "Pass":
        return ACTION_PASS
    if _REDOUBLE.fullmatch(raw):
        return ACTION_REDOUBLE
    if _DOUBLE.fullmatch(raw):
        return ACTION_DOUBLE
    bid = _BID.fullmatch(raw)
    if bid:
        strain = "NT" if bid.group(2) == "NT" else bid.group(2)
        return bid_action(int(bid.group(1)), strain)
    nt = _BID_NT.fullmatch(raw)
    if nt:
        return bid_action(int(nt.group(1)), "NT")
    trump = _TRUMP.fullmatch(raw)
    if trump:
        return trump_action(TRUMP_FROM_SAN[trump.group(1).lower()])
    goal = _GOAL.fullmatch(raw)
    if goal:
        return goal_action(int(goal.group(1)))
    card = card_from_san(raw)
    if card is not None:
        return card.id
    return None


def parse_san(text: str) -> int | None:
    raw = text.strip().strip("`").splitlines()[0].strip()
    raw = re.sub(r"^(action|move|output)\s*[:=]\s*", "", raw, flags=re.I)
    stripped = _VERB.sub("", raw, count=1)
    if stripped != raw and re.search(r"\s", stripped.strip()):
        return None
    return _parse_token(re.sub(r"\s+", "", stripped))


def format_scoresheet(
    tricks: list,
    contract: tuple[str, int] | None,
    current_trick=None,
    auction_text: str | None = None,
    heading: str | None = None,
) -> str:
    """Chess scoresheet: auction, then *h #9, then  1. W3s NAs E6s SQh"""
    lines: list[str] = []
    if heading:
        lines.append(heading)
    if auction_text:
        lines.append(auction_text)
    if contract is not None:
        trump, goal = contract
        strain = "n" if trump == "NT" else trump.lower()
        lines.append(f"*{strain} #{goal}")
    for index, trick in enumerate(tricks, start=1):
        moves = " ".join(f"{seat}{card_san(card)}" for seat, card in trick)
        lines.append(f"{index:>2}. {moves}")
    if current_trick:
        index = len(tricks) + 1
        moves = " ".join(f"{seat}{card_san(card)}" for seat, card in current_trick)
        lines.append(f"{index:>2}. {moves}")
    return "\n".join(lines)
