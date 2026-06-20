import json
import random
from multiprocessing import Pool

from game import GameState, COLOR_NAMES
from bots import GreedyBot, PlannedBot, RandomBot, FixedPriorityOpponent
from db import create_simulation, insert_game, insert_move, insert_snapshot

BOT_REGISTRY = {
    "GreedyBot": GreedyBot,
    "PlannedBot": PlannedBot,
    "RandomBot": RandomBot,
    "FixedPriorityOpponent": FixedPriorityOpponent,
}


def _run_one(args):
    bot1_name, bot2_name, seed, game_index = args
    rng = random.Random(seed) if seed is not None else random.Random()

    bot1_cls = BOT_REGISTRY[bot1_name]
    bot2_cls = BOT_REGISTRY[bot2_name]
    bot1 = bot1_cls()
    bot2 = bot2_cls()

    game = GameState()
    game.init_bag()
    game.start_round()

    moves = []
    snapshots = []
    turn = 0

    initial_snap = game.get_state_snapshot()
    snapshots.append(("Game start", json.dumps(initial_snap)))

    while not game.game_over:
        player = game.current_player
        bot = bot1 if player == 0 else bot2
        move = bot.choose_move(game, player)
        if move is None:
            break

        scores_before = [game.players[0].score, game.players[1].score]

        color_name = COLOR_NAMES.get(move.color, str(move.color))
        src = f"F{move.source_idx + 1}" if move.source_type == "factory" else "center"
        dest = f"line {move.line_idx + 1}" if move.line_idx >= 0 else "floor"
        action_desc = f"P{player} takes {color_name} from {src} -> {dest}"

        moves.append({
            "turn": turn,
            "player": player,
            "action_type": move.source_type,
            "source_idx": move.source_idx if move.source_type == "factory" else -1,
            "color": color_name,
            "line_idx": move.line_idx,
            "score_p1_before": scores_before[0],
            "score_p2_before": scores_before[1],
        })

        if move.source_type == "center":
            game.current_player_action("center", move.color, move.line_idx)
        else:
            game.current_player_action("factory", move.source_idx, move.color, move.line_idx)

        turn += 1

        snap = game.get_state_snapshot()
        snapshots.append((action_desc, json.dumps(snap)))

        if game.phase == "wall_tiling":
            game.resolve_wall_tiling()
            snap = game.get_state_snapshot()
            snapshots.append(("Wall tiling resolved", json.dumps(snap)))

    final_snap = game.get_state_snapshot()
    snapshots.append(("Game over", json.dumps(final_snap)))

    return {
        "game_index": game_index,
        "seed": seed,
        "score1": final_snap["players"][0]["score"],
        "score2": final_snap["players"][1]["score"],
        "winner": final_snap["winner"],
        "rounds": final_snap["round"],
        "total_turns": turn,
        "moves": moves,
        "snapshots": snapshots,
    }


def run_simulation(bot1_name, bot2_name, num_games, seed=None, workers=None):
    sim_id = create_simulation(bot1_name, bot2_name, num_games, seed)

    args_list = [
        (bot1_name, bot2_name, (seed + i) if seed is not None else None, i)
        for i in range(num_games)
    ]

    pool_size = workers if workers else min(num_games, 8)
    with Pool(pool_size) as pool:
        results = pool.map(_run_one, args_list)

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
                gid,
                move["turn"],
                move["player"],
                move["action_type"],
                move["source_idx"],
                move["color"],
                move["line_idx"],
                move["score_p1_before"],
                move["score_p2_before"],
            )

        for action_desc, state_json in result["snapshots"]:
            insert_snapshot(gid, 0, state_json, action_desc)

    return sim_id
