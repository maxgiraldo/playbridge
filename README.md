# PlayBridge

A chess.com-style MiniBridge site: rated games vs computer, puzzles, lessons,
post-game review, and a gym API so an agent can learn from the same table.

## Run

```bash
python3 -m pip install -r requirements.txt
python3 run.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

| Page | What it is |
| --- | --- |
| `/` | Home, rating, recent games |
| `/play` | Pick a computer (Beginner → Master) |
| `/play/live` | The table |
| `/puzzles` | Daily tactics |
| `/learn` | MiniBridge lessons |
| `/review` | Analyze a finished deal |
| `/history` | Game list and rating swings |
| `/developers` | Move API for agents |

## How a game works

Default rules are **contract bridge**. You sit South. Dealer and vulnerability
follow the duplicate board cycle. Everyone bids (`1C`…`7NT`, `P`, `X`, `XX`).
Three passes after a bid set the contract. Declarer is the first player on the
winning side who bid that strain. Dummy goes face-up after the opening lead.

Scoring is duplicate: part-score +50, game 300/500, slams 500/750 and
1000/1500, doubled undertricks, all from the North–South column.

MiniBridge (no auction — declarer picks trump and a trick goal) is still on
the Rules menu.

## LLM bots (text API)

Each seat is `human`, `engine`, or `llm`. An LLM plays through compact
notation, the same idea as chess `Nb4` / `Ka1`. The seat is the piece and
the card is the square:

```
N1S EP S2H WP N4H P P P
*h #10
 1. W3s NAs E6s SQh
```

Bids use uppercase strain (`1H`, `1NT`) so they are not cards (`4h`).
Calls are `P`, `X`, `XX`. Cards stay lowercase-suit (`As`).
English is rejected.

```bash
GET  /api/games/table/text
# { system, user, legal_action_labels, waiting_for }

POST /api/games/table/step
{ "action": "As" }
```

Point partner/opponents at a model in the table bar, or:

```bash
curl -X POST http://127.0.0.1:8000/api/games/table/config \
  -H 'content-type: application/json' \
  -d '{"partner":"llm","opponents":"llm","llm_model":"gpt-4.1-mini"}'
```

If you set an API key, the server calls that OpenAI-compatible model.
If you do not, the table waits and your agent posts the text move.

```bash
export OPENAI_API_KEY=...
python examples/llm_bot.py --game table --model gpt-4.1-mini
```

## Learning API

Same discrete actions the UI sends:

| Id | Meaning |
| --- | --- |
| 0–51 | Play that card |
| 52–56 | Trump C D H S NT |
| 57–63 | Trick goal 7–13 |

```python
import httpx
client = httpx.Client(base_url="http://127.0.0.1:8000")
game = client.post("/api/games", json={"seed": 1, "skill": "intermediate"}).json()
obs = client.get(f"/api/games/{game['id']}/observation").json()
while not obs["done"]:
    result = client.post(
        f"/api/games/{game['id']}/step",
        json={"action": obs["legal_actions"][0]},
    ).json()
    obs = client.get(f"/api/games/{game['id']}/observation").json()
```

Docs: `/docs` · action spec: `/api/spec` · example client: `examples/random_agent.py`.

## Tests

```bash
python3 -m pytest
```
