# Azul Game Analysis

Board game engine + bot simulation + web dashboard + player vs bot / player vs human.
Built for an IB DP Mathematics Internal Assessment on game theory and statistical analysis of bot strategies.

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
```

## Run the web server

```bash
python manage.py runserver
```

Open http://localhost:8000 in your browser.

## Run a bot simulation via command line

```bash
python manage.py run_simulation 1
```

(Simulations created through the web UI get an ID automatically.)

## Run tests

```bash
pytest tests/ -v
```

## Features

- **Play vs Bot** — play Azul against GreedyBot, PlannedBot, or RandomBot. Every bot move is logged with evaluation scores so you can review why it chose each move.
- **Play vs Human** — create a game, share the Game ID with a friend, and play turn-by-turn over the network.
- **Simulations** — run hundreds of bot-vs-bot games with configurable matchups. Results include win rates, score distributions, and per-game replay.
- **Replay viewer** — step through any game (bot or human) move by move with the full board state at each step.
- **Bot guide** — explains how each bot makes decisions with worked examples.
- **Math IA page** — statistical analysis suggestions, SQL queries, and export guides for the Internal Assessment.
- **User accounts** — register, log in, and track your games.

## Project structure

| Path | Purpose |
|------|---------|
| `game.py` | Core Azul game engine (rules, scoring, state) |
| `bots.py` | AI bot implementations (Greedy, Planned, Random) |
| `azul/` | Django app: models, views, forms, URL routing |
| `azul/models.py` | ORM models for simulations, games, player games |
| `azul/views.py` | All web views (dashboard, play, auth, simulation runner) |
| `azul/sim_runner.py` | Multiprocessing simulation runner (imported by views + management command) |
| `azul/management/commands/run_simulation.py` | CLI management command to run a simulation |
| `templates/` | Django templates (DTL) |
| `static/` | CSS and tile images |
| `tests/` | Pytest unit tests for the game engine |

## Custom tile images

Place PNG images in `static/assets/` to replace coloured circles:

- `blue.png`, `yellow.png`, `red.png`, `black.png`, `white.png`, `start.png`

Each image should be roughly square (e.g. 28×28 px).

## Available bots

- **GreedyBot** — maximises immediate wall score minus floor penalties (`V = S − P`). Avoids ending the game unless winning.
- **PlannedBot** — weighted utility: `V = S − P + R·1 + C·3 + K·5` where R/C/K track row, column, and colour-set progress toward end-game bonuses.
- **RandomBot** — picks a random target colour and line, takes the largest available source.
