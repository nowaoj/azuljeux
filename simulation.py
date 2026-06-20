"""Run many Azul games in parallel and store results in the database.

Each game is played by two bots.  After every turn we store:
  - A state snapshot for the replay viewer.
  - All legal moves the bot considered, with full evaluation scores,
    so the frontend can display "what the bot could have done".
"""

import json
from multiprocessing import Pool

from game import GameState, COLOR_NAMES
from bots import Bot, GreedyBot, PlannedBot, RandomBot
from db import (create_simulation, set_simulation_status,
                increment_games_completed,
                insert_game, insert_move, insert_snapshot)


BOT_REGISTRY: dict[str, type[Bot]] = {
    "GreedyBot":  GreedyBot,
    "PlannedBot": PlannedBot,
    "RandomBot":  RandomBot,
}


def _serialise_evaluation(eval_dict: dict) -> dict:
    """Convert an evaluation dict to a JSON-safe dict (no Move objects)."""
    move = eval_dict["move"]
    return {
        "source_type":   move.source_type,
        "source_idx":    move.source_idx,
        "color_name":    COLOR_NAMES.get(move.color, str(move.color)),
        "color_value":   int(move.color),
        "line_idx":      move.line_idx,
        "S":             eval_dict["S"],
        "P":             eval_dict["P"],
        "R":             eval_dict["R"],
        "C":             eval_dict["C"],
        "K":             eval_dict["K"],
        "V":             eval_dict.get("V", 0),
        "completes":     eval_dict["completes"],
        "finishes_game": eval_dict["finishes_game"],
        "taken":         eval_dict["taken"],
        "overflow":      eval_dict["overflow"],
        "got_start":     eval_dict["got_start"],
    }


def _run_one(args: tuple) -> dict:
    """Run a single game.  Extracted as a module-level function for pickling."""
    bot1_name, bot2_name, seed, game_index = args

    game        = GameState(seed=seed)
    bot1        = BOT_REGISTRY[bot1_name]()
    bot2        = BOT_REGISTRY[bot2_name]()
    bot_names   = [bot1_name, bot2_name]

    game.start_round()

    moves     = []
    snapshots = []
    turn      = 0

    # ── Initial snapshot ────────────────────────────────────────────────
    snapshots.append({
        "action_desc": "Game start",
        "state_json":  json.dumps(game.get_state_snapshot()),
        "evaluations_json": None,
    })

    while not game.game_over:
        player = game.current_player
        bot    = bot1 if player == 0 else bot2
        move   = bot.choose_move(game, player)
        if move is None:
            # Bot cannot / will not move → force end game
            if not game.game_over:
                game.game_over = True
                game._calculate_final_scores()
            break

        scores_before = [game.players[0].score, game.players[1].score]

        # ── Compute a human-readable action description ─────────────────
        color_name = COLOR_NAMES.get(move.color, str(move.color))
        src = (f"F{move.source_idx + 1}"
               if move.source_type == "factory"
               else "center")
        dest = f"line {move.line_idx + 1}" if move.line_idx >= 0 else "floor"
        action_desc = (f"P{player} takes {color_name} from {src} -> {dest}"
                       f" | {bot_names[player]}: {bot.last_reason}")

        # ── Record the move in the moves table ──────────────────────────
        moves.append({
            "turn":       turn,
            "player":     player,
            "action_type":  move.source_type,
            "source_idx":   move.source_idx if move.source_type == "factory" else -1,
            "color":        color_name,
            "line_idx":     move.line_idx,
            "score_p1_before": scores_before[0],
            "score_p2_before": scores_before[1],
        })

        # ── Execute the move ────────────────────────────────────────────
        success = game.execute_move(
            player, move.source_type, move.source_idx, move.color, move.line_idx,
        )
        if not success:
            break

        turn += 1

        # ── Snapshot with evaluations ───────────────────────────────────
        evals_serialised = [
            _serialise_evaluation(e) for e in bot.last_evaluations
        ]
        # Mark the chosen move
        for e in evals_serialised:
            e["chosen"] = (
                e["source_type"]  == move.source_type
                and e["source_idx"]   == move.source_idx
                and e["color_value"]  == int(move.color)
                and e["line_idx"]     == move.line_idx
            )

        snapshots.append({
            "action_desc":      action_desc,
            "state_json":       json.dumps(game.get_state_snapshot()),
            "evaluations_json": json.dumps(evals_serialised) if evals_serialised else None,
        })

        # ── Wall tiling if phase just ended ────────────────────────────
        if game.phase == "wall_tiling":
            game.resolve_wall_tiling()
            snapshots.append({
                "action_desc": "Wall tiling resolved",
                "state_json":  json.dumps(game.get_state_snapshot()),
                "evaluations_json": None,
            })

    # ── Final snapshot ──────────────────────────────────────────────────
    snapshots.append({
        "action_desc": "Game over",
        "state_json":  json.dumps(game.get_state_snapshot()),
        "evaluations_json": None,
    })

    final_state = game.get_state_snapshot()
    return {
        "game_index":  game_index,
        "seed":        seed,
        "score1":      final_state["players"][0]["score"],
        "score2":      final_state["players"][1]["score"],
        "winner":      final_state["winner"],
        "rounds":      final_state["round"],
        "total_turns": turn,
        "moves":       moves,
        "snapshots":   snapshots,
    }


def run_simulation(bot1_name: str, bot2_name: str, num_games: int,
                   seed: int | None = None, workers: int | None = None) -> int:
    """Run *num_games* games between two bots, storing results in the DB.

    Returns the simulation ID.
    """
    sim_id = create_simulation(bot1_name, bot2_name, num_games, seed)
    set_simulation_status(sim_id, "running")

    args_list = [
        (bot1_name, bot2_name, (seed + i) if seed is not None else None, i)
        for i in range(num_games)
    ]

    pool_size = workers if workers else min(num_games, 8)
    try:
        with Pool(pool_size) as pool:
            results = pool.map(_run_one, args_list)
    except Exception:
        set_simulation_status(sim_id, "failed")
        raise

    for result in results:
        gid = insert_game(
            sim_id,
            result["game_index"],
            result["seed"],
            result["score1"],
            result["score2"],
            result["winner"],
            result["rounds"],
            result["total_turns"],
        )
        for move in result["moves"]:
            insert_move(
                gid, move["turn"], move["player"],
                move["action_type"], move["source_idx"],
                move["color"], move["line_idx"],
                move["score_p1_before"], move["score_p2_before"],
            )
        for snap in result["snapshots"]:
            insert_snapshot(
                gid, 0, snap["state_json"],
                snap["action_desc"], snap["evaluations_json"],
            )
        increment_games_completed(sim_id)

    set_simulation_status(sim_id, "done")
    return sim_id
