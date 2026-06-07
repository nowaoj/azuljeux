import random
from game import GameState, Color, COLOR_NAMES, FLOOR_PENALTIES
from bots import GreedyBot, PlannedBot


def print_board(game, turn, player):
    p0, p1 = game.players
    print(f"\n--- Turn {turn} | Player {player} | Round {game.round} | Phase {game.phase} ---")
    print(f"  Score: {p0.score} vs {p1.score}")
    print(f"  Factories:")
    for i, f in enumerate(game.factories):
        if f:
            tiles = [COLOR_NAMES[t] for t in f]
            print(f"    [{i}] {', '.join(tiles)}")
    center = [COLOR_NAMES[t] if isinstance(t, Color) else t for t in game.center]
    print(f"  Center: {center}")
    for p_idx, p in enumerate([p0, p1]):
        print(f"  Player {p_idx}:")
        for li in range(5):
            pl = [COLOR_NAMES[t] for t in p.pattern_lines[li]] if p.pattern_lines[li] else []
            wall_row = [COLOR_NAMES.get(p.wall[li][c], '.') if p.wall[li][c] is not None else
                        COLOR_NAMES.get(game.players[p_idx].wall_color_at(li, c), '_')[:1]
                        for c in range(5)]
            print(f"    L{li}: {''.join(pl):<6}  Wall: {' '.join(wall_row)}")
        fl = [COLOR_NAMES[t] if isinstance(t, Color) else t for t in p.floor_line]
        print(f"    Floor: {', '.join(fl) if fl else '(empty)'}")


def move_desc(move):
    atype, sidx, color, line = move
    cname = COLOR_NAMES.get(color, '?')
    src = f"F{sidx}" if atype == "factory" else "CENTER"
    dest = f"L{line}" if line >= 0 else "FLOOR"
    return f"{src} {cname} → {dest}"


def count_color(tiles, color):
    if isinstance(tiles, list):
        return sum(1 for t in tiles if t == color)
    return 0


def main():
    seed = 245
    random.seed(seed)

    game = GameState()
    game.init_bag()
    game.start_round()

    bot1 = GreedyBot()
    bot2 = PlannedBot()

    turn = 0
    while not game.game_over:
        player = game.current_player
        bot = bot1 if player == 0 else bot2

        print_board(game, turn, player)

        move = bot.select_move(game, player)
        if move is None:
            print(f"  BOT {player} ({bot.name}): No move!")
            break

        scores_before = [game.players[0].score, game.players[1].score]

        action_type, *args = move
        if action_type == "center":
            _, color_val, line_val = args
        else:
            factory_idx, color_val, line_val = args

        cname = COLOR_NAMES.get(color_val, '?')
        src_str = f"factory {args[0]}" if action_type == "factory" else "center"
        tile_count = count_color(game.factories[args[0]], color_val) if action_type == "factory" else count_color([t for t in game.center if isinstance(t, Color)], color_val)
        dest_str = f"line {args[1]}" if args[1] >= 0 else "floor"

        print(f"  BOT {player} ({bot.name}): takes {tile_count}x{cname} from {src_str} → {dest_str}")

        if action_type == "center":
            _, _, color_val2, line_val2 = move
            args = (color_val2, line_val2)
        game.current_player_action(action_type, *args)
        turn += 1

        if game.phase == "wall_tiling":
            print("  --- Wall tiling ---")
            for p_idx in range(2):
                placed = [li for li in range(5) if len(game.players[p_idx].pattern_lines[li]) == li + 1]
                if placed:
                    for li in placed:
                        c = game.players[p_idx].pattern_lines[li][0]
                        print(f"    Player {p_idx} lines full: L{li} color={COLOR_NAMES[c]}")
            scores_before_tiling = [game.players[0].score, game.players[1].score]
            game.resolve_wall_tiling()
            for p_idx in range(2):
                gained = game.players[p_idx].score - scores_before_tiling[p_idx]
                print(f"    Player {p_idx} score: {scores_before_tiling[p_idx]} → {game.players[p_idx].score} (+{gained})")

    print_board(game, turn, game.current_player)
    snap = game.get_state_snapshot()
    print(f"\n=== FINAL ===")
    print(f"Score: {snap['players'][0]['score']} vs {snap['players'][1]['score']}")
    print(f"Bonuses: P0 rows={snap['players'][0]['bonus_rows']} cols={snap['players'][0]['bonus_cols']} colors={snap['players'][0]['bonus_colors']}")
    print(f"         P1 rows={snap['players'][1]['bonus_rows']} cols={snap['players'][1]['bonus_cols']} colors={snap['players'][1]['bonus_colors']}")
    print(f"Winner: {snap['winner']} ({'Greedy' if snap['winner']==0 else 'Planned' if snap['winner']==1 else 'Tie'})")
    print(f"Rounds: {snap['round']}, Turns: {turn}")


if __name__ == "__main__":
    main()
