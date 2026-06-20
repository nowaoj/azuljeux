import json
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import init_db, get_simulations, get_simulation, get_games, get_game, get_moves, get_snapshots, get_dashboard_stats
from simulation import run_simulation

app = FastAPI(title="Azul Game Analysis")

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

BOT_CHOICES = ["GreedyBot", "PlannedBot", "RandomBot", "FixedPriorityOpponent"]


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
    snapshots = get_snapshots(game_id)
    return templates.TemplateResponse(request, "replay.html", {
        "game": game,
        "snapshots_json": json.dumps(snapshots),
        "total_steps": len(snapshots),
    })
