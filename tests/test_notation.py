from engine.cards import action_to_label, goal_action, parse_card, trump_action
from engine.game import Game
from engine.notation import card_san, format_scoresheet, parse_san, seated_san


def test_card_san_is_rank_plus_lowercase_suit():
    assert card_san(parse_card("AS")) == "As"
    assert card_san(parse_card("TH")) == "Th"
    assert card_san(parse_card("2C")) == "2c"
    assert action_to_label(parse_card("KD").id) == "Kd"
    assert action_to_label(trump_action("H")) == "*h"
    assert action_to_label(trump_action("NT")) == "*n"
    assert action_to_label(goal_action(9)) == "#9"


def test_parse_san_cards_and_seats():
    ace = parse_card("AS").id
    ten = parse_card("TH").id
    three = parse_card("3S").id
    assert parse_san("As") == ace
    assert parse_san("AS") == ace
    assert parse_san("NAs") == ace
    assert parse_san("nAs") == ace
    assert parse_san("W3s") == three
    assert parse_san("Th") == ten
    assert parse_san("10h") == ten
    assert parse_san("play:AS") == ace
    assert parse_san("SQh") == parse_card("QH").id
    assert seated_san("N", ace) == "NAs"


def test_parse_san_contract():
    assert parse_san("*h") == trump_action("H")
    assert parse_san("*n") == trump_action("NT")
    assert parse_san("#9") == goal_action(9)
    assert parse_san("S#10") == goal_action(10)
    assert parse_san("W*s") == trump_action("S")
    assert parse_san("NT") is None
    assert parse_san("9") is None
    assert parse_san("hearts") is None
    assert parse_san("play ace of speeds") is None
    assert parse_san("play ace of spades") is None
    assert parse_san("S9") is None


def test_game_steps_compact_san():
    game = Game(seed=3, auto_robots=False, agent_seats=("S",))
    assert game.phase == "select_trump"
    game.step("*h")
    assert game.trump == "H"
    game.step("#9")
    assert game.goal == 9
    assert game.phase == "play"
    labels = [action_to_label(action) for action in game.legal_actions()]
    assert all(not label.startswith("play:") for label in labels)
    first = game.legal_actions()[0]
    game.step(action_to_label(first))
    assert game.current_trick or game.tricks
    sheet = game.scoresheet()
    assert sheet.startswith("*h #9")
    assert "1." in sheet


def test_scoresheet_reads_like_chess():
    trick = [
        ("W", parse_card("3S")),
        ("N", parse_card("AS")),
        ("E", parse_card("6S")),
        ("S", parse_card("QH")),
    ]
    sheet = format_scoresheet([trick], ("H", 9))
    assert sheet.splitlines() == ["*h #9", " 1. W3s NAs E6s SQh"]
