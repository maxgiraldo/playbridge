"""Double-dummy engine: perfect play with all remaining cards known.

This is the same idea as Bo Haglund's DDS. We search the play tree with
alpha-beta and return how many of the remaining tricks North-South can take.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.cards import Card, SEATS

if TYPE_CHECKING:
    from engine.game import Game

SEAT_I = {seat: index for index, seat in enumerate(SEATS)}
NEXT = (1, 2, 3, 0)
NS_SEATS = (0, 2)
SUIT_MASK = tuple(((1 << 13) - 1) << (suit * 13) for suit in range(4))
TRUMP_ID = {"C": 0, "D": 1, "H": 2, "S": 3, "NT": None, None: None}

NODE_LIMIT = 40_000


def _suit(card: int) -> int:
    return card // 13


def _rank(card: int) -> int:
    return card % 13


def _beats(card: int, current: int, lead: int, trump: int | None) -> bool:
    card_tr = trump is not None and _suit(card) == trump
    cur_tr = trump is not None and _suit(current) == trump
    if card_tr and not cur_tr:
        return True
    if cur_tr and not card_tr:
        return False
    if _suit(card) != _suit(current):
        return False
    return _rank(card) > _rank(current)


def _winner(trick: list[tuple[int, int]], trump: int | None) -> int:
    lead = _suit(trick[0][1])
    win_seat, win_card = trick[0]
    for seat, card in trick[1:]:
        if _beats(card, win_card, lead, trump):
            win_seat, win_card = seat, card
    return win_seat


def _legal(hand: int, lead: int | None) -> int:
    if lead is None:
        return hand
    follow = hand & SUIT_MASK[lead]
    return follow or hand


def _cards(mask: int) -> list[int]:
    out: list[int] = []
    while mask:
        bit = mask & -mask
        out.append(bit.bit_length() - 1)
        mask ^= bit
    out.sort(key=_rank, reverse=True)
    return out


def _search(
    hands: list[int],
    to_act: int,
    trick: list[tuple[int, int]],
    trump: int | None,
    alpha: int,
    beta: int,
    nodes: list[int],
) -> int:
    nodes[0] += 1
    if nodes[0] > NODE_LIMIT:
        raise TimeoutError

    remaining = hands[0] | hands[1] | hands[2] | hands[3]
    if remaining == 0 and not trick:
        return 0

    lead = None if not trick else _suit(trick[0][1])
    legal = _legal(hands[to_act], lead)
    maximizing = to_act in NS_SEATS
    best = -1 if maximizing else 14

    for card in _cards(legal):
        next_hands = hands[:]
        next_hands[to_act] &= ~(1 << card)
        next_trick = trick + [(to_act, card)]
        if len(next_trick) < 4:
            val = _search(next_hands, NEXT[to_act], next_trick, trump, alpha, beta, nodes)
        else:
            winner = _winner(next_trick, trump)
            extra = 1 if winner in NS_SEATS else 0
            val = extra + _search(next_hands, winner, [], trump, alpha - extra, beta - extra, nodes)
        if maximizing:
            if val > best:
                best = val
            if best > alpha:
                alpha = best
        else:
            if val < best:
                best = val
            if best < beta:
                beta = best
        if alpha >= beta:
            break
    return best


def ns_tricks_from(game: Game) -> int | None:
    """Remaining NS tricks with perfect play, or None if the tree is too big."""
    trump = TRUMP_ID.get(game.trump)
    hands = [0, 0, 0, 0]
    for seat, cards in game.hands.items():
        mask = 0
        for card in cards:
            mask |= 1 << card.id
        hands[SEAT_I[seat]] = mask
    trick = [(SEAT_I[seat], card.id) for seat, card in game.current_trick]
    try:
        return _search(hands, SEAT_I[game.to_act], trick, trump, -1, 14, [0])
    except TimeoutError:
        return None


def engine_card(game: Game) -> int | None:
    """Best legal card for the acting side, or None if the tree is too big."""
    legal = game.legal_cards(game.to_act)
    if not legal:
        return None
    if len(legal) == 1:
        return legal[0].id
    if sum(len(cards) for cards in game.hands.values()) > 24:
        return None

    actor_ns = game.to_act in {"N", "S"}
    best_card = legal[0]
    best_val: int | None = None
    for card in sorted(legal, key=lambda item: -item.rank_value):
        clone = game.clone()
        clone.auto_robots = False
        clone._apply(card.id)
        rest = 0 if clone.phase == "deal_over" else ns_tricks_from(clone)
        if rest is None:
            return None
        total_ns = clone.tricks_ns + rest
        value = total_ns if actor_ns else -total_ns
        if best_val is None or value > best_val:
            best_val = value
            best_card = card
    return best_card.id


def estimate_ns_tricks(game: Game) -> int:
    """DDS if cheap, otherwise a length + HCP guess."""
    found = ns_tricks_from(game)
    if found is not None:
        return game.tricks_ns + found
    hcp = game.hcp.get("N", 0) + game.hcp.get("S", 0)
    return min(13, max(7, 6 + max(0, hcp - 12) // 3))
