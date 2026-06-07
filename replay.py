import sys
import csv
import pygame
from game import Color, FACTORY_COUNT, WALL_LAYOUT, FLOOR_PENALTIES
from ui import AzulUI


COLOR_VAL_MAP = {
    "blue": Color.BLUE,
    "yellow": Color.YELLOW,
    "red": Color.RED,
    "black": Color.BLACK,
    "white": Color.WHITE,
}


def load_moves(filepath, game_id=0):
    moves = []
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(row["game_id"]) != game_id:
                continue
            moves.append({
                "turn": int(row["turn"]),
                "player": int(row["player"]),
                "action_type": row["action_type"],
                "source_idx": int(row["source_idx"]),
                "color": row["color"],
                "line_idx": int(row["line_idx"]),
                "score_p1_before": int(row["score_p1_before"]),
                "score_p2_before": int(row["score_p2_before"]),
            })
    return moves


def get_wall_target_col(line_idx, color):
    for c in range(5):
        if WALL_LAYOUT[line_idx][c] == color:
            return c
    return -1


class ReplayState:
    def __init__(self, moves):
        self.moves = moves
        self.snapshots = []
        self._build()

    def _build(self):
        factories = [[] for _ in range(FACTORY_COUNT)]
        center = []
        pattern_lines = [[[] for _ in range(5)] for _ in range(2)]
        wall = [[[None] * 5 for _ in range(5)] for _ in range(2)]
        floor_line = [[], []]
        scores = [0, 0]
        current_player = 0
        starting_player = 0
        round_num = 1
        phase = "factory_offer"
        taken_from_center = [False, False]
        turn = 0
        game_over = False
        winner = -1

        round_boundaries = self._find_round_boundaries()

        for rbi, round_start in enumerate(round_boundaries):
            if game_over:
                break

            round_end = self._get_round_end(round_start)
            round_moves = self.moves[round_start:round_end]

            if rbi > 0 or round_start > 0:
                for p in range(2):
                    for li in range(5):
                        if len(pattern_lines[p][li]) == li + 1:
                            color = pattern_lines[p][li][0]
                            col = get_wall_target_col(li, color)
                            if col >= 0 and wall[p][li][col] is None:
                                wall[p][li][col] = color
                            pattern_lines[p][li] = []
                    penalty = 0
                    for i, t in enumerate(floor_line[p]):
                        if i < len(FLOOR_PENALTIES):
                            if isinstance(t, Color):
                                penalty += FLOOR_PENALTIES[i]
                            elif t != "START":
                                penalty += FLOOR_PENALTIES[i]
                    scores[p] = max(0, scores[p] + penalty)
                    floor_line[p] = []

                round_num += 1
                starting_player = 1 - starting_player
                current_player = starting_player
                phase = "factory_offer"
                taken_from_center = [False, False]

                for p in range(2):
                    if all(wall[p][r][c] is not None for c in range(5) for r in [p]):
                        pass
                    for r in range(5):
                        if all(wall[p][r][c] is not None for c in range(5)):
                            game_over = True
                            for pp in range(2):
                                h_count = sum(1 for r2 in range(5) if all(wall[pp][r2][c] is not None for c in range(5)))
                                v_count = 0
                                for cc in range(5):
                                    if all(wall[pp][r2][cc] is not None for r2 in range(5)):
                                        v_count += 1
                                fc_count = 0
                                for col in Color:
                                    found = True
                                    for r2 in range(5):
                                        row_has = False
                                        for cc in range(5):
                                            if WALL_LAYOUT[r2][cc] == col and wall[pp][r2][cc] is not None:
                                                row_has = True
                                                break
                                        if not row_has:
                                            found = False
                                            break
                                    if found:
                                        fc_count += 1
                                scores[pp] += h_count * 2 + v_count * 7 + fc_count * 10
                            if scores[0] > scores[1]:
                                winner = 0
                            elif scores[1] > scores[0]:
                                winner = 1
                            else:
                                h0 = sum(1 for r in range(5) if all(wall[0][r][c] is not None for c in range(5)))
                                h1 = sum(1 for r in range(5) if all(wall[1][r][c] is not None for c in range(5)))
                                winner = 0 if h0 > h1 else 1 if h1 > h0 else -1
                            break
                    if game_over:
                        break

            factory_colors_taken = {}
            center_colors_seen = set()
            for mv in round_moves:
                if mv["action_type"] == "factory":
                    factory_colors_taken[mv["source_idx"]] = mv["color"]
                center_colors_seen.add(mv["color"])

            filler_pool = list(center_colors_seen)
            if not filler_pool:
                filler_pool = list(COLOR_VAL_MAP.keys())
            fi = 0
            for fi_idx in range(FACTORY_COUNT):
                if fi_idx in factory_colors_taken:
                    c = COLOR_VAL_MAP[factory_colors_taken[fi_idx]]
                    factories[fi_idx] = [Color(c)]
                    for _ in range(3):
                        factories[fi_idx].append(COLOR_VAL_MAP[filler_pool[fi % len(filler_pool)]])
                        fi += 1
                else:
                    factories[fi_idx] = []
                    for _ in range(4):
                        factories[fi_idx].append(COLOR_VAL_MAP[filler_pool[fi % len(filler_pool)]])
                        fi += 1

            center = ["START"]

            for mv in round_moves:
                player = mv["player"]
                color_name = mv["color"]
                color_val = COLOR_VAL_MAP[color_name]
                action_type = mv["action_type"]
                source_idx = mv["source_idx"]
                line_idx = mv["line_idx"]

                if player == 0:
                    scores[0] = mv["score_p1_before"]
                else:
                    scores[1] = mv["score_p2_before"]

                if action_type == "factory":
                    factory = factories[source_idx]
                    taken = [t for t in factory if t == color_val]
                    spill = [t for t in factory if t != color_val]
                    center.extend(spill)
                    factories[source_idx] = []
                else:
                    real_tiles = [t for t in center if not isinstance(t, str)]
                    taken = [t for t in real_tiles if t == color_val]
                    center = [t for t in center if not isinstance(t, str) and t != color_val]
                    if not taken_from_center[player]:
                        taken_from_center[player] = True
                        if "START" in center:
                            center.remove("START")

                if line_idx >= 0:
                    pl = pattern_lines[player][line_idx]
                    max_size = line_idx + 1
                    space = max_size - len(pl)
                    to_place = taken[:space]
                    overflow = taken[space:]
                    pl.extend(to_place)
                    if overflow:
                        fl = floor_line[player]
                        fl_space = 7 - len(fl)
                        fl.extend(overflow[:fl_space])
                else:
                    fl = floor_line[player]
                    fl_space = 7 - len(fl)
                    fl.extend(taken[:fl_space])

                self._save_snapshot(turn, mv, factories, center, pattern_lines, wall,
                                    floor_line, scores, current_player, round_num, phase,
                                    game_over, winner)
                current_player = 1 - current_player
                turn += 1

        for p in range(2):
            for li in range(5):
                if len(pattern_lines[p][li]) == li + 1:
                    color = pattern_lines[p][li][0]
                    col = get_wall_target_col(li, color)
                    if col >= 0 and wall[p][li][col] is None:
                        wall[p][li][col] = color
                    pattern_lines[p][li] = []
            penalty = 0
            for i, t in enumerate(floor_line[p]):
                if i < len(FLOOR_PENALTIES):
                    if isinstance(t, Color):
                        penalty += FLOOR_PENALTIES[i]
                    elif t != "START":
                        penalty += FLOOR_PENALTIES[i]
            scores[p] = max(0, scores[p] + penalty)
            floor_line[p] = []

        if not game_over:
            for p in range(2):
                for r in range(5):
                    if all(wall[p][r][c] is not None for c in range(5)):
                        game_over = True
                        break
                if game_over:
                    break
            if game_over:
                for pp in range(2):
                    h_count = sum(1 for r2 in range(5) if all(wall[pp][r2][c] is not None for c in range(5)))
                    v_count = sum(1 for cc in range(5) if all(wall[pp][r2][cc] is not None for r2 in range(5)))
                    fc_count = 0
                    for col in Color:
                        found = True
                        for r2 in range(5):
                            row_has = False
                            for cc in range(5):
                                if WALL_LAYOUT[r2][cc] == col and wall[pp][r2][cc] is not None:
                                    row_has = True
                                    break
                            if not row_has:
                                found = False
                                break
                        if found:
                            fc_count += 1
                    scores[pp] += h_count * 2 + v_count * 7 + fc_count * 10
                if scores[0] > scores[1]:
                    winner = 0
                elif scores[1] > scores[0]:
                    winner = 1
                else:
                    h0 = sum(1 for r in range(5) if all(wall[0][r][c] is not None for c in range(5)))
                    h1 = sum(1 for r in range(5) if all(wall[1][r][c] is not None for c in range(5)))
                    winner = 0 if h0 > h1 else 1 if h1 > h0 else -1

        self._save_final_snapshot(turn, factories, center, pattern_lines, wall,
                                  floor_line, scores, round_num, game_over, winner)

    def _save_snapshot(self, turn, mv, factories, center, pattern_lines, wall,
                       floor_line, scores, current_player, round_num, phase,
                       game_over, winner):
        snapshot = self._make_state_snapshot(factories, center, pattern_lines, wall,
                                              floor_line, scores, current_player,
                                              round_num, phase, game_over, winner)

        action_desc = f"P{mv['player']} takes {mv['color']} from "
        if mv["action_type"] == "factory":
            action_desc += f"F{mv['source_idx'] + 1}"
        else:
            action_desc += "center"
        if mv["line_idx"] >= 0:
            action_desc += f" -> line {mv['line_idx'] + 1}"
        else:
            action_desc += " -> floor"

        self.snapshots.append({
            "step": turn,
            "action": action_desc,
            "state": snapshot,
        })

    def _save_final_snapshot(self, turn, factories, center, pattern_lines, wall,
                              floor_line, scores, round_num, game_over, winner):
        snapshot = self._make_state_snapshot(factories, center, pattern_lines, wall,
                                              floor_line, scores, 0, round_num,
                                              "game_over", True, winner)
        self.snapshots.append({
            "step": turn,
            "action": "Game over",
            "state": snapshot,
        })

    def _make_state_snapshot(self, factories, center, pattern_lines, wall,
                              floor_line, scores, current_player, round_num,
                              phase, game_over, winner):
        center_out = []
        for c in center:
            if isinstance(c, str):
                center_out.append(c)
            else:
                center_out.append(c.value)

        return {
            "factories": [[c.value for c in f] for f in factories],
            "center": center_out,
            "players": [
                {
                    "pattern_lines": [[c.value for c in pl] for pl in pattern_lines[0]],
                    "wall": [[c.value if c is not None else None for c in row] for row in wall[0]],
                    "floor_line": [c.value if isinstance(c, Color) else c for c in floor_line[0]],
                    "score": scores[0],
                },
                {
                    "pattern_lines": [[c.value for c in pl] for pl in pattern_lines[1]],
                    "wall": [[c.value if c is not None else None for c in row] for row in wall[1]],
                    "floor_line": [c.value if isinstance(c, Color) else c for c in floor_line[1]],
                    "score": scores[1],
                },
            ],
            "current_player": current_player,
            "starting_player": current_player,
            "phase": phase,
            "round": round_num,
            "game_over": game_over,
            "winner": winner,
        }

    def _find_round_boundaries(self):
        boundaries = [0]
        for i in range(1, len(self.moves)):
            prev = self.moves[i - 1]
            cur = self.moves[i]
            if (cur["score_p1_before"] != prev["score_p1_before"] or
                cur["score_p2_before"] != prev["score_p2_before"]):
                boundaries.append(i)
        return boundaries

    def _get_round_end(self, start_idx):
        for i in range(start_idx + 1, len(self.moves)):
            prev = self.moves[i - 1]
            cur = self.moves[i]
            if (cur["score_p1_before"] != prev["score_p1_before"] or
                cur["score_p2_before"] != prev["score_p2_before"]):
                return i
        return len(self.moves)

    def get_snapshot(self, idx):
        if 0 <= idx < len(self.snapshots):
            return self.snapshots[idx]
        return None

    def total_steps(self):
        return len(self.snapshots)


def main():
    filepath = "moves_planned_vs_random.csv"
    game_id = 0

    if len(sys.argv) > 1:
        game_id = int(sys.argv[1])
    if len(sys.argv) > 2:
        filepath = sys.argv[2]

    if game_id < 0:
        print("Available games:")
        seen = set()
        with open(filepath, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                gid = int(row["game_id"])
                if gid not in seen:
                    print(f"  Game {gid} - {row['score_p1_before']} vs {row['score_p2_before']}")
                    seen.add(gid)
        return

    print(f"Loading moves for game {game_id} from {filepath}...")
    moves = load_moves(filepath, game_id)
    if not moves:
        print(f"No moves found for game {game_id}")
        return
    print(f"Loaded {len(moves)} moves. Building replay...")

    engine = ReplayState(moves)
    print(f"Built {engine.total_steps()} snapshots.")

    if engine.total_steps() == 0:
        print("No snapshots generated.")
        return

    pygame.init()
    info = pygame.display.Info()
    WIDTH = info.current_w
    HEIGHT = info.current_h

    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
    pygame.display.set_caption(f"Azul Replay - Game {game_id}")
    clock = pygame.time.Clock()

    ui = AzulUI(is_host=True)
    ui.my_player = 0
    ui.opponent = 1
    ui.connected = True
    ui.game_started = True
    ui.screen = screen
    ui.WIDTH = WIDTH
    ui.HEIGHT = HEIGHT
    ui.scale = min(WIDTH / 1280, HEIGHT / 960)

    current_step = 0
    snap = engine.get_snapshot(0)
    if snap:
        ui.set_state(snap["state"])

    font_small = pygame.font.Font(None, 28)
    font_med = pygame.font.Font(None, 36)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_RIGHT:
                    if current_step < engine.total_steps() - 1:
                        current_step += 1
                        snap = engine.get_snapshot(current_step)
                        if snap:
                            ui.set_state(snap["state"])
                elif event.key == pygame.K_LEFT:
                    if current_step > 0:
                        current_step -= 1
                        snap = engine.get_snapshot(current_step)
                        if snap:
                            ui.set_state(snap["state"])
                elif event.key == pygame.K_HOME:
                    current_step = 0
                    snap = engine.get_snapshot(0)
                    if snap:
                        ui.set_state(snap["state"])
                elif event.key == pygame.K_END:
                    current_step = engine.total_steps() - 1
                    snap = engine.get_snapshot(current_step)
                    if snap:
                        ui.set_state(snap["state"])

        ui._draw_game()

        snap = engine.get_snapshot(current_step)
        if snap:
            bar = pygame.Surface((WIDTH, 50))
            bar.set_alpha(210)
            bar.fill((20, 20, 25))
            screen.blit(bar, (0, HEIGHT - 50))

            step_text = font_med.render(
                f"Step {current_step + 1}/{engine.total_steps()}  |  {snap['action']}",
                True, (220, 220, 220),
            )
            screen.blit(step_text, (20, HEIGHT - 42))

            nav = font_small.render(
                "\u2190 \u2192 Navigate   Home/End: jump   Esc: exit",
                True, (150, 150, 150),
            )
            screen.blit(nav, (WIDTH - nav.get_width() - 20, HEIGHT - 40))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
