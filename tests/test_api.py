from fastapi.testclient import TestClient

from api.main import app


def test_health_and_table_flow():
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["ok"] is True

        table = client.get("/api/games/table")
        assert table.status_code == 200
        body = table.json()
        assert body["id"] == "table"
        assert "obs_vector" in body
        assert len(body["action_mask"]) == 102

        created = client.post("/api/games", json={"seed": 11, "auto_robots": False})
        assert created.status_code == 200
        game_id = created.json()["id"]
        assert created.json()["phase"] == "select_trump"

        stepped = client.post(f"/api/games/{game_id}/step", json={"action": "*n"})
        assert stepped.status_code == 200
        assert stepped.json()["trump"] == "NT"
        assert stepped.json()["phase"] == "select_goal"

        goal = client.post(f"/api/games/{game_id}/step", json={"action": "#9"})
        assert goal.status_code == 200
        assert goal.json()["goal"] == 9
        assert goal.json()["phase"] == "play"
        assert goal.json()["scoresheet"].startswith("*n #9")

        legal = client.get(f"/api/games/{game_id}/legal-actions")
        assert legal.status_code == 200
        assert legal.json()["actions"]

        obs = client.get(f"/api/games/{game_id}/observation")
        assert obs.status_code == 200
        assert len(obs.json()["obs_vector"]) == 335


def test_illegal_move_is_rejected():
    with TestClient(app) as client:
        created = client.post("/api/games", json={"seed": 2, "auto_robots": False})
        game_id = created.json()["id"]
        bad = client.post(f"/api/games/{game_id}/step", json={"action": 0})
        assert bad.status_code == 400
