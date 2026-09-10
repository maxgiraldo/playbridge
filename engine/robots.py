"""Rule-based robots with chess.com-style computer strengths."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from engine.cards import TRUMPS, Card, goal_action, hcp_of, left_of, trump_action
from engine.dds import engine_card, estimate_ns_tricks

if TYPE_CHECKING:
    from engine.game import Game

SKILLS = ("beginner", "intermediate", "advanced", "master")


def choose_trump(game: Game) -> int:
    declarer = game.declarer
    if declarer is None:
        raise RuntimeError("no declarer")
    partner = game.partner(declarer)
    combined = list(game.hands[declarer]) + list(game.hands[partner])
    lengths = Counter(card.suit for card in combined)
    hcp = hcp_of(combined)

    best_suit = max(TRUMPS[:-1], key=lambda suit: (lengths[suit], suit in {"S", "H"}))
    balanced = max(lengths.values()) <= 8 and min(lengths.values()) >= 2
    if balanced and hcp >= 25 and lengths[best_suit] <= 8:
        return trump_action("NT")
    return trump_action(best_suit)


def choose_goal(game: Game) -> int:
    declarer = game.declarer
    if declarer is None or game.trump is None:
        raise RuntimeError("contract strain is not set")
    partner = game.partner(declarer)
    combined = list(game.hands[declarer]) + list(game.hands[partner])
    hcp = hcp_of(combined)
    trump_len = 0 if game.trump == "NT" else sum(1 for card in combined if card.suit == game.trump)

    tricks = 6 + max(0, hcp - 12) // 3
    if trump_len >= 8:
        tricks += 1
    if trump_len >= 9:
        tricks += 1
    if trump_len >= 10:
        tricks += 1
    probe = game.clone()
    probe.auto_robots = False
    probe.goal = 7
    probe.phase = "play"
    probe.to_act = left_of(probe.declarer or "S")
    if sum(len(cards) for cards in probe.hands.values()) <= 24:
        tricks = estimate_ns_tricks(probe)
        if probe.declarer not in {"N", "S"}:
            tricks = 13 - tricks
    return goal_action(min(13, max(7, tricks)))


def _trick_winner_if(game: Game, extra: Card) -> str:
    return game.winner_of_plays(list(game.current_trick) + [(game.to_act, extra)])


def choose_card(game: Game) -> int:
    seat = game.to_act
    legal = game.legal_cards(seat)
    if not legal:
        raise RuntimeError(f"no legal cards for {seat}")
    if not game.current_trick:
        return _lead(legal, game.trump).id

    partner = game.partner(seat)
    partner_winning = game.winner_of_plays(game.current_trick) == partner
    following = [card for card in legal if card.suit == game.current_trick[0][1].suit]

    def can_win(card: Card) -> bool:
        return _trick_winner_if(game, card) == seat

    if following:
        winners = [card for card in following if can_win(card)]
        if partner_winning:
            return min(following, key=lambda card: card.rank_value).id
        if winners:
            return min(winners, key=lambda card: (card.rank_value, card.suit)).id
        return min(following, key=lambda card: card.rank_value).id

    trumps = [card for card in legal if game.trump not in (None, "NT") and card.suit == game.trump]
    if trumps and not partner_winning:
        winners = [card for card in trumps if can_win(card)]
        if winners:
            return min(winners, key=lambda card: card.rank_value).id
    return min(legal, key=lambda card: (card.hcp, card.rank_value)).id


def _lead(legal: list[Card], trump: str | None) -> Card:
    non_trump = [card for card in legal if trump in (None, "NT") or card.suit != trump]
    pool = non_trump or legal
    lengths = Counter(card.suit for card in pool)
    suit = max(lengths, key=lambda item: (lengths[item], item in {"S", "H"}))
    in_suit = [card for card in pool if card.suit == suit]
    return min(in_suit, key=lambda card: card.rank_value)


def choose_card_master(game: Game) -> int:
    """Same ideas as choose_card, but prefer establishing winners on lead."""
    if game.current_trick:
        return choose_card(game)
    legal = game.legal_cards(game.to_act)
    non_trump = [card for card in legal if game.trump in (None, "NT") or card.suit != game.trump]
    pool = non_trump or legal
    lengths = Counter(card.suit for card in pool)
    suit = max(lengths, key=lambda item: (lengths[item], item in {"S", "H"}))
    in_suit = [card for card in pool if card.suit == suit]
    honors = [card for card in in_suit if card.rank in {"A", "K", "Q"}]
    if honors and lengths[suit] >= 4:
        return max(honors, key=lambda card: card.rank_value).id
    return min(in_suit, key=lambda card: card.rank_value).id


def choose_action(game: Game, skill: str | None = None) -> int:
    skill = skill or getattr(game, "skill", "intermediate")
    if game.phase == "auction":
        from engine.bidding import choose_call

        if skill == "beginner" and game.rng.random() < 0.25:
            return game.rng.choice(game.legal_actions())
        call = choose_call(game)
        legal = game.legal_actions()
        return call if call in legal else legal[0]
    if game.phase == "select_trump":
        if skill == "beginner" and game.rng.random() < 0.45:
            return game.rng.choice(game.legal_actions())
        return choose_trump(game)
    if game.phase == "select_goal":
        action = choose_goal(game)
        if skill == "beginner" and game.rng.random() < 0.4:
            return game.rng.choice(game.legal_actions())
        return action
    if game.phase == "play":
        if skill == "beginner" and game.rng.random() < 0.5:
            return game.rng.choice(game.legal_actions())
        if skill != "beginner" and getattr(game, "dummy_visible", lambda: True)():
            solved = engine_card(game)
            if solved is not None:
                return solved
        if skill == "master":
            return choose_card_master(game)
        return choose_card(game)
    raise RuntimeError(f"robot has no action in phase {game.phase}")
