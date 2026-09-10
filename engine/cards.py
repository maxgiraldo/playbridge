"""Cards, seats, and the discrete action space used by learning agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

SEATS = ("N", "E", "S", "W")
PARTNERS = {"N": "S", "S": "N", "E": "W", "W": "E"}
NS = ("N", "S")
EW = ("E", "W")

SUITS = ("C", "D", "H", "S")
SUIT_NAMES = {"C": "clubs", "D": "diamonds", "H": "hearts", "S": "spades"}
SUIT_SYMBOLS = {"C": "\u2663", "D": "\u2666", "H": "\u2665", "S": "\u2660"}
DISPLAY_SUIT_ORDER = ("S", "H", "C", "D")

RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")
RANK_VALUES = {rank: index for index, rank in enumerate(RANKS)}
HCP_VALUES = {"A": 4, "K": 3, "Q": 2, "J": 1}

TRUMPS = ("C", "D", "H", "S", "NT")
GOAL_TRICKS = tuple(range(7, 14))

# Discrete actions:
# 0-51 play a card
# 52-56 MiniBridge trump C D H S NT
# 57-63 MiniBridge goal 7-13
# 64-98 contract bids 1C..7NT
# 99 Pass  100 Double  101 Redouble
ACTION_PLAY_END = 52
ACTION_TRUMP_START = 52
ACTION_GOAL_START = 57
ACTION_BID_START = 64
ACTION_PASS = 99
ACTION_DOUBLE = 100
ACTION_REDOUBLE = 101
ACTION_SPACE = 102
BID_STRAINS = TRUMPS
BID_LEVELS = (1, 2, 3, 4, 5, 6, 7)


@dataclass(frozen=True, order=True)
class Card:
    suit: str
    rank: str

    def __post_init__(self) -> None:
        if self.suit not in SUITS:
            raise ValueError(f"invalid suit: {self.suit}")
        if self.rank not in RANKS:
            raise ValueError(f"invalid rank: {self.rank}")

    @property
    def id(self) -> int:
        return SUITS.index(self.suit) * 13 + RANKS.index(self.rank)

    @property
    def hcp(self) -> int:
        return HCP_VALUES.get(self.rank, 0)

    @property
    def rank_value(self) -> int:
        return RANK_VALUES[self.rank]

    @property
    def code(self) -> str:
        return f"{self.rank}{self.suit}"

    @property
    def color(self) -> str:
        return "red" if self.suit in {"H", "D"} else "black"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "suit": self.suit,
            "rank": self.rank,
            "hcp": self.hcp,
        }


def card_from_id(card_id: int) -> Card:
    if not 0 <= card_id < 52:
        raise ValueError(f"card id out of range: {card_id}")
    return Card(suit=SUITS[card_id // 13], rank=RANKS[card_id % 13])


def parse_card(text: str) -> Card:
    raw = text.strip().upper().replace("10", "T")
    if len(raw) == 2 and raw[0] in RANKS and raw[1] in SUITS:
        return Card(suit=raw[1], rank=raw[0])
    if len(raw) == 2 and raw[0] in SUITS and raw[1] in RANKS:
        return Card(suit=raw[0], rank=raw[1])
    raise ValueError(f"cannot parse card: {text}")


def full_deck() -> list[Card]:
    return [Card(suit=suit, rank=rank) for suit in SUITS for rank in RANKS]


def sort_hand(cards: Iterable[Card]) -> list[Card]:
    order = {suit: index for index, suit in enumerate(DISPLAY_SUIT_ORDER)}
    return sorted(cards, key=lambda card: (order[card.suit], -card.rank_value))


def hcp_of(cards: Iterable[Card]) -> int:
    return sum(card.hcp for card in cards)


def next_seat(seat: str) -> str:
    return SEATS[(SEATS.index(seat) + 1) % 4]


def left_of(seat: str) -> str:
    return next_seat(seat)


def action_to_label(action: int) -> str:
    """Compact SAN: As, Th, *h, #9, 1H, 1NT, P, X, XX."""
    if 0 <= action < ACTION_PLAY_END:
        card = card_from_id(action)
        return f"{card.rank}{card.suit.lower()}"
    if ACTION_TRUMP_START <= action < ACTION_GOAL_START:
        trump = TRUMPS[action - ACTION_TRUMP_START]
        return f"*{'n' if trump == 'NT' else trump.lower()}"
    if ACTION_GOAL_START <= action < ACTION_BID_START:
        return f"#{GOAL_TRICKS[action - ACTION_GOAL_START]}"
    if ACTION_BID_START <= action < ACTION_PASS:
        level, strain = decode_bid(action)
        return f"{level}{strain}"
    if action == ACTION_PASS:
        return "P"
    if action == ACTION_DOUBLE:
        return "X"
    if action == ACTION_REDOUBLE:
        return "XX"
    raise ValueError(f"action out of range: {action}")


def trump_action(trump: str) -> int:
    return ACTION_TRUMP_START + TRUMPS.index(trump)


def goal_action(goal: int) -> int:
    return ACTION_GOAL_START + GOAL_TRICKS.index(goal)


def bid_action(level: int, strain: str) -> int:
    return ACTION_BID_START + (level - 1) * 5 + BID_STRAINS.index(strain)


def decode_bid(action: int) -> tuple[int, str]:
    if not ACTION_BID_START <= action < ACTION_PASS:
        raise ValueError(f"not a bid action: {action}")
    offset = action - ACTION_BID_START
    return offset // 5 + 1, BID_STRAINS[offset % 5]


def call_rank(action: int) -> int:
    """Sort key for strain bids. Pass/X/XX are not ranked."""
    if ACTION_BID_START <= action < ACTION_PASS:
        return action - ACTION_BID_START
    raise ValueError(f"not a ranked bid: {action}")
