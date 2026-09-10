import pytest

from engine.cards import action_to_label, goal_action, parse_card, trump_action
from engine.game import Game
from engine.textio import observation_text, parse_action_text, prompt_payload


def test_parse_text_is_san_only():
    assert parse_action_text("NAs") == parse_card("AS").id
    assert parse_action_text("As") == parse_card("AS").id
    assert parse_action_text("play:AS") == parse_card("AS").id
    assert parse_action_text("PLAY 10H") == parse_card("TH").id
    assert parse_action_text("*h") == trump_action("H")
    assert parse_action_text("#9") == goal_action(9)


def test_english_is_rejected():
    for phrase in (
        "play ace of spades",
        "play ace of speeds",
        "trump hearts",
        "hearts",
        "NT",
        "goal 9",
        "9",
        "choose hearts",
    ):
        with pytest.raises(ValueError, match="not SAN"):
            parse_action_text(phrase)


def test_game_rejects_english_and_accepts_san():
    game = Game(seed=3, auto_robots=False, agent_seats=("S",))
    with pytest.raises(ValueError, match="not SAN"):
        game.step("hearts")
    game.step("*h")
    assert game.trump == "H"
    with pytest.raises(ValueError, match="not SAN"):
        game.step("goal 9")
    game.step("#9")
    assert game.goal == 9


def test_text_observation_lists_legal_moves():
    game = Game(seed=3, auto_robots=False, agent_seats=("S",))
    text = observation_text(game)
    assert "Legal" in text
    assert "*h" in text
    prompt = prompt_payload(game)
    assert "English is illegal" in prompt["system"]
    assert "As" in prompt["system"]
    assert all(label.startswith("*") for label in prompt["legal_action_labels"])
    assert action_to_label(game.legal_actions()[0]) in prompt["legal_action_labels"]
