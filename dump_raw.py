import random, statistics, csv
from game import GameState, Color
from bots import GreedyBot, PlannedBot, FixedPriorityOpponent, RandomBot

FLOOR_PENALTIES = [-1, -1, -2, -2, -2, -3, -3]

def rows_completed(wall):
    return sum(1 for row in wall if all(c is not None for c in row))

def cols_completed(wall):
    return sum(1 for c in range(5) if all(wall[r][c] is not None for r in range(5)))

def colour_sets(wall):
    return sum(1 for c in range(5) if all(wall[r][c] is not None for r in range(5)))

def play_game(bot0, bot1):
    game = GameState()
    game.init_bag()
    game.start_round()
    penalty_acc = [0, 0]
    while not game.game_over:
        if game.phase == "wall_tiling":
            for pi in range(2):
                for i, tile in enumerate(game.players[pi].floor_line):
                    if i < len(FLOOR_PENALTIES):
                        penalty_acc[pi] -= FLOOR_PENALTIES[i]
            game.resolve_wall_tiling()
            continue
        p = game.current_player
        bot = bot0 if p == 0 else bot1
        move = bot.choose_move(game, p)
        if move is None:
            break
        if move.source_type == "center":
            game.current_player_action("center", move.color, move.line_idx)
        else:
            game.current_player_action("factory", move.source_idx, move.color, move.line_idx)
    return {
        "score0": game.players[0].score, "score1": game.players[1].score,
        "wall0": game.players[0].wall, "wall1": game.players[1].wall,
        "winner": game.get_state_snapshot()["winner"],
        "penalty0": penalty_acc[0], "penalty1": penalty_acc[1],
    }

N = 100

matchups = [
    ("greedy_vs_planned", "GreedyBot", GreedyBot(), "PlannedBot", PlannedBot()),
    ("planned_vs_fixed", "PlannedBot", PlannedBot(), "FixedPriority", FixedPriorityOpponent()),
    ("greedy_vs_fixed", "GreedyBot", GreedyBot(), "FixedPriority", FixedPriorityOpponent()),
    ("planned_vs_random", "PlannedBot", PlannedBot(), "RandomBot", RandomBot()),
]

for fname, name_a, bot_a, name_b, bot_b in matchups:
    rows = []
    for seed in range(N):
        random.seed(seed)
        r = play_game(bot_a, bot_b)
        rows.append({
            "seed": seed,
            "score_a": r["score0"], "score_b": r["score1"],
            "penalty_a": r["penalty0"], "penalty_b": r["penalty1"],
            "rows_a": rows_completed(r["wall0"]), "rows_b": rows_completed(r["wall1"]),
            "cols_a": cols_completed(r["wall0"]), "cols_b": cols_completed(r["wall1"]),
            "colours_a": colour_sets(r["wall0"]), "colours_b": colour_sets(r["wall1"]),
            "winner": r["winner"],
        })
    out = f"raw_{fname}.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"Written {out}")
