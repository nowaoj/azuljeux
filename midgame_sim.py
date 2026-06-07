import csv
import random
import copy
from game import GameState, Color, WALL_LAYOUT, FACTORY_COUNT
from bots import GreedyBot, PlannedBot, RandomBot


def generate_midgame_state(seed, num_wall_tiles=12):
    rng = random.Random(seed)

    gs = GameState()
    gs.init_bag()
    gs.round = 3
    gs.current_player = 0
    gs.starting_player = 0
    gs.phase = "factory_offer"

    all_positions = [(r, c) for r in range(5) for c in range(5)]
    rng.shuffle(all_positions)

    player = 0
    taken = 0
    for r, c in all_positions:
        if taken >= num_wall_tiles:
            break
        if gs.players[player].wall[r][c] is None:
            gs.players[player].wall[r][c] = WALL_LAYOUT[r][c]
            taken += 1
            player = 1 - player

    for p in range(2):
        for li in range(5):
            for c in range(5):
                if gs.players[p].wall[li][c] is not None:
                    gs.players[p].pattern_lines[li] = []
                    break

    for p in range(2):
        score = 0
        for r in range(5):
            for c in range(5):
                if gs.players[p].wall[r][c] is not None:
                    score += 1
        gs.players[p].score = score

    gs.taken_from_center = [False, False]
    gs.center = ["START"]

    return gs


def fill_factories_from_bag(gs, rng):
    for i in range(FACTORY_COUNT):
        gs.factories[i] = []
        for _ in range(4):
            if gs.bag:
                gs.factories[i].append(gs.bag.pop())
            else:
                gs.lid_to_bag()
                if gs.bag:
                    gs.factories[i].append(gs.bag.pop())


def run_simulation(bot1, bot2, gs, rng):
    game = copy.deepcopy(gs)
    fill_factories_from_bag(game, rng)
    turn = 0
    while not game.game_over:
        player = game.current_player
        bot = bot1 if player == 0 else bot2
        move = bot.select_move(game, player)
        if move is None:
            break
        action_type, *args = move
        if action_type == "center":
            _, _, color_val, line_val = move
            args = (color_val, line_val)
        game.current_player_action(action_type, *args)
        turn += 1
        if game.phase == "wall_tiling":
            game.resolve_wall_tiling()
    snap = game.get_state_snapshot()
    return {
        "score1": snap["players"][0]["score"],
        "score2": snap["players"][1]["score"],
        "winner": snap["winner"],
        "rounds": snap["round"],
        "total_turns": turn,
    }


def main():
    N = 100
    BASE_SEED = 999

    print("=== Mid-game simulation: 12 wall tiles pre-placed ===")
    print()

    greedy_wins = 0
    planned_wins = 0
    random_wins_g = 0
    random_wins_p = 0
    g_scores = []
    p_scores = []
    r_scores_g = []
    r_scores_p = []

    for game_id in range(N):
        seed = BASE_SEED + game_id

        base_state = generate_midgame_state(seed * 2, num_wall_tiles=12)

        gs_g = copy.deepcopy(base_state)
        rng_g = random.Random(seed * 2 + 1)
        fill_factories_from_bag(gs_g, rng_g)

        gs_p = copy.deepcopy(base_state)
        rng_p = random.Random(seed * 2 + 1)
        fill_factories_from_bag(gs_p, rng_p)

        result_g = run_simulation(GreedyBot(), RandomBot(), gs_g, rng_g)
        result_p = run_simulation(PlannedBot(), RandomBot(), gs_p, rng_p)

        g_scores.append(result_g["score1"])
        r_scores_g.append(result_g["score2"])
        p_scores.append(result_p["score1"])
        r_scores_p.append(result_p["score2"])

        if result_g["winner"] == 0:
            greedy_wins += 1
        if result_p["winner"] == 0:
            planned_wins += 1
        if result_g["winner"] == 1:
            random_wins_g += 1
        if result_p["winner"] == 1:
            random_wins_p += 1

        if (game_id + 1) % 10 == 0 or game_id == 0:
            print(f"[{(game_id + 1):>3}/{N}] G:{result_g['score1']}-{result_g['score2']}  "
                  f"P:{result_p['score1']}-{result_p['score2']}")

    print()
    print("=" * 60)
    print("RESULTS (mid-game start, 12 wall tiles pre-placed, same factories)")
    print("=" * 60)
    print()
    print(f"GreedyBot vs RandomBot:")
    print(f"  Greedy wins: {greedy_wins}, Random wins: {random_wins_g}, Draws: {N - greedy_wins - random_wins_g}")
    print(f"  Avg Greedy score: {sum(g_scores) / N:.1f}")
    print(f"  Avg Random score: {sum(r_scores_g) / N:.1f}")
    print()
    print(f"PlannedBot vs RandomBot:")
    print(f"  Planned wins: {planned_wins}, Random wins: {random_wins_p}, Draws: {N - planned_wins - random_wins_p}")
    print(f"  Avg Planned score: {sum(p_scores) / N:.1f}")
    print(f"  Avg Random score: {sum(r_scores_p) / N:.1f}")
    print()


if __name__ == "__main__":
    main()
