"""Contract-bridge auction: legal calls, contract, dealer, vulnerability."""

from __future__ import annotations

from engine.cards import (
    ACTION_DOUBLE,
    ACTION_PASS,
    ACTION_REDOUBLE,
    BID_LEVELS,
    BID_STRAINS,
    NS,
    PARTNERS,
    SEATS,
    bid_action,
    decode_bid,
)

# Duplicate board cycle (boards 1-16, then repeat).
VUL_CYCLE = (
    "none",
    "NS",
    "EW",
    "both",
    "NS",
    "EW",
    "both",
    "none",
    "EW",
    "both",
    "none",
    "NS",
    "both",
    "none",
    "NS",
    "EW",
)


def dealer_for_deal(deal_number: int) -> str:
    return SEATS[(max(1, deal_number) - 1) % 4]


def vulnerability_for_deal(deal_number: int) -> str:
    return VUL_CYCLE[(max(1, deal_number) - 1) % 16]


def side_vulnerable(vulnerability: str, seat: str) -> bool:
    if vulnerability == "both":
        return True
    if vulnerability == "none":
        return False
    return seat in (NS if vulnerability == "NS" else ("E", "W"))


def is_strain_bid(action: int) -> bool:
    return bid_action(1, "C") <= action <= bid_action(7, "NT")


def last_strain_bid(auction: list[tuple[str, int]]) -> tuple[str, int] | None:
    for seat, action in reversed(auction):
        if is_strain_bid(action):
            return seat, action
    return None


def last_non_pass(auction: list[tuple[str, int]]) -> tuple[str, int] | None:
    for seat, action in reversed(auction):
        if action != ACTION_PASS:
            return seat, action
    return None


def consecutive_passes(auction: list[tuple[str, int]]) -> int:
    count = 0
    for _, action in reversed(auction):
        if action != ACTION_PASS:
            break
        count += 1
    return count


def auction_complete(auction: list[tuple[str, int]]) -> bool:
    if len(auction) >= 4 and all(action == ACTION_PASS for _, action in auction[:4]) and len(auction) == 4:
        return True
    if last_strain_bid(auction) is None:
        return False
    return consecutive_passes(auction) >= 3


def passed_out(auction: list[tuple[str, int]]) -> bool:
    return len(auction) >= 4 and all(action == ACTION_PASS for _, action in auction) and last_strain_bid(auction) is None


def legal_calls(auction: list[tuple[str, int]], seat: str) -> list[int]:
    legal = [ACTION_PASS]
    last_bid = last_strain_bid(auction)
    floor = -1 if last_bid is None else last_bid[1]
    for level in BID_LEVELS:
        for strain in BID_STRAINS:
            action = bid_action(level, strain)
            if last_bid is None or action > floor:
                legal.append(action)
    last = last_non_pass(auction)
    if last is not None:
        last_seat, last_action = last
        same_side = PARTNERS[last_seat] == seat or last_seat == seat
        if is_strain_bid(last_action) and not same_side:
            legal.append(ACTION_DOUBLE)
        if last_action == ACTION_DOUBLE and not same_side:
            legal.append(ACTION_REDOUBLE)
    return legal


def contract_from_auction(auction: list[tuple[str, int]]) -> dict | None:
    last = last_strain_bid(auction)
    if last is None:
        return None
    bidder, action = last
    level, strain = decode_bid(action)
    side = {bidder, PARTNERS[bidder]}
    declarer = bidder
    for seat, call in auction:
        if seat in side and is_strain_bid(call) and decode_bid(call)[1] == strain:
            declarer = seat
            break
    doubled = 0
    for _, call in reversed(auction):
        if call == ACTION_REDOUBLE:
            doubled = 2
            break
        if call == ACTION_DOUBLE:
            doubled = 1
            break
        if is_strain_bid(call):
            break
    return {
        "declarer": declarer,
        "dummy": PARTNERS[declarer],
        "level": level,
        "strain": strain,
        "trump": strain,
        "goal": level + 6,
        "doubled": doubled,
    }


def format_auction(auction: list[tuple[str, int]], dealer: str) -> str:
    from engine.cards import action_to_label

    start = SEATS.index(dealer)
    cells = ["\u2014"] * start
    cells.extend(action_to_label(action) for _, action in auction)
    while len(cells) % 4:
        cells.append("")
    lines = ["   N    E    S    W"]
    for row in range(0, len(cells), 4):
        chunk = cells[row : row + 4]
        lines.append("".join(f"{item:<5}" for item in chunk).rstrip())
    return "\n".join(lines)
