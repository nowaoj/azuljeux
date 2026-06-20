import random
import statistics
from game import GameState, Color
from bots import GreedyBot, PlannedBot, FixedPriorityOpponent

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
    snap = game.get_state_snapshot()
    p0 = game.players[0]
    p1 = game.players[1]
    return {
        "score0": p0.score, "score1": p1.score,
        "wall0": p0.wall, "wall1": p1.wall,
        "winner": snap["winner"],
        "penalty0": penalty_acc[0],
        "penalty1": penalty_acc[1],
    }

N = 100

matchups = [
    ("GreedyBot", GreedyBot(), "PlannedBot", PlannedBot()),
    ("PlannedBot", PlannedBot(), "FixedPriority", FixedPriorityOpponent()),
    ("GreedyBot", GreedyBot(), "FixedPriority", FixedPriorityOpponent()),
]

for name_a, bot_a, name_b, bot_b in matchups:
    results = []
    for seed in range(N):
        random.seed(seed)
        r = play_game(bot_a, bot_b)
        floor_penalty_0 = r["penalty0"]
        floor_penalty_1 = r["penalty1"]
        r["penalty0"] = -floor_penalty_0
        r["penalty1"] = -floor_penalty_1
        r["rows0"] = rows_completed(r["wall0"])
        r["rows1"] = rows_completed(r["wall1"])
        r["cols0"] = cols_completed(r["wall0"])
        r["cols1"] = cols_completed(r["wall1"])
        r["colours0"] = colour_sets(r["wall0"])
        r["colours1"] = colour_sets(r["wall1"])
        results.append(r)

    scores_a = [r["score0"] for r in results]
    scores_b = [r["score1"] for r in results]
    wins_a = sum(1 for r in results if r["winner"] == 0)
    wins_b = sum(1 for r in results if r["winner"] == 1)
    margins = [r["score0"] - r["score1"] for r in results]
    penalties_a = [r["penalty0"] for r in results]
    penalties_b = [r["penalty1"] for r in results]
    rows_a = [r["rows0"] for r in results]
    rows_b = [r["rows1"] for r in results]
    cols_a = [r["cols0"] for r in results]
    cols_b = [r["cols1"] for r in results]
    colours_a = [r["colours0"] for r in results]
    colours_b = [r["colours1"] for r in results]

    print(f"Matchup: {name_a} (A) vs {name_b} (B)")
    print(f"{'Metric':<30} {name_a:<20} {name_b:<20}")
    print("-" * 70)
    print(f"{'Mean score':<30} {statistics.mean(scores_a):<20.2f} {statistics.mean(scores_b):<20.2f}")
    print(f"{'Score variance':<30} {statistics.variance(scores_a):<20.2f} {statistics.variance(scores_b):<20.2f}")
    print(f"{'Win rate':<30} {wins_a/N:<20.2%} {wins_b/N:<20.2%}")
    print(f"{'Mean winning margin':<30} {statistics.mean(margins):<20.2f} {'':<20}")
    print(f"{'Median winning margin':<30} {statistics.median(margins):<20.2f} {'':<20}")
    print(f"{'Avg rows completed':<30} {statistics.mean(rows_a):<20.2f} {statistics.mean(rows_b):<20.2f}")
    print(f"{'Avg columns completed':<30} {statistics.mean(cols_a):<20.2f} {statistics.mean(cols_b):<20.2f}")
    print(f"{'Avg colour sets completed':<30} {statistics.mean(colours_a):<20.2f} {statistics.mean(colours_b):<20.2f}")
    print(f"{'Avg penalty points':<30} {statistics.mean(penalties_a):<20.2f} {statistics.mean(penalties_b):<20.2f}")
    print()
