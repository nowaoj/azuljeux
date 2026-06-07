import random
from enum import IntEnum

class Color(IntEnum):
    BLUE = 0
    YELLOW = 1
    RED = 2
    BLACK = 3
    WHITE = 4

COLOR_NAMES = {
    Color.BLUE: "blue",
    Color.YELLOW: "yellow",
    Color.RED: "red",
    Color.BLACK: "black",
    Color.WHITE: "white",
}

COLOR_RGB = {
    Color.BLUE: (0, 120, 200),
    Color.YELLOW: (240, 200, 0),
    Color.RED: (200, 30, 30),
    Color.BLACK: (40, 40, 40),
    Color.WHITE: (220, 220, 210),
}

WALL_LAYOUT = [
    [Color.BLUE, Color.YELLOW, Color.RED, Color.BLACK, Color.WHITE],
    [Color.WHITE, Color.BLUE, Color.YELLOW, Color.RED, Color.BLACK],
    [Color.BLACK, Color.WHITE, Color.BLUE, Color.YELLOW, Color.RED],
    [Color.RED, Color.BLACK, Color.WHITE, Color.BLUE, Color.YELLOW],
    [Color.YELLOW, Color.RED, Color.BLACK, Color.WHITE, Color.BLUE],
]

FLOOR_PENALTIES = [-1, -1, -2, -2, -2, -3, -3]
FACTORY_COUNT = 5
TILES_PER_COLOR = 20

class PlayerBoard:
    def __init__(self):
        self.pattern_lines = [[] for _ in range(5)]
        self.wall = [[None] * 5 for _ in range(5)]
        self.floor_line = []
        self.score = 0

    def can_place_in_pattern(self, line_idx, color):
        if line_idx < 0 or line_idx > 4:
            return False
        line = self.pattern_lines[line_idx]
        max_size = line_idx + 1
        if len(line) >= max_size:
            return False
        if len(line) > 0 and line[0] != color:
            return False
        wall_col = -1
        for c in range(5):
            if WALL_LAYOUT[line_idx][c] == color:
                wall_col = c
                break
        if wall_col >= 0 and self.wall[line_idx][wall_col] is not None:
            return False
        return True

    def add_to_pattern(self, line_idx, tiles):
        if not tiles:
            return []
        color = tiles[0]
        line = self.pattern_lines[line_idx]
        max_size = line_idx + 1
        space_left = max_size - len(line)
        to_place = tiles[:space_left]
        overflow = tiles[space_left:]
        line.extend(to_place)
        return overflow

    def wall_color_at(self, line_idx, col_idx):
        return WALL_LAYOUT[line_idx][col_idx]

    def get_wall_target_col(self, line_idx, color):
        for c in range(5):
            if WALL_LAYOUT[line_idx][c] == color:
                return c
        return -1

    def place_on_wall(self, line_idx):
        line = self.pattern_lines[line_idx]
        if len(line) != line_idx + 1:
            return 0
        color = line[0]
        col = self.get_wall_target_col(line_idx, color)
        if col < 0 or self.wall[line_idx][col] is not None:
            return 0
        self.wall[line_idx][col] = color
        self.pattern_lines[line_idx] = []
        return self._score_wall_placement(line_idx, col)

    def discard_floor(self):
        penalty = 0
        for i, tile in enumerate(self.floor_line):
            if i < len(FLOOR_PENALTIES):
                penalty += FLOOR_PENALTIES[i]
        self.floor_line = []
        return penalty

    def _score_wall_placement(self, row, col):
        score = 0
        hor_count = 1
        c = col - 1
        while c >= 0 and self.wall[row][c] is not None:
            hor_count += 1
            c -= 1
        c = col + 1
        while c < 5 and self.wall[row][c] is not None:
            hor_count += 1
            c += 1

        ver_count = 1
        r = row - 1
        while r >= 0 and self.wall[r][col] is not None:
            ver_count += 1
            r -= 1
        r = row + 1
        while r < 5 and self.wall[r][col] is not None:
            ver_count += 1
            r += 1

        if hor_count == 1 and ver_count == 1:
            score = 1
        elif hor_count > 1 and ver_count == 1:
            score = hor_count
        elif ver_count > 1 and hor_count == 1:
            score = ver_count
        else:
            score = hor_count + ver_count

        self.score += score
        return score

    def has_complete_row(self):
        for r in range(5):
            if all(self.wall[r][c] is not None for c in range(5)):
                return True
        return False

    def count_horizontal_rows(self):
        count = 0
        for r in range(5):
            if all(self.wall[r][c] is not None for c in range(5)):
                count += 1
        return count

    def count_vertical_cols(self):
        count = 0
        for c in range(5):
            if all(self.wall[r][c] is not None for r in range(5)):
                count += 1
        return count

    def count_full_colors(self):
        count = 0
        for color in Color:
            found = True
            for r in range(5):
                row_has = False
                for c in range(5):
                    if WALL_LAYOUT[r][c] == color and self.wall[r][c] is not None:
                        row_has = True
                        break
                if not row_has:
                    found = False
                    break
            if found:
                count += 1
        return count


class GameState:
    def __init__(self, seed=None):
        self.players = [PlayerBoard(), PlayerBoard()]
        self.factories = [[] for _ in range(FACTORY_COUNT)]
        self.center = []
        self.starting_player = 0
        self.current_player = 0
        self.bag = []
        self.lid = []
        self.phase = "factory_offer"
        self.round = 1
        self.last_round = False
        self.game_over = False
        self.winner = -1
        self.taken_from_center = [False, False]

    def init_bag(self):
        self.bag = []
        colors = list(Color)
        for _ in range(TILES_PER_COLOR):
            for color in colors:
                self.bag.append(color)
        random.shuffle(self.bag)

    def fill_factories(self):
        for i in range(FACTORY_COUNT):
            self.factories[i] = []
            for _ in range(4):
                if self.bag:
                    self.factories[i].append(self.bag.pop())
                else:
                    self.lid_to_bag()
                    if self.bag:
                        self.factories[i].append(self.bag.pop())

    def start_round(self):
        self.center = ["START"]
        self.taken_from_center = [False, False]
        self.fill_factories()

    def lid_to_bag(self):
        if not self.lid:
            return
        self.bag.extend(self.lid)
        self.lid = []
        random.shuffle(self.bag)

    def can_take_from_factory(self, player_idx, factory_idx, color):
        if self.phase != "factory_offer":
            return False
        if player_idx != self.current_player:
            return False
        if factory_idx < 0 or factory_idx >= FACTORY_COUNT:
            return False
        factory = self.factories[factory_idx]
        if not factory:
            return False
        return color in factory

    def can_take_from_center(self, player_idx, color):
        if self.phase != "factory_offer":
            return False
        if player_idx != self.current_player:
            return False
        if not self.center:
            return False
        return color in self.center

    def take_from_factory(self, player_idx, factory_idx, color):
        if not self.can_take_from_factory(player_idx, factory_idx, color):
            return None
        factory = self.factories[factory_idx]
        taken = [t for t in factory if t == color]
        moved = [t for t in factory if t != color]
        self.center.extend(moved)
        self.factories[factory_idx] = []
        return taken

    def take_from_center(self, player_idx, color):
        if not self.can_take_from_center(player_idx, color):
            return None
        taken = [t for t in self.center if t == color]
        self.center = [t for t in self.center if t != color]
        got_start = False
        if not self.taken_from_center[player_idx]:
            self.taken_from_center[player_idx] = True
            if "START" in self.center:
                self.center.remove("START")
                got_start = True
        return taken, got_start

    def place_tiles_on_pattern(self, player_idx, line_idx, tiles):
        if line_idx < 0 or line_idx > 4:
            return tiles
        player = self.players[player_idx]
        if not tiles:
            return tiles
        color = tiles[0]
        if not player.can_place_in_pattern(line_idx, color):
            return tiles
        return player.add_to_pattern(line_idx, tiles)

    def place_on_floor(self, player_idx, tiles):
        player = self.players[player_idx]
        space = 7 - len(player.floor_line)
        to_floor = tiles[:space]
        player.floor_line.extend(to_floor)
        overflow = tiles[space:]
        self.lid.extend(overflow)
        return to_floor

    def current_player_action(self, action_type, *args):
        if action_type == "factory":
            factory_idx, color, line_idx = args
            tiles = self.take_from_factory(self.current_player, factory_idx, color)
            if tiles is None:
                return False
            if line_idx >= 0:
                overflow = self.place_tiles_on_pattern(self.current_player, line_idx, tiles)
                if overflow:
                    self.place_on_floor(self.current_player, overflow)
            else:
                self.place_on_floor(self.current_player, tiles)
            self.advance_turn()
            return True
        elif action_type == "center":
            color, line_idx = args
            result = self.take_from_center(self.current_player, color)
            if result is None:
                return False
            tiles, got_start = result
            if got_start:
                self.players[self.current_player].floor_line.append("START")
            if line_idx >= 0:
                overflow = self.place_tiles_on_pattern(self.current_player, line_idx, tiles)
                if overflow:
                    self.place_on_floor(self.current_player, overflow)
            else:
                self.place_on_floor(self.current_player, tiles)
            self.advance_turn()
            return True
        return False

    def advance_turn(self):
        if self._is_phase_over():
            self.start_wall_tiling()
            return
        self.current_player = 1 - self.current_player

    def _is_phase_over(self):
        for f in self.factories:
            if f:
                return False
        center_tiles = [t for t in self.center if t != "START"]
        if center_tiles:
            return False
        return True

    def start_wall_tiling(self):
        self.phase = "wall_tiling"

    def resolve_wall_tiling(self):
        for p in range(2):
            player = self.players[p]
            for line_idx in range(5):
                if len(player.pattern_lines[line_idx]) == line_idx + 1:
                    player.place_on_wall(line_idx)
            penalty = player.discard_floor()
            player.score = max(0, player.score + penalty)
        self.check_end_game()
        if not self.game_over:
            self.prepare_next_round()

    def check_end_game(self):
        for p in range(2):
            if self.players[p].has_complete_row():
                self.last_round = True
        if self.last_round:
            self.game_over = True
            self.calculate_final_scores()

    def calculate_final_scores(self):
        for p in range(2):
            player = self.players[p]
            player.score += player.count_horizontal_rows() * 2
            player.score += player.count_vertical_cols() * 7
            player.score += player.count_full_colors() * 10
        if self.players[0].score > self.players[1].score:
            self.winner = 0
        elif self.players[1].score > self.players[0].score:
            self.winner = 1
        else:
            h0 = self.players[0].count_horizontal_rows()
            h1 = self.players[1].count_horizontal_rows()
            if h0 > h1:
                self.winner = 0
            elif h1 > h0:
                self.winner = 1
            else:
                self.winner = -1

    def prepare_next_round(self):
        self.phase = "factory_offer"
        self.round += 1
        self.starting_player = 1 - self.starting_player
        self.current_player = self.starting_player
        self.start_round()

    def get_state_snapshot(self):
        return {
            "factories": [[c.value for c in f] for f in self.factories],
            "center": [c if isinstance(c, str) else c.value for c in self.center],
            "players": [
                {
                    "pattern_lines": [[c.value for c in pl] for pl in self.players[i].pattern_lines],
                    "wall": [[c.value if c is not None else None for c in row] for row in self.players[i].wall],
                    "floor_line": [c.value if isinstance(c, Color) else c for c in self.players[i].floor_line],
                    "score": self.players[i].score,
                }
                for i in range(2)
            ],
            "current_player": self.current_player,
            "starting_player": self.starting_player,
            "phase": self.phase,
            "round": self.round,
            "game_over": self.game_over,
            "winner": self.winner,
        }

    def load_state_snapshot(self, snapshot):
        self.factories = [[Color(c) for c in f] for f in snapshot["factories"]]
        self.center = []
        for c in snapshot["center"]:
            if isinstance(c, str):
                self.center.append(c)
            else:
                self.center.append(Color(c))
        for i in range(2):
            p = snapshot["players"][i]
            self.players[i].pattern_lines = [[Color(c) for c in pl] for pl in p["pattern_lines"]]
            self.players[i].wall = [[Color(c) if c is not None else None for c in row] for row in p["wall"]]
            self.players[i].floor_line = []
            for c in p["floor_line"]:
                if isinstance(c, str):
                    self.players[i].floor_line.append(c)
                else:
                    self.players[i].floor_line.append(Color(c))
            self.players[i].score = p["score"]
        self.current_player = snapshot["current_player"]
        self.starting_player = snapshot["starting_player"]
        self.phase = snapshot["phase"]
        self.round = snapshot["round"]
        self.game_over = snapshot["game_over"]
        self.winner = snapshot["winner"]
