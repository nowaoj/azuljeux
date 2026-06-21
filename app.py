import json
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import (init_db, get_simulations, get_simulation, get_games, get_game,
                get_moves, get_snapshots, get_dashboard_stats)
from simulation import run_simulation
from bots import GreedyBot, PlannedBot, RandomBot, Move, evaluate_move, get_legal_moves
from game import GameState, Color, WALL_LAYOUT, COLOR_NAMES

app = FastAPI(title="Azul Game Analysis")

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

BOT_CHOICES = ["GreedyBot", "PlannedBot", "RandomBot"]

COLOR_HEX = {
    Color.BLUE: "#0066CC",
    Color.YELLOW: "#FFCC00",
    Color.RED: "#CC3333",
    Color.BLACK: "#444444",
    Color.WHITE: "#DDDDDD",
}


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def index(request: Request):
    stats = get_dashboard_stats()
    sims = get_simulations(limit=20)
    return templates.TemplateResponse(request, "index.html", {
        "stats": stats,
        "simulations": sims,
        "bot_choices": BOT_CHOICES,
    })


@app.get("/run")
def run_form(request: Request):
    return templates.TemplateResponse(request, "run.html", {
        "bot_choices": BOT_CHOICES,
    })


@app.post("/run")
def run_submit(
    bot1: str = Form(...),
    bot2: str = Form(...),
    num_games: int = Form(100),
    seed: int = Form(None),
):
    sim_id = run_simulation(bot1, bot2, num_games, seed)
    return RedirectResponse(url=f"/simulations/{sim_id}", status_code=303)


# ── Bots guide ──────────────────────────────────────────────────────

def _build_example_state():
    gs = GameState()
    gs.factories = [
        [Color.BLUE, Color.BLUE, Color.RED, Color.YELLOW],
        [Color.RED, Color.RED, Color.RED, Color.BLACK],
        [], [], [],
    ]
    gs.center = ["START"]
    p = gs.players[0]
    p.pattern_lines = [[], [Color.BLUE], [], [Color.RED, Color.RED], []]
    p.wall = [[None] * 5 for _ in range(5)]
    gs.current_player = 0
    gs._taken_from_center = [False, False]
    gs.round = 2
    return gs


def _explain_move(game, move):
    if move.source_type == "factory":
        src = f"F{move.source_idx + 1}"
    else:
        src = "center"
    dest = f"line {move.line_idx + 1}" if move.line_idx >= 0 else "floor"
    return f"Take {COLOR_NAMES[move.color]} from {src} → {dest}"


@app.get("/bots")
def bots_docs(request: Request):
    gs = _build_example_state()

    moves = get_legal_moves(gs, 0)
    scored = []
    for move in moves:
        ev = evaluate_move(gs, 0, move)
        scored.append({
            "move": _explain_move(gs, move),
            "source": "factory" if move.source_type == "factory" else "center",
            "source_idx": move.source_idx,
            "color": COLOR_NAMES[move.color],
            "color_hex": COLOR_HEX[move.color],
            "line": move.line_idx,
            "S": ev["S"], "P": ev["P"], "R": ev["R"], "C": ev["C"], "K": ev["K"],
            "completes": ev["completes"],
            "finishes_game": ev["finishes_game"],
            "V_greedy": ev["S"] - ev["P"],
            "V_planned": ev["S"] - ev["P"] + ev["R"] * 1 + ev["C"] * 3 + ev["K"] * 5,
        })

    greedy_sorted = sorted(
        scored,
        key=lambda x: (-x["V_greedy"],
                       -(x["line"] if x["line"] >= 0 else -999),
                       -(x["P"] == 0)),
    )
    planned_sorted = sorted(
        scored,
        key=lambda x: (-x["V_planned"],
                       0 if x["completes"] else 1,
                       x["line"] if x["line"] >= 0 else 999),
    )
    greedy_top = greedy_sorted[:8]
    planned_top = planned_sorted[:8]

    factories_display = []
    for fi, f in enumerate(gs.factories):
        if f:
            factories_display.append({
                "label": f"F{fi + 1}",
                "tiles": [{"name": COLOR_NAMES[t], "hex": COLOR_HEX[t]} for t in f],
            })
    center_tiles = [
        {"name": COLOR_NAMES[t], "hex": COLOR_HEX[t]}
        for t in gs.center if isinstance(t, Color)
    ]
    has_start = "START" in gs.center

    pattern_lines_display = []
    for li, pl in enumerate(gs.players[0].pattern_lines):
        row = [{"name": COLOR_NAMES[t], "hex": COLOR_HEX[t]} for t in pl]
        pattern_lines_display.append({
            "index": li, "max": li + 1,
            "tiles": row, "empty": (li + 1) - len(pl),
        })

    wall_display = [[None] * 5 for _ in range(5)]
    for r in range(5):
        for c in range(5):
            wall_display[r][c] = {
                "target": COLOR_NAMES[WALL_LAYOUT[r][c]],
                "hex": COLOR_HEX[WALL_LAYOUT[r][c]],
                "placed": gs.players[0].wall[r][c] is not None,
            }

    return templates.TemplateResponse(request, "bots.html", {
        "factories": factories_display,
        "center_tiles": center_tiles,
        "has_start": has_start,
        "pattern_lines": pattern_lines_display,
        "wall": wall_display,
        "greedy_top": greedy_top,
        "planned_top": planned_top,
        "all_moves": scored,
    })


# ── Scenario builder ────────────────────────────────────────────────

BOT_INSTANCES = {
    "GreedyBot": GreedyBot(),
    "PlannedBot": PlannedBot(),
    "RandomBot": RandomBot(),
}


def _scenario_defaults() -> dict:
    """Return default form values matching the example state on /bots."""
    gs = _build_example_state()
    return _state_to_form(gs, "PlannedBot")


def _state_to_form(gs: GameState, bot_name: str) -> dict:
    """Serialise a GameState to flat form-field dict for template pre-fill."""
    f: dict = {"bot": bot_name}
    for fi in range(5):
        tiles = gs.factories[fi] if fi < len(gs.factories) else []
        for tj in range(4):
            f[f"factory_{fi}_{tj}"] = str(tiles[tj].value) if tj < len(tiles) else ""
    center_colors = [t for t in gs.center if isinstance(t, Color)]
    for color in Color:
        f[f"center_c_{color.value}"] = "on" if color in center_colors else ""
    f["center_start"] = "on" if "START" in gs.center else ""
    for pi in range(2):
        p = gs.players[pi]
        for li in range(5):
            pl = p.pattern_lines[li]
            if pl:
                f[f"p{pi}_pl_{li}_color"] = str(pl[0].value)
                f[f"p{pi}_pl_{li}_count"] = str(len(pl))
            else:
                f[f"p{pi}_pl_{li}_color"] = ""
                f[f"p{pi}_pl_{li}_count"] = "0"
        for r in range(5):
            for c in range(5):
                key = f"p{pi}_wall_{r}_{c}"
                if p.wall[r][c] is not None:
                    f[key] = "on"
        floor_vals = []
        for t in p.floor_line:
            if t == "START":
                floor_vals.append("START")
            else:
                floor_vals.append(str(t.value))
        f[f"p{pi}_floor"] = ",".join(floor_vals)
        f[f"p{pi}_score"] = str(p.score)
    f["current_player"] = str(gs.current_player)
    f["round"] = str(gs.round)
    f["taken_from_center_0"] = "on" if gs._taken_from_center[0] else ""
    f["taken_from_center_1"] = "on" if gs._taken_from_center[1] else ""
    return f


def _build_state_from_form(form) -> GameState:
    """Parse form fields back into a GameState."""
    gs = GameState()
    # Factories
    for fi in range(5):
        gs.factories[fi] = []
        for tj in range(4):
            val = form.get(f"factory_{fi}_{tj}", "")
            if val and val.strip():
                try:
                    gs.factories[fi].append(Color(int(val)))
                except (ValueError, TypeError):
                    pass
    # Centre
    gs.center = []
    for c in range(5):
        if form.get(f"center_c_{c}") == "on":
            gs.center.append(Color(c))
    if form.get("center_start") == "on":
        gs.center.insert(0, "START")
    # Players
    for pi in range(2):
        p = gs.players[pi]
        for li in range(5):
            color_val = form.get(f"p{pi}_pl_{li}_color", "")
            count_val = form.get(f"p{pi}_pl_{li}_count", "0")
            try:
                cnt = int(count_val)
            except (ValueError, TypeError):
                cnt = 0
            if color_val and cnt > 0:
                try:
                    color = Color(int(color_val))
                    max_size = li + 1
                    cnt = min(cnt, max_size)
                    p.pattern_lines[li] = [color] * cnt
                except (ValueError, TypeError):
                    p.pattern_lines[li] = []
            else:
                p.pattern_lines[li] = []
        for r in range(5):
            for c in range(5):
                key = f"p{pi}_wall_{r}_{c}"
                if form.get(key) == "on":
                    p.wall[r][c] = WALL_LAYOUT[r][c]
        floor_str = form.get(f"p{pi}_floor", "")
        p.floor_line = []
        if floor_str:
            for token in floor_str.split(","):
                token = token.strip()
                if token.upper() == "START":
                    p.floor_line.append("START")
                elif token:
                    try:
                        p.floor_line.append(Color(int(token)))
                    except (ValueError, TypeError):
                        pass
        try:
            p.score = max(0, int(form.get(f"p{pi}_score", "0")))
        except (ValueError, TypeError):
            p.score = 0
    try:
        gs.current_player = int(form.get("current_player", "0"))
    except (ValueError, TypeError):
        gs.current_player = 0
    try:
        gs.round = max(1, int(form.get("round", "1")))
    except (ValueError, TypeError):
        gs.round = 1
    if form.get("taken_from_center_0") == "on":
        gs._taken_from_center[0] = True
    if form.get("taken_from_center_1") == "on":
        gs._taken_from_center[1] = True
    return gs


@app.get("/scenario")
def scenario_form(request: Request):
    defaults = _scenario_defaults()
    return templates.TemplateResponse(request, "scenario.html", {
        "bot_choices": BOT_CHOICES,
        "color_names": COLOR_NAMES,
        "color_hex": COLOR_HEX,
        "wall_layout": WALL_LAYOUT,
        "floor_penalties_text": [-1, -1, -2, -2, -2, -3, -3],
        "defaults": defaults,
        "results": None,
    })


@app.post("/scenario")
async def scenario_submit(request: Request):
    form = await request.form()
    bot_name = form.get("bot", "PlannedBot")

    gs = _build_state_from_form(form)
    bot = BOT_INSTANCES.get(bot_name)
    if bot is None:
        bot = BOT_INSTANCES["PlannedBot"]
        bot_name = "PlannedBot"

    move = bot.choose_move(gs, 0)
    results = None
    if move is not None:
        # Build scored list for the result table
        moves = get_legal_moves(gs, 0)
        scored = []
        for m in moves:
            ev = evaluate_move(gs, 0, m)
            scored.append({
                "move": _explain_move(gs, m),
                "color": COLOR_NAMES[m.color],
                "color_hex": COLOR_HEX[m.color],
                "line": m.line_idx,
                "S": ev["S"],
                "P": ev["P"],
                "R": ev["R"],
                "C": ev["C"],
                "K": ev["K"],
                "completes": ev["completes"],
                "finishes_game": ev["finishes_game"],
                "V": ev.get("V", ev["S"] - ev["P"]),
                "chosen": m == move,
            })
        results = {
            "bot_name": bot_name,
            "chosen_move": _explain_move(gs, move),
            "chosen_color": COLOR_NAMES[move.color],
            "chosen_color_hex": COLOR_HEX[move.color],
            "chosen_line": move.line_idx,
            "reason": bot.last_reason,
            "scored": scored,
            "num_moves": len(moves),
        }

    defaults = _state_to_form(gs, bot_name)
    return templates.TemplateResponse(request, "scenario.html", {
        "bot_choices": BOT_CHOICES,
        "color_names": COLOR_NAMES,
        "color_hex": COLOR_HEX,
        "wall_layout": WALL_LAYOUT,
        "floor_penalties_text": [-1, -1, -2, -2, -2, -3, -3],
        "defaults": defaults,
        "results": results,
    })


# ── Math IA suggestions ─────────────────────────────────────────────

IA_METRICS = [
    {
        "id": "win_rate",
        "name": "Win rate with confidence interval",
        "description": "For each bot in a matchup, compute the proportion of wins "
                       "across N games. Use the Wilson score interval to get a 95% "
                       "confidence interval around the observed win rate.",
        "formula": "p̂ ± z√(p̂(1−p̂)/N + z²/4N²) / (1 + z²/N)",
        "visualisation": "Bar chart of win rates with error bars.",
        "statistical_test": "Chi-squared test (or G-test) of independence: does "
                            "the winner distribution depend on which bot plays first?",
    },
    {
        "id": "score_diff",
        "name": "Score difference distribution",
        "description": "For each game compute Δ = score₁ − score₂. A positive mean "
                       "indicates bot₁ has an advantage. Visualise the distribution "
                       "and test whether the mean is significantly different from zero.",
        "formula": "H₀: μ_Δ = 0    H₁: μ_Δ ≠ 0",
        "visualisation": "Histogram of score differences + overlaid normal curve.",
        "statistical_test": "One-sample t-test or Wilcoxon signed-rank test.",
    },
    {
        "id": "first_player",
        "name": "First-player advantage",
        "description": "Compare win rates when a bot starts vs when it goes second. "
                       "Azul has a known first-player disadvantage (the first to take "
                       "from centre gets the −1 START penalty). Quantify this effect.",
        "formula": "WinRate(starting) − WinRate(second)",
        "visualisation": "Grouped bar chart: wins by bot + starting position.",
        "statistical_test": "Two-proportion z-test or Fisher's exact test.",
    },
    {
        "id": "rounds",
        "name": "Game length (rounds and turns)",
        "description": "How many rounds does each bot pairing take to finish? "
                       "More aggressive bots may end the game faster.",
        "formula": "Mean rounds ± SD, mean turns ± SD",
        "visualisation": "Box plot of rounds per matchup.",
        "statistical_test": "Two-sample t-test for rounds between different matchups.",
    },
    {
        "id": "floor_penalty",
        "name": "Floor penalty accumulation",
        "description": "Track total floor penalty per game per bot. Do smarter bots "
                       "avoid the floor more effectively? Is floor penalty correlated "
                       "with losing?",
        "formula": "Mean penalty per game per bot",
        "visualisation": "Violin plot of floor penalties per bot.",
        "statistical_test": "Mann-Whitney U test comparing penalties between bots.",
    },
    {
        "id": "bonus_breakdown",
        "name": "End-game bonus breakdown",
        "description": "Record the three bonuses (rows, columns, colour sets) "
                       "separately. Which bonus type contributes most to the final "
                       "score? Do different bots prioritise different bonuses?",
        "formula": "Mean row bonus, mean column bonus, mean colour-set bonus per bot",
        "visualisation": "Stacked bar chart of score components.",
        "statistical_test": "ANOVA: do the three bonus types differ in magnitude?",
    },
    {
        "id": "move_diversity",
        "name": "Move diversity and entropy",
        "description": "For each bot, compute the entropy of chosen moves. "
                       "A deterministic bot (PlannedBot) will have lower entropy "
                       "than a random one. Measure how predictable each bot is.",
        "formula": "H = −∑ p(m) log₂ p(m)",
        "visualisation": "Entropy bar chart per bot.",
        "statistical_test": "Compare variance of move choices between bots (F-test).",
    },
    {
        "id": "score_progression",
        "name": "Score progression per round",
        "description": "Track cumulative score after each round. Do bots that score "
                       "early maintain their lead, or do comeback wins happen?",
        "formula": "Score_round(r) − Score_round(r−1)",
        "visualisation": "Line chart of cumulative scores by round (one line per bot, "
                         "shaded ±1 SD).",
        "statistical_test": "Repeated-measures ANOVA or mixed-effects model.",
    },
]

RECOMMENDED_PIPELINE = [
    "Install Jupyter notebook or use the web dashboard to explore data.",
    "Export simulation data from SQLite to a Pandas DataFrame for analysis.",
    "Start with descriptive statistics: means, variances, histograms.",
    "Move to inferential tests: t-tests, chi-squared, confidence intervals.",
    "Create visualisations for your IA: bar charts, box plots, histograms.",
    "Interpret results in the context of Azul game theory.",
]

DB_QUERY_EXAMPLES = [
    {
        "title": "Win counts per bot",
        "sql": "SELECT winner, COUNT(*) FROM games GROUP BY winner;",
    },
    {
        "title": "Average score per bot in a simulation",
        "sql": "SELECT AVG(score1), AVG(score2) FROM games WHERE simulation_id = 1;",
    },
    {
        "title": "Games where winner scored less than loser (comebacks)",
        "sql": "SELECT * FROM games WHERE (winner = 0 AND score1 < score2) OR (winner = 1 AND score2 < score1);",
    },
    {
        "title": "Score difference distribution",
        "sql": "SELECT score1 - score2 AS diff FROM games;",
    },
]


@app.get("/ia")
def math_ia(request: Request):
    return templates.TemplateResponse(request, "ia.html", {
        "metrics": IA_METRICS,
        "pipeline": RECOMMENDED_PIPELINE,
        "db_queries": DB_QUERY_EXAMPLES,
    })


# ── Simulation routes ───────────────────────────────────────────────

@app.get("/simulations")
def simulations_list(request: Request):
    sims = get_simulations(limit=100)
    return templates.TemplateResponse(request, "simulations.html", {
        "simulations": sims,
    })


@app.get("/simulations/{sim_id}")
def simulation_detail(request: Request, sim_id: int):
    sim = get_simulation(sim_id)
    if not sim:
        return templates.TemplateResponse(request, "404.html", status_code=404)
    games = get_games(sim_id)

    total = len(games)
    wins1 = sum(1 for g in games if g["winner"] == 0)
    wins2 = sum(1 for g in games if g["winner"] == 1)
    draws = total - wins1 - wins2
    scores1 = [g["score1"] for g in games]
    scores2 = [g["score2"] for g in games]
    mean1 = sum(scores1) / total if total else 0
    mean2 = sum(scores2) / total if total else 0
    rounds_list = [g["rounds"] for g in games]
    mean_rounds = sum(rounds_list) / total if total else 0

    score_dist = {}
    for s in scores1 + scores2:
        bucket = (s // 10) * 10
        score_dist[bucket] = score_dist.get(bucket, 0) + 1

    max_count = max(score_dist.values()) if score_dist else 1
    dist_buckets = sorted(score_dist.items())

    return templates.TemplateResponse(request, "result.html", {
        "sim": sim,
        "games": games,
        "total": total,
        "wins1": wins1,
        "wins2": wins2,
        "draws": draws,
        "mean1": round(mean1, 1),
        "mean2": round(mean2, 1),
        "mean_rounds": round(mean_rounds, 1),
        "dist_buckets": dist_buckets,
        "max_count": max_count,
    })


@app.get("/games/{game_id}/replay")
def game_replay(request: Request, game_id: int):
    game = get_game(game_id)
    if not game:
        return templates.TemplateResponse(request, "404.html", status_code=404)
    sim = get_simulation(game["simulation_id"])
    snapshots = get_snapshots(game_id)
    # Pre-parse evaluations_json so the template doesn't have to
    for snap in snapshots:
        if snap.get("evaluations_json"):
            snap["evaluations"] = json.loads(snap["evaluations_json"])
        else:
            snap["evaluations"] = []
    assets_dir = BASE_DIR / "static" / "assets"
    tile_images = {
        slug: (assets_dir / f"{slug}.png").is_file()
        for slug in ["blue", "yellow", "red", "black", "white", "start"]
    }
    return templates.TemplateResponse(request, "replay.html", {
        "game": game,
        "bot1_name": sim["bot1_name"] if sim else "Player 0",
        "bot2_name": sim["bot2_name"] if sim else "Player 1",
        "snapshots_json": json.dumps(snapshots),
        "total_steps": len(snapshots),
        "tile_images_json": json.dumps(tile_images),
    })
