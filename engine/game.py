"""Minibridge state machine, legal moves, and gym-style transitions."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Iterable

from engine.auction import (
    auction_complete,
    contract_from_auction,
    dealer_for_deal,
    format_auction,
    legal_calls,
    passed_out,
    side_vulnerable,
    vulnerability_for_deal,
)
from engine.cards import (
    ACTION_DOUBLE,
    ACTION_GOAL_START,
    ACTION_PASS,
    ACTION_PLAY_END,
    ACTION_REDOUBLE,
    ACTION_SPACE,
    ACTION_TRUMP_START,
    EW,
    GOAL_TRICKS,
    NS,
    PARTNERS,
    SEATS,
    SUITS,
    TRUMPS,
    Card,
    action_to_label,
    bid_action,
    card_from_id,
    decode_bid,
    full_deck,
    goal_action,
    hcp_of,
    left_of,
    next_seat,
    parse_card,
    sort_hand,
    trump_action,
)
from engine.notation import format_scoresheet, parse_san, seated_san
from engine.scoring import score_contract, score_duplicate

Phase = str


@dataclass
class Transition:
    observation: dict[str, Any]
    reward: float
    done: bool
    info: dict[str, Any]


@dataclass
class Game:
    """One table: a running score plus the current deal.

    North/South are the learner seats (both hands are visible, matching the
    MiniBridge teaching layout). East/West are robots unless auto_robots is off.
    """

    seed: int | None = None
    auto_robots: bool = True
    agent_seats: tuple[str, ...] = NS
    skill: str = "intermediate"
    rules: str = "minibridge"
    player_kinds: dict[str, str] = field(default_factory=dict)
    llm_model: str = "gpt-4.1-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    rng: random.Random = field(init=False, repr=False)

    deal_number: int = 0
    score: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    opening_hands: dict[str, list[Card]] = field(default_factory=dict)
    archived: bool = False

    phase: Phase = "idle"
    hands: dict[str, list[Card]] = field(default_factory=dict)
    hcp: dict[str, int] = field(default_factory=dict)
    declarer: str | None = None
    dummy: str | None = None
    trump: str | None = None
    goal: int | None = None
    level: int | None = None
    doubled: int = 0
    dealer: str = "N"
    vulnerability: str = "none"
    auction: list[tuple[str, int]] = field(default_factory=list)
    to_act: str = "S"
    current_trick: list[tuple[str, Card]] = field(default_factory=list)
    tricks: list[list[tuple[str, Card]]] = field(default_factory=list)
    last_trick: list[tuple[str, Card]] = field(default_factory=list)
    tricks_ns: int = 0
    tricks_ew: int = 0
    deal_result: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        if not self.player_kinds:
            self.player_kinds = {
                seat: ("human" if seat in self.agent_seats else "engine") for seat in SEATS
            }
        if not self.hands:
            self.reset()

    @staticmethod
    def partner(seat: str) -> str:
        return PARTNERS[seat]

    def reset(self, seed: int | None = None) -> dict[str, Any]:
        if seed is not None:
            self.seed = seed
            self.rng = random.Random(seed)
        self._deal()
        if self.auto_robots:
            self._autoplay_robots()
        return self.observation()

    def new_match(self, seed: int | None = None) -> dict[str, Any]:
        self.score = 0
        self.deal_number = 0
        self.history.clear()
        return self.reset(seed)

    def _deal(self) -> None:
        deck = full_deck()
        self.rng.shuffle(deck)
        self.deal_number += 1
        self.hands = {
            seat: sort_hand(deck[index * 13 : (index + 1) * 13])
            for index, seat in enumerate(SEATS)
        }
        self.hcp = {seat: hcp_of(self.hands[seat]) for seat in SEATS}
        self.dealer = dealer_for_deal(self.deal_number)
        self.vulnerability = vulnerability_for_deal(self.deal_number)
        self.auction = []
        self.level = None
        self.doubled = 0
        self.trump = None
        self.goal = None
        self.current_trick = []
        self.tricks = []
        self.last_trick = []
        self.tricks_ns = 0
        self.tricks_ew = 0
        self.deal_result = None
        self.archived = False
        self.opening_hands = {seat: list(cards) for seat, cards in self.hands.items()}
        if self.rules == "bridge":
            self.declarer = None
            self.dummy = None
            self.to_act = self.dealer
            self.phase = "auction"
        else:
            ns_hcp = self.hcp["N"] + self.hcp["S"]
            ew_hcp = self.hcp["E"] + self.hcp["W"]
            declaring = NS if ns_hcp >= ew_hcp else EW
            a, b = declaring
            if self.hcp[a] > self.hcp[b]:
                self.declarer = a
            elif self.hcp[b] > self.hcp[a]:
                self.declarer = b
            else:
                self.declarer = "S" if declaring is NS else "W"
            self.dummy = self.partner(self.declarer)
            self.to_act = self.declarer
            self.phase = "select_trump"

    def clone(self) -> Game:
        copy = Game.__new__(Game)
        copy.seed = self.seed
        copy.auto_robots = self.auto_robots
        copy.agent_seats = self.agent_seats
        copy.skill = self.skill
        copy.rules = self.rules
        copy.player_kinds = dict(self.player_kinds)
        copy.llm_model = self.llm_model
        copy.llm_base_url = self.llm_base_url
        copy.llm_api_key = self.llm_api_key
        copy.opening_hands = {seat: list(cards) for seat, cards in self.opening_hands.items()}
        copy.archived = self.archived
        copy.rng = random.Random()
        copy.rng.setstate(self.rng.getstate())
        copy.deal_number = self.deal_number
        copy.score = self.score
        copy.history = [dict(item) for item in self.history]
        copy.trajectory = [dict(item) for item in self.trajectory]
        copy.phase = self.phase
        copy.hands = {seat: list(cards) for seat, cards in self.hands.items()}
        copy.hcp = dict(self.hcp)
        copy.declarer = self.declarer
        copy.dummy = self.dummy
        copy.trump = self.trump
        copy.goal = self.goal
        copy.level = self.level
        copy.doubled = self.doubled
        copy.dealer = self.dealer
        copy.vulnerability = self.vulnerability
        copy.auction = list(self.auction)
        copy.to_act = self.to_act
        copy.current_trick = list(self.current_trick)
        copy.tricks = [list(trick) for trick in self.tricks]
        copy.last_trick = list(self.last_trick)
        copy.tricks_ns = self.tricks_ns
        copy.tricks_ew = self.tricks_ew
        copy.deal_result = None if self.deal_result is None else dict(self.deal_result)
        return copy

    def controller(self, seat: str | None = None) -> str:
        """Who actually plays this seat. Dummy is played by declarer."""
        seat = seat or self.to_act
        if self.phase == "play" and self.dummy and seat == self.dummy and self.declarer:
            return self.declarer
        return seat

    def acting_kind(self, seat: str | None = None) -> str:
        if self.phase in {"deal_over", "idle"}:
            return "none"
        return self.player_kinds.get(self.controller(seat), "engine")

    def is_robot(self, seat: str | None = None) -> bool:
        return self.acting_kind(seat) == "engine"

    def configure_players(self, kinds: dict[str, str]) -> None:
        allowed = {"human", "engine", "llm"}
        for seat, kind in kinds.items():
            seat = seat.upper()
            if seat not in SEATS:
                raise ValueError(f"invalid seat: {seat}")
            if kind not in allowed:
                raise ValueError(f"kind must be one of {sorted(allowed)}")
            self.player_kinds[seat] = kind
        humans = tuple(seat for seat, kind in self.player_kinds.items() if kind == "human")
        self.agent_seats = humans or ("S",)

    def legal_actions(self) -> list[int]:
        if self.phase == "auction":
            return legal_calls(self.auction, self.to_act)
        if self.phase == "select_trump":
            return [trump_action(trump) for trump in TRUMPS]
        if self.phase == "select_goal":
            return [goal_action(goal) for goal in GOAL_TRICKS]
        if self.phase == "play":
            return [card.id for card in self.legal_cards(self.to_act)]
        return []

    def dummy_visible(self) -> bool:
        if not self.dummy:
            return False
        if self.rules != "bridge":
            return self.phase in {"select_trump", "select_goal", "play", "deal_over"}
        if self.phase == "deal_over":
            return True
        if self.phase != "play":
            return False
        return bool(self.tricks) or bool(self.current_trick)

    def legal_cards(self, seat: str) -> list[Card]:
        hand = list(self.hands[seat])
        if not self.current_trick:
            return hand
        led = self.current_trick[0][1].suit
        following = [card for card in hand if card.suit == led]
        return following or hand

    def action_mask(self) -> list[int]:
        mask = [0] * ACTION_SPACE
        for action in self.legal_actions():
            mask[action] = 1
        return mask

    def winner_of_plays(self, plays: Iterable[tuple[str, Card]]) -> str:
        plays = list(plays)
        if not plays:
            raise ValueError("empty trick")
        led_suit = plays[0][1].suit
        trump = self.trump
        winning_seat, winning_card = plays[0]
        for seat, card in plays[1:]:
            if self._beats(card, winning_card, led_suit, trump):
                winning_seat, winning_card = seat, card
        return winning_seat

    @staticmethod
    def _beats(card: Card, current: Card, led_suit: str, trump: str | None) -> bool:
        trump_suit = None if trump in (None, "NT") else trump
        card_trump = trump_suit is not None and card.suit == trump_suit
        current_trump = trump_suit is not None and current.suit == trump_suit
        if card_trump and not current_trump:
            return True
        if current_trump and not card_trump:
            return False
        if card.suit != current.suit:
            return False
        if current.suit != led_suit and not current_trump:
            return False
        return card.rank_value > current.rank_value

    def step(self, action: int | str | dict[str, Any]) -> Transition:
        if self.phase in {"idle", "deal_over"}:
            raise ValueError("deal is over; call reset() for a new deal")

        parsed = self._parse_action(action)
        if parsed not in self.legal_actions():
            raise ValueError(
                f"illegal action {action_to_label(parsed) if isinstance(parsed, int) else action} "
                f"in phase {self.phase} for {self.to_act}"
            )

        obs_before = self.observation()
        actor = self.to_act
        self._apply(parsed)

        robot_actions: list[dict[str, Any]] = []
        if self.auto_robots:
            robot_actions = self._autoplay_robots()

        reward = 0.0
        info: dict[str, Any] = {
            "action": parsed,
            "action_label": action_to_label(parsed),
            "actor": actor,
            "robot_actions": robot_actions,
            "phase": self.phase,
        }
        if self.phase == "deal_over" and self.deal_result:
            ns_points = self.deal_result["ns_points"]
            reward = ns_points / 100.0
            info["deal_result"] = self.deal_result
            info["ns_points"] = ns_points

        transition = Transition(
            observation=self.observation(),
            reward=reward,
            done=self.phase == "deal_over",
            info=info,
        )
        self.trajectory.append(
            {
                "observation": obs_before,
                "action": parsed,
                "action_label": action_to_label(parsed),
                "actor": actor,
                "reward": reward,
                "done": transition.done,
                "next_observation": transition.observation,
                "info": {
                    "phase": info["phase"],
                    "robot_actions": robot_actions,
                    "ns_points": info.get("ns_points"),
                },
            }
        )
        return transition

    def _parse_action(self, action: int | str | dict[str, Any]) -> int:
        if isinstance(action, int):
            return action
        if isinstance(action, str):
            text = action.strip()
            parsed = parse_san(text)
            if parsed is not None:
                return parsed
            if text.startswith("play:"):
                return parse_card(text.split(":", 1)[1]).id
            if text.startswith("trump:"):
                return trump_action(text.split(":", 1)[1].upper())
            if text.startswith("goal:"):
                return goal_action(int(text.split(":", 1)[1]))
            raise ValueError(
                f"not SAN: {action!r}. Use As, 1H, 1NT, P, X, *h, #9."
            )
        if isinstance(action, dict):
            if "action" in action and action["action"] is not None:
                return self._parse_action(action["action"])
            kind = action.get("type") or action.get("kind")
            if kind in {"trump", "select_trump"}:
                return trump_action(str(action.get("trump") or action.get("suit")).upper())
            if kind in {"goal", "select_goal"}:
                return goal_action(int(action["goal"]))
            if kind in {"play", "play_card", "card"}:
                card = action.get("card")
                if isinstance(card, int):
                    return card
                return parse_card(str(card)).id
            if kind in {"bid", "call", "auction"}:
                if action.get("level") and action.get("strain"):
                    return bid_action(int(action["level"]), str(action["strain"]).upper())
                call = str(action.get("call") or action.get("bid") or "").strip()
                parsed = parse_san(call)
                if parsed is not None:
                    return parsed
                raise ValueError(f"cannot parse bid: {action!r}")
        raise ValueError(f"cannot parse action: {action!r}")

    def _apply(self, action: int) -> None:
        if self.phase == "auction":
            self.auction.append((self.to_act, action))
            if auction_complete(self.auction):
                if passed_out(self.auction):
                    self._pass_out()
                    return
                info = contract_from_auction(self.auction)
                assert info is not None
                self.declarer = info["declarer"]
                self.dummy = info["dummy"]
                self.trump = info["trump"]
                self.level = info["level"]
                self.goal = info["goal"]
                self.doubled = info["doubled"]
                self.phase = "play"
                self.to_act = left_of(self.declarer)
                return
            self.to_act = next_seat(self.to_act)
            return
        if self.phase == "select_trump":
            self.trump = TRUMPS[action - ACTION_TRUMP_START]
            self.phase = "select_goal"
            self.to_act = self.declarer or "S"
            return
        if self.phase == "select_goal":
            self.goal = GOAL_TRICKS[action - ACTION_GOAL_START]
            self.phase = "play"
            self.to_act = left_of(self.declarer or "S")
            return
        if self.phase == "play":
            card = card_from_id(action)
            hand = self.hands[self.to_act]
            for index, owned in enumerate(hand):
                if owned.id == card.id:
                    hand.pop(index)
                    break
            else:
                raise ValueError(f"{self.to_act} does not hold {card.code}")
            self.current_trick.append((self.to_act, card))
            if len(self.current_trick) < 4:
                self.to_act = next_seat(self.to_act)
                return
            winner = self.winner_of_plays(self.current_trick)
            self.tricks.append(list(self.current_trick))
            self.last_trick = list(self.current_trick)
            self.current_trick = []
            if winner in NS:
                self.tricks_ns += 1
            else:
                self.tricks_ew += 1
            if self.tricks_ns + self.tricks_ew == 13:
                self._finish_deal()
            else:
                self.to_act = winner
            return
        raise RuntimeError(f"cannot apply action in phase {self.phase}")

    def _pass_out(self) -> None:
        self.deal_result = {
            "made": False,
            "passed_out": True,
            "tricks": 0,
            "goal": 0,
            "trump": None,
            "trick_points": 0,
            "bonus": 0,
            "points": 0,
            "deal": self.deal_number,
            "declarer": None,
            "dummy": None,
            "declaring_side": None,
            "tricks_ns": 0,
            "tricks_ew": 0,
            "ns_points": 0,
            "match_score": self.score,
            "contract": "Pass",
            "dealer": self.dealer,
            "vulnerability": self.vulnerability,
        }
        self.history.append(dict(self.deal_result))
        self.phase = "deal_over"
        self.to_act = self.dealer

    def _finish_deal(self) -> None:
        assert self.trump is not None and self.goal is not None and self.declarer is not None
        declaring_ns = self.declarer in NS
        declaring_tricks = self.tricks_ns if declaring_ns else self.tricks_ew
        if self.rules == "bridge":
            vul = side_vulnerable(self.vulnerability, self.declarer)
            scored = score_duplicate(
                self.trump,
                self.level or (self.goal - 6),
                declaring_tricks,
                vul,
                self.doubled,
            )
        else:
            scored = score_contract(self.trump, self.goal, declaring_tricks)
        ns_points = scored["points"] if declaring_ns else -scored["points"]
        self.score += ns_points
        self.deal_result = {
            **scored,
            "deal": self.deal_number,
            "declarer": self.declarer,
            "dummy": self.dummy,
            "declaring_side": "NS" if declaring_ns else "EW",
            "tricks_ns": self.tricks_ns,
            "tricks_ew": self.tricks_ew,
            "ns_points": ns_points,
            "match_score": self.score,
            "contract": self.contract_label(),
            "dealer": self.dealer,
            "vulnerability": self.vulnerability,
            "auction": [
                {"seat": seat, "call": action_to_label(action)} for seat, action in self.auction
            ],
        }
        self.history.append(dict(self.deal_result))
        self.phase = "deal_over"
        self.to_act = self.declarer

    def _autoplay_robots(self) -> list[dict[str, Any]]:
        from engine.robots import choose_action

        played: list[dict[str, Any]] = []
        guard = 0
        while self.phase not in {"deal_over", "idle"} and self.is_robot(self.to_act):
            action = choose_action(self, self.skill)
            actor = self.to_act
            self._apply(action)
            played.append(
                {
                    "actor": actor,
                    "action": action,
                    "action_label": action_to_label(action),
                }
            )
            guard += 1
            if guard > 250:
                raise RuntimeError("robot autoplay did not terminate")
        return played

    def visible_hands(self, viewer: str | None = None) -> dict[str, list[dict[str, Any]] | None]:
        """NS always see each other. Dummy is public after the deal starts."""
        visible = set(self.agent_seats)
        if viewer:
            visible.add(viewer)
        if self.dummy_visible():
            visible.add(self.dummy)
        if self.phase == "deal_over":
            visible.update(SEATS)
        out: dict[str, list[dict[str, Any]] | None] = {}
        for seat in SEATS:
            if seat in visible:
                out[seat] = [card.to_dict() for card in sort_hand(self.hands[seat])]
            else:
                out[seat] = None
        return out

    def public_state(self) -> dict[str, Any]:
        return {
            "deal_number": self.deal_number,
            "score": self.score,
            "phase": self.phase,
            "to_act": self.to_act,
            "declarer": self.declarer,
            "dummy": self.dummy,
            "rules": self.rules,
            "trump": self.trump,
            "goal": self.goal,
            "level": self.level,
            "doubled": self.doubled,
            "dealer": self.dealer,
            "vulnerability": self.vulnerability,
            "auction": [
                {"seat": seat, "call": action_to_label(action), "action": action}
                for seat, action in self.auction
            ],
            "dummy_visible": self.dummy_visible(),
            "contract": self.contract_label(),
            "skill": self.skill,
            "move_list": self.move_list(),
            "controller": None if self.phase == "deal_over" else self.controller(),
            "human_seat": next(
                (seat for seat, kind in self.player_kinds.items() if kind == "human"),
                self.agent_seats[0] if self.agent_seats else "S",
            ),
            "player_kinds": dict(self.player_kinds),
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "waiting_for": None
            if self.phase in {"deal_over", "idle"}
            else {
                "seat": self.to_act,
                "controller": self.controller(),
                "kind": self.acting_kind(),
            },
            "hcp": dict(self.hcp),
            "hcp_ns": self.hcp.get("N", 0) + self.hcp.get("S", 0),
            "hcp_ew": self.hcp.get("E", 0) + self.hcp.get("W", 0),
            "tricks_ns": self.tricks_ns,
            "tricks_ew": self.tricks_ew,
            "current_trick": [
                {"seat": seat, "card": card.to_dict()} for seat, card in self.current_trick
            ],
            "last_trick": [
                {"seat": seat, "card": card.to_dict()} for seat, card in self.last_trick
            ],
            "tricks_played": len(self.tricks),
            "deal_result": self.deal_result,
            "auto_robots": self.auto_robots,
            "agent_seats": list(self.agent_seats),
            "legal_actions": self.legal_actions(),
            "legal_action_labels": [action_to_label(action) for action in self.legal_actions()],
            "scoresheet": self.scoresheet(),
            "action_mask": self.action_mask(),
            "action_space": ACTION_SPACE,
        }

    def observation_vector(self) -> list[float]:
        """Fixed-length vector for supervised / RL agents.

        Layout (length 335):
          0-51     South cards
          52-103   North cards
          104-155  dummy cards (zeros if dummy is N/S already encoded)
          156-207  cards already played
          208-259  cards in the current trick
          260-264  trump one-hot C D H S NT
          265-272  goal one-hot (none + 7..13)
          273-276  to_act N E S W
          277-280  phase one-hot
          281-282  tricks_ns, tricks_ew / 13
          283-286  HCP N E S W / 40
          287-290  hand lengths / 13
          291-334  4 x 11 current-trick seat/card extras reserved as zeros
        """
        vec = [0.0] * 335

        def mark_cards(offset: int, cards: Iterable[Card]) -> None:
            for card in cards:
                vec[offset + card.id] = 1.0

        mark_cards(0, self.hands.get("S", []))
        mark_cards(52, self.hands.get("N", []))
        if self.dummy and self.dummy not in NS:
            mark_cards(104, self.hands.get(self.dummy, []))

        played = [card for trick in self.tricks for _, card in trick]
        played.extend(card for _, card in self.current_trick)
        mark_cards(156, played)
        mark_cards(208, (card for _, card in self.current_trick))

        if self.trump:
            vec[260 + TRUMPS.index(self.trump)] = 1.0
        if self.goal is None:
            vec[265] = 1.0
        else:
            vec[266 + (self.goal - 7)] = 1.0

        vec[273 + SEATS.index(self.to_act)] = 1.0
        phase_index = {
            "auction": 0,
            "select_trump": 0,
            "select_goal": 1,
            "play": 2,
            "deal_over": 3,
        }.get(self.phase, 0)
        vec[277 + phase_index] = 1.0
        vec[281] = self.tricks_ns / 13.0
        vec[282] = self.tricks_ew / 13.0
        for index, seat in enumerate(SEATS):
            vec[283 + index] = self.hcp.get(seat, 0) / 40.0
            vec[287 + index] = len(self.hands.get(seat, [])) / 13.0
        return vec

    def contract_label(self) -> str | None:
        if self.trump is None or self.goal is None:
            return None
        if self.rules == "bridge" and self.level:
            label = f"{self.level}{self.trump}"
            if self.doubled == 1:
                label += "X"
            elif self.doubled == 2:
                label += "XX"
            return label
        return f"{self.goal}{self.trump}"

    def scoresheet(self) -> str:
        contract = (self.trump, self.goal) if self.trump and self.goal else None
        heading = None
        auction_text = None
        if self.rules == "bridge":
            heading = f"{self.dealer} deal  {self.vulnerability} vul"
            if self.auction:
                auction_text = format_auction(self.auction, self.dealer)
        return format_scoresheet(
            self.tricks,
            contract,
            self.current_trick,
            auction_text=auction_text,
            heading=heading,
        )

    def move_list(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if self.trump and self.goal:
            strain = "n" if self.trump == "NT" else self.trump.lower()
            rows.append(
                {
                    "kind": "contract",
                    "text": f"*{strain} #{self.goal}",
                    "san": f"*{strain} #{self.goal}",
                }
            )
        for index, trick in enumerate(self.tricks, 1):
            winner = self.winner_of_plays(trick)
            text = f"{index}. " + " ".join(
                seated_san(seat, card.id) for seat, card in trick
            )
            rows.append(
                {
                    "kind": "trick",
                    "n": index,
                    "winner": winner,
                    "plays": [
                        {
                            "seat": seat,
                            "card": card.to_dict(),
                            "san": seated_san(seat, card.id),
                        }
                        for seat, card in trick
                    ],
                    "text": text,
                }
            )
        if self.current_trick:
            n = len(self.tricks) + 1
            text = f"{n}. " + " ".join(
                seated_san(seat, card.id) for seat, card in self.current_trick
            )
            rows.append(
                {
                    "kind": "partial",
                    "n": n,
                    "plays": [
                        {
                            "seat": seat,
                            "card": card.to_dict(),
                            "san": seated_san(seat, card.id),
                        }
                        for seat, card in self.current_trick
                    ],
                    "text": text,
                }
            )
        return rows

    def resign(self) -> dict[str, Any]:
        if self.phase not in {"play", "select_trump", "select_goal", "auction"}:
            raise ValueError("nothing to resign")
        if self.phase == "auction":
            while not auction_complete(self.auction):
                self.auction.append((self.to_act, ACTION_PASS))
                self.to_act = next_seat(self.to_act)
            if passed_out(self.auction):
                self._pass_out()
                return self.observation()
            info = contract_from_auction(self.auction)
            if info:
                self.declarer = info["declarer"]
                self.dummy = info["dummy"]
                self.trump = info["trump"]
                self.level = info["level"]
                self.goal = info["goal"]
                self.doubled = info["doubled"]
        if self.trump is None:
            self.trump = "NT"
        if self.goal is None:
            self.goal = 9
        self.current_trick = []
        self._finish_deal()
        if self.deal_result:
            self.deal_result["resigned"] = True
        return self.observation()

    def archive_record(self) -> dict[str, Any] | None:
        if not self.deal_result:
            return None
        declaring_ns = self.declarer in NS
        made = bool(self.deal_result.get("made"))
        won = made if declaring_ns else not made
        return {
            "seed": self.seed,
            "skill": self.skill,
            "opening_hands": {
                seat: [card.to_dict() for card in cards]
                for seat, cards in self.opening_hands.items()
            },
            "hcp": dict(self.hcp),
            "tricks": [
                [{"seat": seat, "card": card.to_dict()} for seat, card in trick]
                for trick in self.tricks
            ],
            "move_list": self.move_list(),
            "result": "win" if won else "loss",
            "won": won,
            **self.deal_result,
        }

    def observation(self) -> dict[str, Any]:
        state = self.public_state()
        state["hands"] = self.visible_hands()
        state["hand_counts"] = {seat: len(self.hands.get(seat, [])) for seat in SEATS}
        state["obs_vector"] = self.observation_vector()
        from engine.textio import observation_text

        state["text"] = observation_text(self)
        return state

    def table_state(self) -> dict[str, Any]:
        """Richer payload used by the browser table."""
        state = self.observation()
        state["hands_full"] = {
            seat: [card.to_dict() for card in sort_hand(self.hands[seat])] for seat in SEATS
        }
        state["history"] = list(self.history)
        human = self.agent_seats[0] if self.agent_seats else "S"
        partner = self.partner(human)
        state["seats"] = [
            {
                "seat": seat,
                "label": (
                    "You"
                    if seat in self.agent_seats
                    else "Partner"
                    if seat == partner
                    else "Robot"
                ),
                "hcp": self.hcp.get(seat, 0),
                "is_declarer": seat == self.declarer,
                "is_dummy": seat == self.dummy,
                "to_act": seat == self.to_act and self.phase != "deal_over",
                "count": len(self.hands.get(seat, [])),
                "kind": self.player_kinds.get(seat, "engine"),
            }
            for seat in SEATS
        ]
        return state
