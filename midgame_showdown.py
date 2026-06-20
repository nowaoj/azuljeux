import random
import copy
from game import GameState, Color, WALL_LAYOUT, FACTORY_COUNT, COLOR_NAMES
from bots import GreedyBot, PlannedBot, FixedPriorityOpponent

# Unique color abbreviations
COLOR_SHORT = {Color.BLUE: "Bl", Color.YELLOW: "Ye", Color.RED: "Rd",
               Color.BLACK: "Bk", Color.WHITE: "Wh"}


def generate_midgame_state(seed):
    rng = random.Random(seed)
    gs = GameState()
    gs.init_bag()
    gs.round = rng.randint(2, 4)
    gs.current_player = 0
    gs.starting_player = 0
    gs.phase = "factory_offer"

    all_pos = [(r, c) for r in range(5) for c in range(5)]
    rng.shuffle(all_pos)
    num = rng.randint(6, 14)
    player = 0
    taken = 0
    for r, c in all_pos:
        if taken >= num:
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
                tile = gs.players[p].wall[r][c]
                if tile is None:
                    continue
                hor = 1
                cc = c - 1
                while cc >= 0 and gs.players[p].wall[r][cc] is not None:
                    hor += 1; cc -= 1
                cc = c + 1
                while cc < 5 and gs.players[p].wall[r][cc] is not None:
                    hor += 1; cc += 1
                ver = 1
                rr = r - 1
                while rr >= 0 and gs.players[p].wall[rr][c] is not None:
                    ver += 1; rr -= 1
                rr = r + 1
                while rr < 5 and gs.players[p].wall[rr][c] is not None:
                    ver += 1; rr += 1
                if hor == 1 and ver == 1:
                    score += 1
                elif hor > 1 and ver == 1:
                    score += hor
                elif ver > 1 and hor == 1:
                    score += ver
                else:
                    score += hor + ver
        gs.players[p].score = score

    gs.taken_from_center = [False, False]
    gs.center = ["START"]
    return gs


def fill_factories(gs, rng):
    for i in range(FACTORY_COUNT):
        gs.factories[i] = []
        for _ in range(4):
            if gs.bag:
                gs.factories[i].append(gs.bag.pop())
            else:
                gs.lid_to_bag()
                if gs.bag:
                    gs.factories[i].append(gs.bag.pop())


def wall_display(wall):
    lines = []
    for r in range(5):
        cells = []
        for c in range(5):
            tile = wall[r][c]
            target = WALL_LAYOUT[r][c]
            if tile is not None:
                cells.append(COLOR_SHORT[tile].upper())
            else:
                cells.append(COLOR_SHORT[target].lower())
        lines.append(" ".join(cells))
    return lines


def print_board(game, label="STATE"):
    p0, p1 = game.players
    print(f"  +- {label} {'-'*40}+")
    print(f"  | Round {game.round}  |  P{game.current_player}'s turn  |  Scores: {p0.score} vs {p1.score}")
    print()

    for i, f in enumerate(game.factories):
        if f:
            tiles = [COLOR_SHORT[t] for t in f]
            print(f"    F{i}: {' '.join(tiles)}")
        else:
            print(f"    F{i}: —")
    center_str = " ".join(COLOR_SHORT[t] if isinstance(t, Color) else "ST" for t in game.center)
    print(f"    CTR: {center_str}")
    print()

    for p_idx in range(2):
        p = game.players[p_idx]
        who = "US" if p_idx == 0 else "OP"
        wall_lines = wall_display(p.wall)
        print(f"  +- P{p_idx} ({who})  score={p.score}")
        for li in range(5):
            pl = "".join(COLOR_SHORT[t] for t in p.pattern_lines[li])
            cap = li + 1
            fill = len(p.pattern_lines[li])
            bar = "#" * fill + "." * (cap - fill)
            print(f"  | L{li} [{bar}] {pl:<8}  | wall: {wall_lines[li]}")
        fl = " ".join(COLOR_SHORT[t] if isinstance(t, Color) else "ST" for t in p.floor_line)
        print(f"  | Floor: [{fl if fl else '--'}]")
        print()
    print()


def apply_move(game, move):
    if move.source_type == "center":
        game.current_player_action("center", move.color, move.line_idx)
    else:
        game.current_player_action("factory", move.source_idx, move.color, move.line_idx)


def play_full_game(bot0, bot1, game):
    turn = 0
    while not game.game_over:
        player = game.current_player
        bot = bot0 if player == 0 else bot1
        move = bot.choose_move(game, player)
        if move is None:
            break
        apply_move(game, move)
        turn += 1
        if game.phase == "wall_tiling":
            game.resolve_wall_tiling()
    snap = game.get_state_snapshot()
    return snap, turn


def main():
    seed = random.randint(0, 9999)
    print("=" * 72)
    print("  MIDGAME SHOWDOWN")
    print("  Three bots start from an identical midgame position")
    print("  and play a full game against GreedyBot.")
    print("=" * 72)
    print()

    base_state = generate_midgame_state(seed)
    rng = random.Random(seed + 1)
    fill_factories(base_state, rng)

    print_board(base_state, "STARTING POSITION (seed={})".format(seed))

    bots = [
        ("GreedyBot", GreedyBot()),
        ("PlannedBot", PlannedBot()),
        ("FixedPriorityOpponent", FixedPriorityOpponent()),
    ]

    results = []
    for name, bot in bots:
        game = copy.deepcopy(base_state)
        print(f"  +{'='*68}+")
        print(f"  |  {name} (P0) vs GreedyBot (P1)")
        print(f"  +{'='*68}+")
        print()

        snap, total_turns = play_full_game(bot, GreedyBot(), game)

        s0, s1 = snap["players"][0]["score"], snap["players"][1]["score"]
        w = snap["winner"]
        label = "WINS" if w == 0 else "LOSS" if w == 1 else "DRAW"
        print(f"  +- FINAL  Round {snap['round']}  |  {s0} - {s1}  |  {name} {label}")
        print()
        results.append((name, s0, s1, label))

        # Show final boards
        p0_wall = wall_display(game.players[0].wall)
        p1_wall = wall_display(game.players[1].wall)
        print(f"    P0 ({name}) wall:")
        for r in range(5):
            print(f"      {p0_wall[r]}")
        print(f"    P1 (GreedyBot) wall:")
        for r in range(5):
            print(f"      {p1_wall[r]}")
        print(f"    Turns played: {total_turns}")
        print()

    print("=" * 72)
    print("  HEAD-TO-HEAD SUMMARY")
    print("=" * 72)
    print(f"  {'Bot':<28} {'Score':>8}  {'Result':>10}")
    print(f"  {'-'*28} {'-'*8}  {'-'*10}")
    for name, s0, _, label in results:
        print(f"  {name:<28} {s0:>5} vs Greedy  {label:>10}")
    print()


if __name__ == "__main__":
    main()
