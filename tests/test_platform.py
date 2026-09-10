from engine.puzzles import generate_puzzle
from engine.rating import elo_update
from fastapi.testclient import TestClient

from api.main import app


def test_elo_moves_toward_result():
    up, delta = elo_update(1200, 1200, 1.0)
    assert delta > 0
    assert up == 1200 + delta
    down, loss = elo_update(1200, 1200, 0.0)
    assert loss < 0
    assert down == 1200 + loss


def test_puzzle_generator():
    puzzle = generate_puzzle(kind="trump", seed=3)
    assert puzzle["kind"] == "trump"
    assert "answer" in puzzle
    assert puzzle["hands"]["N"]


def test_platform_me_puzzles_and_history():
    with TestClient(app) as client:
        me = client.get("/api/me")
        assert me.status_code == 200
        assert "rating" in me.json()

        daily = client.get("/api/puzzles/daily")
        assert daily.status_code == 200
        puzzle_id = daily.json()["id"]
        assert "answer" not in daily.json()

        solved = client.post(f"/api/puzzles/{puzzle_id}/solve", json={"action": 52})
        assert solved.status_code == 200
        assert "correct" in solved.json()

        created = client.post("/api/games", json={"seed": 3, "skill": "beginner", "auto_robots": False})
        assert created.status_code == 200
        assert created.json()["skill"] == "beginner"
        game_id = created.json()["id"]

        resigned = client.post(f"/api/games/{game_id}/resign")
        assert resigned.status_code == 200
        assert resigned.json()["phase"] == "deal_over"
        assert resigned.json()["archive"]["id"]

        history = client.get("/api/history")
        assert history.status_code == 200
        assert history.json()["games"]
