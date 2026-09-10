from engine.auction import (
    auction_complete,
    contract_from_auction,
    legal_calls,
    passed_out,
)
from engine.cards import ACTION_DOUBLE, ACTION_PASS, action_to_label, bid_action, parse_card
from engine.game import Game
from engine.notation import parse_san
from engine.scoring import score_duplicate


def test_duplicate_scores():
    assert score_duplicate("NT", 1, 7)["points"] == 90
    assert score_duplicate("H", 2, 8)["points"] == 110
    assert score_duplicate("NT", 3, 9)["points"] == 400
    assert score_duplicate("NT", 3, 10)["points"] == 430
    assert score_duplicate("S", 4, 10, vulnerable=True)["points"] == 620
    assert score_duplicate("H", 6, 12)["points"] == 980
    assert score_duplicate("NT", 7, 13, vulnerable=True)["points"] == 2220
    assert score_duplicate("H", 4, 9)["points"] == -50
    assert score_duplicate("H", 4, 10, doubled=1)["points"] == 590
    assert score_duplicate("NT", 1, 5, doubled=1)["points"] == -300


def test_bid_tokens_are_not_cards():
    assert parse_san("4H") == bid_action(4, "H")
    assert parse_san("4h") == parse_card("4H").id
    assert parse_san("1NT") == bid_action(1, "NT")
    assert parse_san("P") == ACTION_PASS
    assert parse_san("X") == ACTION_DOUBLE
    assert parse_san("N1S") == bid_action(1, "S")
    assert parse_san("EP") == ACTION_PASS
    assert action_to_label(bid_action(3, "NT")) == "3NT"


def test_auction_ends_after_three_passes():
    auction = [
        ("N", bid_action(1, "S")),
        ("E", ACTION_PASS),
        ("S", bid_action(2, "H")),
        ("W", ACTION_PASS),
        ("N", bid_action(4, "H")),
        ("E", ACTION_PASS),
        ("S", ACTION_PASS),
        ("W", ACTION_PASS),
    ]
    assert auction_complete(auction)
    info = contract_from_auction(auction)
    assert info["level"] == 4
    assert info["strain"] == "H"
    assert info["declarer"] == "S"
    assert info["dummy"] == "N"
    assert info["goal"] == 10


def test_four_passes_is_passed_out():
    auction = [(seat, ACTION_PASS) for seat in ("N", "E", "S", "W")]
    assert passed_out(auction)
    assert auction_complete(auction)
    assert contract_from_auction(auction) is None


def test_double_only_of_opponents_bid():
    auction = [("N", bid_action(1, "H"))]
    legal_e = set(legal_calls(auction, "E"))
    legal_s = set(legal_calls(auction, "S"))
    assert ACTION_DOUBLE in legal_e
    assert ACTION_DOUBLE not in legal_s


def _first_bid(game: Game) -> int:
    return next((action for action in game.legal_actions() if action != ACTION_PASS), ACTION_PASS)


def test_contract_deal_plays_out():
    game = Game(seed=3, auto_robots=False, agent_seats=("S",), rules="bridge")
    assert game.phase == "auction"
    assert game.dealer == "N"
    game.step(_first_bid(game))
    while game.phase == "auction":
        game.step(ACTION_PASS)
    assert game.phase == "play"
    assert game.goal == game.level + 6
    assert not game.dummy_visible()
    game.step(game.legal_actions()[0])
    assert game.dummy_visible()
    steps = 0
    while game.phase != "deal_over" and steps < 60:
        game.step(game.legal_actions()[0])
        steps += 1
    assert game.phase == "deal_over"
    assert game.tricks_ns + game.tricks_ew == 13


def test_engine_can_finish_a_bridge_deal():
    game = Game(seed=11, auto_robots=True, agent_seats=("S",), rules="bridge")
    steps = 0
    while game.phase != "deal_over" and steps < 120:
        action = _first_bid(game) if game.phase == "auction" else game.legal_actions()[0]
        game.step(action)
        steps += 1
    assert game.phase == "deal_over"
    if not game.deal_result.get("passed_out"):
        assert game.tricks_ns + game.tricks_ew == 13
        assert game.deal_result["contract"]
