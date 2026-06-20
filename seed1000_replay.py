import random
from game import GameState, Color, WALL_LAYOUT, COLOR_NAMES
from bots import GreedyBot, PlannedBot, FixedPriorityOpponent

COLOR_SHORT = {Color.BLUE: "Bl", Color.YELLOW: "Ye", Color.RED: "Rd",
               Color.BLACK: "Bk", Color.WHITE: "Wh"}

def wall_display(wall):
    return [" ".join(COLOR_SHORT[wall[r][c]].upper() if wall[r][c] else COLOR_SHORT[WALL_LAYOUT[r][c]].lower() for c in range(5)) for r in range(5)]

def show(game, turn, move, bot_name, player):
    p0, p1 = game.players
    print(f"  +- Turn {turn}  P{player} ({bot_name}) {'-'*50}+")
    print(f"  | Round {game.round}  Scores: {p0.score} vs {p1.score}")
    for i, f in enumerate(game.factories):
        print(f"  | F{i}: {' '.join(COLOR_SHORT[t] for t in f) if f else '--'}")
    print(f"  | CTR: {' '.join(COLOR_SHORT[t] if isinstance(t, Color) else 'ST' for t in game.center)}")
    if move:
        src = f"F{move.source_idx}" if move.source_type == "factory" else "CTR"
        dest = f"L{move.line_idx}" if move.line_idx >= 0 else "FLOOR"
        print(f"  | >>> {COLOR_SHORT[move.color]} from {src} -> {dest}")
    for p_idx in range(2):
        p = game.players[p_idx]
        wall_lines = wall_display(p.wall)
        print(f"  | P{p_idx} ({'US' if p_idx==player else 'OP'}) score={p.score}")
        for li in range(5):
            pl = "".join(COLOR_SHORT[t] for t in p.pattern_lines[li])
            fill = len(p.pattern_lines[li])
            print(f"  |   L{li} [{'#'*fill}{'.'*(li+1-fill)}] {pl:<8}  wall: {wall_lines[li]}")
        fl = " ".join(COLOR_SHORT[t] if isinstance(t, Color) else 'ST' for t in p.floor_line) or '--'
        print(f"  |   Floor: [{fl}]")
    print()

def play_and_show(bot0, bot1, label, seed):
    random.seed(seed)
    game = GameState()
    game.init_bag()
    game.start_round()
    print("=" * 72)
    print(f"  {label}  (seed={seed})")
    print("=" * 72)
    turn = 0
    while not game.game_over:
        p = game.current_player
        bot = bot0 if p == 0 else bot1
        move = bot.choose_move(game, p)
        show(game, turn, move, type(bot).__name__, p)
        if move is None: break
        if move.source_type == "center":
            game.current_player_action("center", move.color, move.line_idx)
        else:
            game.current_player_action("factory", move.source_idx, move.color, move.line_idx)
        turn += 1
        if game.phase == "wall_tiling":
            s_before = [game.players[0].score, game.players[1].score]
            game.resolve_wall_tiling()
            print(f"  +- Wall Tiling {'-'*50}+")
            for pi in range(2):
                gained = game.players[pi].score - s_before[pi]
                print(f"  | P{pi} gained {gained} pts (total: {game.players[pi].score})")
            print()
    snap = game.get_state_snapshot()
    print(f"  +- GAME OVER {'-'*50}+")
    print(f"  | Final: {snap['players'][0]['score']} vs {snap['players'][1]['score']}")
    print(f"  | Winner: {'P0' if snap['winner']==0 else 'P1' if snap['winner']==1 else 'TIE'}")
    print()

import sys
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
play_and_show(GreedyBot(), PlannedBot(), "GreedyBot (P0) vs PlannedBot (P1)", seed=seed)
play_and_show(PlannedBot(), FixedPriorityOpponent(), "PlannedBot (P0) vs FixedPriority (P1)", seed=seed)
play_and_show(GreedyBot(), FixedPriorityOpponent(), "GreedyBot (P0) vs FixedPriority (P1)", seed=seed)
