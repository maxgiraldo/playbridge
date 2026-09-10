from engine.cards import Card, card_from_id, parse_card, trump_action, goal_action
from engine.game import Game
from engine.scoring import score_contract


def test_card_ids_round_trip():
    for card_id in range(52):
        assert card_from_id(card_id).id == card_id
    assert parse_card("AS").code == "AS"
    assert parse_card("10H").code == "TH"


def test_scoring_bonuses_match_table_prompt():
    made_game = score_contract("S", 9, 10)
    assert made_game["made"] is True
    assert made_game["trick_points"] == 300
    assert made_game["bonus"] == 100
    assert made_game["points"] == 400

    slam = score_contract("NT", 12, 12)
    assert slam["bonus"] == 500
    assert slam["points"] == 12 * 40 + 500

    grand = score_contract("H", 13, 13)
    assert grand["bonus"] == 1000

    down = score_contract("C", 11, 9)
    assert down["made"] is False
    assert down["points"] == -40


def test_must_follow_suit():
    game = Game(seed=1, auto_robots=False)
    game.phase = "play"
    game.trump = "S"
    game.goal = 9
    game.declarer = "S"
    game.dummy = "N"
    game.to_act = "S"
    game.hands["S"] = [parse_card("AS"), parse_card("2H"), parse_card("3C")]
    game.current_trick = [("W", parse_card("KS"))]
    legal = {card.code for card in game.legal_cards("S")}
    assert legal == {"AS"}


def test_trump_beats_led_suit():
    game = Game(seed=1, auto_robots=False)
    game.trump = "S"
    winner = game.winner_of_plays(
        [
            ("W", parse_card("AH")),
            ("N", parse_card("2S")),
            ("E", parse_card("KH")),
            ("S", parse_card("3H")),
        ]
    )
    assert winner == "N"


def test_full_auto_deal_completes():
    game = Game(seed=7, auto_robots=True, agent_seats=("N", "S"))
    steps = 0
    while game.phase != "deal_over" and steps < 80:
        action = game.legal_actions()[0]
        game.step(action)
        steps += 1
    assert game.phase == "deal_over"
    assert game.tricks_ns + game.tricks_ew == 13
    assert game.deal_result is not None
    assert game.history


def test_named_actions_and_clone():
    game = Game(seed=3, auto_robots=False)
    if game.phase == "select_trump":
        game.step({"type": "trump", "trump": "H"})
    if game.phase == "select_goal":
        game.step("goal:9")
    clone = game.clone()
    assert clone.trump == game.trump
    assert clone.goal == game.goal
    assert clone.hands["S"] is not game.hands["S"]


def test_action_helpers():
    assert trump_action("NT") == 56
    assert goal_action(7) == 57
    assert Card("S", "A").id == 51


def test_dummy_is_played_by_declarer():
    game = Game(seed=3, auto_robots=False, agent_seats=("S",))
    game.phase = "play"
    game.declarer = "S"
    game.dummy = "N"
    game.to_act = "N"
    assert game.controller() == "S"
    assert game.is_robot() is False
    game.declarer = "N"
    game.dummy = "S"
    game.to_act = "S"
    assert game.controller() == "N"
    assert game.is_robot() is True


def test_dds_picks_the_winning_card():
    from engine.dds import engine_card, ns_tricks_from

    game = Game(seed=1, auto_robots=False, agent_seats=("S",))
    game.phase = "play"
    game.trump = "NT"
    game.goal = 7
    game.declarer = "S"
    game.dummy = "N"
    game.to_act = "S"
    game.tricks_ns = 0
    game.tricks_ew = 0
    game.current_trick = []
    game.hands = {
        "S": [parse_card("AS"), parse_card("2D")],
        "N": [parse_card("3D"), parse_card("4D")],
        "E": [parse_card("5D"), parse_card("6D")],
        "W": [parse_card("AD"), parse_card("7D")],
    }
    assert ns_tricks_from(game) == 1
    assert engine_card(game) == parse_card("AS").id
