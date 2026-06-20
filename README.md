# Azul Game Analysis

Board game engine + bot simulation + web statistics dashboard.
Built for an IB DP Mathematics Internal Assessment on game theory and statistical analysis of bot strategies.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Launch the web dashboard

```bash
uvicorn app:app --reload
```

Open http://localhost:8000 in your browser.

### Run tests

```bash
pytest tests/ -v
```

## Project structure

| File | Purpose |
|------|---------|
| `game.py` | Core Azul game engine (rules, scoring, state) |
| `bots.py` | AI bot implementations (Greedy, Planned, Random, FixedPriority) |
| `db.py` | SQLite database layer for storing results and replays |
| `simulation.py` | Multiprocessing simulation runner |
| `app.py` | FastAPI web application (dashboard + API) |
| `templates/` | Jinja2 HTML templates |
| `static/` | CSS styles |
| `tests/` | Pytest unit tests |

## Available bots

- **GreedyBot** — maximises immediate wall score minus floor penalties
- **PlannedBot** — weighted utility considering wall score, row/column/colour progress
- **RandomBot** — random target with largest source selection
- **FixedPriorityOpponent** — avoids floor when possible
