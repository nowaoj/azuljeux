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
| `bots.py` | AI bot implementations (Greedy, Planned, Random) |
| `db.py` | SQLite database layer for storing results and replays |
| `simulation.py` | Multiprocessing simulation runner |
| `app.py` | FastAPI web application (dashboard + API) |
| `templates/` | Jinja2 HTML templates |
| `static/` | CSS styles |
| `tests/` | Pytest unit tests |

## Custom tile images

Place PNG images in `static/assets/` to replace coloured circles in the replay viewer:

| File | Purpose |
|------|---------|
| `blue.png` | Blue tile |
| `yellow.png` | Yellow tile |
| `red.png` | Red tile |
| `black.png` | Black tile |
| `white.png` | White tile |
| `start.png` | START token (the unique −1 penalty marker) |

Each image is checked independently — if a file is present it replaces the coloured circle for that colour only; missing files fall back to the default circle. Images should be roughly square (e.g. 28×28 px for tile slots, 16×16 for bag/lid counters).

## Available bots

- **GreedyBot** — maximises immediate wall score minus floor penalties
- **PlannedBot** — weighted utility considering wall score, row/column/colour progress
- **RandomBot** — random target with largest source selection
- **RandomBot** — picks a random target line/colour, takes largest source
