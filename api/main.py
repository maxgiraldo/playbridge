"""PlayBridge: chess.com-style MiniBridge platform plus a gym learning API."""

from __future__ import annotations

import secrets
import uuid
from pathlib import Path
from typing import Any

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.llm import complete_action, llm_ready
from api.store import platform
from engine.cards import ACTION_SPACE, SEATS, action_to_label
from engine.game import Game
from engine.rating import COMPUTER_RATINGS
from engine.robots import SKILLS
from engine.textio import prompt_payload

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
GAMES: dict[str, Game] = {}
DEFAULT_ID = "table"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if DEFAULT_ID not in GAMES:
        GAMES[DEFAULT_ID] = Game(
            seed=secrets.randbelow(1_000_000),
            skill="intermediate",
            agent_seats=("S",),
            rules="bridge",
        )
    yield


app = FastAPI(
    title="PlayBridge API",
    description=(
        "Play MiniBridge like a chess site: rated games, puzzles, and review. "
        "Agents can also train through the gym-style move API."
    ),
    version="2.0.0",
    lifespan=lifespan,
)


class NewGameRequest(BaseModel):
    seed: int | None = None
    auto_robots: bool = True
    agent_seats: list[str] = Field(default_factory=lambda: ["S"])
    reset_match: bool = True
    skill: str = "intermediate"
    player_kinds: dict[str, str] | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    rules: str | None = None


class StepRequest(BaseModel):
    action: int | str | None = None
    type: str | None = None
    card: int | str | None = None
    trump: str | None = None
    goal: int | None = None
    call: str | None = None
    bid: str | None = None
    level: int | None = None
    strain: str | None = None


class ResetRequest(BaseModel):
    seed: int | None = None
    new_match: bool = False
    skill: str | None = None
    rules: str | None = None


class PuzzleSolveRequest(BaseModel):
    action: int


class ConfigRequest(BaseModel):
    player_kinds: dict[str, str] | None = None
    partner: str | None = None
    opponents: str | None = None
    south: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    skill: str | None = None
    rules: str | None = None


def _game(game_id: str) -> Game:
    game = GAMES.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail=f"unknown game id: {game_id}")
    return game


def _validate_seats(seats: list[str]) -> tuple[str, ...]:
    cleaned = tuple(seat.upper() for seat in seats)
    for seat in cleaned:
        if seat not in SEATS:
            raise HTTPException(status_code=400, detail=f"invalid seat: {seat}")
    if not cleaned:
        raise HTTPException(status_code=400, detail="agent_seats cannot be empty")
    return cleaned


def _validate_skill(skill: str) -> str:
    if skill not in SKILLS:
        raise HTTPException(status_code=400, detail=f"skill must be one of {list(SKILLS)}")
    return skill


def _maybe_archive(game: Game, extra: dict[str, Any]) -> None:
    if game.phase != "deal_over" or game.archived:
        return
    record = game.archive_record()
    if not record:
        return
    archived = platform.archive_deal(record)
    game.archived = True
    extra["archive"] = archived
    extra["profile"] = platform.me()


def _payload(game_id: str, game: Game, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    body = {"id": game_id, **game.table_state(), "profile": platform.me()}
    if extra:
        body.update(extra)
    return body


def _apply_bot_config(game: Game, body: NewGameRequest | ConfigRequest) -> None:
    kinds = dict(body.player_kinds or {})
    if getattr(body, "south", None):
        kinds["S"] = body.south
    if getattr(body, "partner", None):
        kinds["N"] = body.partner
    if getattr(body, "opponents", None):
        kinds["E"] = body.opponents
        kinds["W"] = body.opponents
    if kinds:
        game.configure_players(kinds)
    if body.llm_model:
        game.llm_model = body.llm_model
    if body.llm_base_url:
        game.llm_base_url = body.llm_base_url
    if body.llm_api_key:
        game.llm_api_key = body.llm_api_key
    if getattr(body, "skill", None):
        game.skill = _validate_skill(body.skill)
    if getattr(body, "rules", None):
        if body.rules not in {"bridge", "minibridge"}:
            raise HTTPException(status_code=400, detail="rules must be bridge or minibridge")
        game.rules = body.rules


def _play_waiting_llms(game: Game) -> list[dict[str, Any]]:
    played: list[dict[str, Any]] = []
    if not game.auto_robots or not llm_ready(game):
        return played
    guard = 0
    while game.phase not in {"deal_over", "idle"} and game.acting_kind() == "llm":
        action = complete_action(game)
        actor = game.to_act
        game._apply(action)
        played.append(
            {
                "actor": actor,
                "action": action,
                "action_label": action_to_label(action),
                "kind": "llm",
            }
        )
        if game.auto_robots:
            played.extend(game._autoplay_robots())
        guard += 1
        if guard > 40:
            raise HTTPException(status_code=500, detail="llm autoplay did not terminate")
    return played


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "action_space": ACTION_SPACE, "games": len(GAMES)}


@app.get("/api/spec")
def spec() -> dict[str, Any]:
    return {
        "action_space": ACTION_SPACE,
        "actions": {
            "0-51": "play card id (suit*13 + rank, C2=0 ... SA=51)",
            "52-56": "MiniBridge trump C D H S NT",
            "57-63": "MiniBridge trick goal 7-13",
            "64-98": "contract bids 1C..7NT",
            "99": "Pass",
            "100": "Double",
            "101": "Redouble",
        },
        "reward": "0 during the deal; NS points / 100.0 when the deal ends",
        "observation_vector_size": 335,
        "phases": ["auction", "select_trump", "select_goal", "play", "deal_over"],
        "rules": ["bridge", "minibridge"],
        "seats": list(SEATS),
        "text_actions": {
            "auction": "1C 1D 1H 1S 1NT 4H P X XX   seated: N1S EP WX",
            "trump": "*c *d *h *s *n",
            "goal": "#7 #8 #9 #10 #11 #12 #13",
            "play": "As Th 2c Kd   seated: NAs W3s E6s SQh",
            "rejected": "English phrases (play ace of spades, one heart)",
        },
        "player_kinds": ["human", "engine", "llm"],
        "skills": list(SKILLS),
        "computer_ratings": COMPUTER_RATINGS,
        "scoring": {
            "per_trick": {"C": 20, "D": 20, "H": 30, "S": 30, "NT": 40},
            "bonus_if_bid_enough_and_made": {
                "9-11": 100,
                "12": 500,
                "13": 1000,
            },
            "down": "minus (goal - tricks) * trick value, scored from NS",
        },
    }


@app.get("/api/me")
def me() -> dict[str, Any]:
    return platform.me()


@app.get("/api/history")
def history() -> dict[str, Any]:
    return {"games": list(reversed(platform.history[-50:]))}


@app.get("/api/history/{archive_id}")
def history_item(archive_id: str) -> dict[str, Any]:
    try:
        return platform.get_game(archive_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="game not found") from exc


@app.get("/api/puzzles/daily")
def daily_puzzle() -> dict[str, Any]:
    return platform.public_puzzle(platform.ensure_daily())


@app.get("/api/puzzles/next")
def next_puzzle(kind: str | None = None) -> dict[str, Any]:
    return platform.new_puzzle(kind)


@app.get("/api/puzzles/{puzzle_id}")
def get_puzzle(puzzle_id: str) -> dict[str, Any]:
    try:
        return platform.public_puzzle(platform.get_puzzle(puzzle_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="puzzle not found") from exc


@app.post("/api/puzzles/{puzzle_id}/solve")
def solve_puzzle(puzzle_id: str, body: PuzzleSolveRequest) -> dict[str, Any]:
    try:
        return platform.solve_puzzle(puzzle_id, body.action)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="puzzle not found") from exc


@app.post("/api/games")
def create_game(body: NewGameRequest | None = None) -> dict[str, Any]:
    body = body or NewGameRequest()
    seats = _validate_seats(body.agent_seats)
    skill = _validate_skill(body.skill)
    game = Game(
        seed=body.seed,
        auto_robots=False,
        agent_seats=seats,
        skill=skill,
        rules=body.rules or "minibridge",
    )
    _apply_bot_config(game, body)
    game.auto_robots = body.auto_robots
    if game.auto_robots:
        game._autoplay_robots()
        _play_waiting_llms(game)
    game_id = uuid.uuid4().hex[:12]
    GAMES[game_id] = game
    return _payload(game_id, game)


@app.get("/api/games")
def list_games() -> dict[str, Any]:
    return {
        "games": [
            {
                "id": game_id,
                "deal_number": game.deal_number,
                "score": game.score,
                "phase": game.phase,
                "to_act": game.to_act,
                "skill": game.skill,
            }
            for game_id, game in GAMES.items()
        ]
    }


@app.get("/api/games/{game_id}")
def get_game(game_id: str) -> dict[str, Any]:
    return _payload(game_id, _game(game_id))


@app.get("/api/games/{game_id}/observation")
def get_observation(game_id: str) -> dict[str, Any]:
    game = _game(game_id)
    prompt = prompt_payload(game)
    return {
        "id": game_id,
        "phase": game.phase,
        "to_act": game.to_act,
        "done": game.phase == "deal_over",
        "legal_actions": game.legal_actions(),
        "legal_action_labels": [action_to_label(a) for a in game.legal_actions()],
        "action_mask": game.action_mask(),
        "action_space": ACTION_SPACE,
        "obs_vector": game.observation_vector(),
        "state": game.public_state(),
        "hands": game.visible_hands(),
        "text": prompt["user"],
        "system": prompt["system"],
        "waiting_for": game.public_state()["waiting_for"],
    }


@app.get("/api/games/{game_id}/text")
def get_text(game_id: str) -> dict[str, Any]:
    game = _game(game_id)
    prompt = prompt_payload(game)
    return {
        "id": game_id,
        **prompt,
        "scoresheet": game.scoresheet(),
        "waiting_for": game.public_state()["waiting_for"],
    }


@app.post("/api/games/{game_id}/config")
def config_game(game_id: str, body: ConfigRequest) -> dict[str, Any]:
    game = _game(game_id)
    old_rules = game.rules
    _apply_bot_config(game, body)
    if body.rules and body.rules != old_rules:
        game.reset()
    extra: dict[str, Any] = {}
    if game.auto_robots:
        extra["robot_actions"] = game._autoplay_robots() + _play_waiting_llms(game)
    return _payload(game_id, game, extra=extra)


@app.get("/api/games/{game_id}/legal-actions")
def get_legal_actions(game_id: str) -> dict[str, Any]:
    game = _game(game_id)
    actions = game.legal_actions()
    return {
        "id": game_id,
        "phase": game.phase,
        "to_act": game.to_act,
        "actions": actions,
        "labels": [action_to_label(action) for action in actions],
        "action_mask": game.action_mask(),
    }


@app.post("/api/games/{game_id}/step")
def step_game(game_id: str, body: StepRequest) -> dict[str, Any]:
    game = _game(game_id)
    payload: dict[str, Any] = body.model_dump(exclude_none=True)
    if body.action is None and body.type is None and body.card is None and body.trump is None and body.goal is None:
        raise HTTPException(status_code=400, detail="provide action, or type + card/trump/goal")
    try:
        transition = game.step(payload if body.action is None else body.action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    extra = {
        "reward": transition.reward,
        "done": transition.done,
        "info": transition.info,
    }
    extra["info"]["llm_actions"] = _play_waiting_llms(game)
    extra["done"] = game.phase == "deal_over"
    extra["reward"] = extra["reward"] if extra["reward"] else (
        (game.deal_result or {}).get("ns_points", 0) / 100.0 if extra["done"] else 0.0
    )
    _maybe_archive(game, extra)
    return _payload(game_id, game, extra=extra)


@app.post("/api/games/{game_id}/resign")
def resign_game(game_id: str) -> dict[str, Any]:
    game = _game(game_id)
    try:
        game.resign()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    extra: dict[str, Any] = {"done": True, "resigned": True}
    _maybe_archive(game, extra)
    return _payload(game_id, game, extra=extra)


@app.post("/api/games/{game_id}/reset")
def reset_game(game_id: str, body: ResetRequest | None = None) -> dict[str, Any]:
    game = _game(game_id)
    body = body or ResetRequest()
    if body.skill:
        game.skill = _validate_skill(body.skill)
    if body.rules:
        if body.rules not in {"bridge", "minibridge"}:
            raise HTTPException(status_code=400, detail="rules must be bridge or minibridge")
        game.rules = body.rules
    if body.new_match:
        game.new_match(body.seed)
    else:
        game.reset(body.seed)
    extra = {"llm_actions": _play_waiting_llms(game)}
    return _payload(game_id, game, extra=extra)


@app.get("/api/games/{game_id}/trajectory")
def get_trajectory(game_id: str) -> dict[str, Any]:
    game = _game(game_id)
    return {
        "id": game_id,
        "steps": len(game.trajectory),
        "score": game.score,
        "history": game.history,
        "trajectory": game.trajectory,
    }


@app.delete("/api/games/{game_id}")
def delete_game(game_id: str) -> dict[str, Any]:
    if game_id == DEFAULT_ID:
        raise HTTPException(status_code=400, detail="cannot delete the default table")
    _game(game_id)
    del GAMES[game_id]
    return {"deleted": game_id}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/{full_path:path}")
def spa(full_path: str) -> FileResponse:
    if full_path.startswith(("api/", "docs", "redoc", "openapi.json", "static/")):
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(STATIC / "index.html")
