import random
from enum import IntEnum


# ── Tile colours ──────────────────────────────────────────────────────────────
# Official Azul uses five colours: blue, yellow, red, black, white.
# We store them as an IntEnum so they serialise cleanly to/from JSON.

class Color(IntEnum):
    BLUE   = 0
    YELLOW = 1
    RED    = 2
    BLACK  = 3
    WHITE  = 4


COLOR_NAMES = {
    Color.BLUE:   "blue",
    Color.YELLOW: "yellow",
    Color.RED:    "red",
    Color.BLACK:  "black",
    Color.WHITE:  "white",
}

COLOR_RGB = {
    Color.BLUE:   (  0, 120, 200),
    Color.YELLOW: (240, 200,   0),
    Color.RED:    (200,  30,  30),
    Color.BLACK:  ( 40,  40,  40),
    Color.WHITE:  (220, 220, 210),
}


# ── Constants ─────────────────────────────────────────────────────────────────
# Official Azul: 5 factories, 4 tiles each.  20 tiles of each colour = 100.
# The floor line has 7 spaces.  There are 5 pattern-line rows (indices 0-4).

FACTORY_COUNT     = 5
TILES_PER_COLOR   = 20
FLOOR_PENALTIES   = [-1, -1, -2, -2, -2, -3, -3]


# ── Wall layout ───────────────────────────────────────────────────────────────
# Fixed 5×5 wall.  Each row has an ordered permutation of the 5 colours.
# Row i is row i of the wall; column c is the c-th position in that row.
# Indexing: WALL_LAYOUT[row][col] == the colour that belongs in that cell.

WALL_LAYOUT = [
    [Color.BLUE,   Color.YELLOW, Color.RED,    Color.BLACK,  Color.WHITE],
    [Color.WHITE,  Color.BLUE,   Color.YELLOW, Color.RED,    Color.BLACK],
    [Color.BLACK,  Color.WHITE,  Color.BLUE,   Color.YELLOW, Color.RED],
    [Color.RED,    Color.BLACK,  Color.WHITE,  Color.BLUE,   Color.YELLOW],
    [Color.YELLOW, Color.RED,    Color.BLACK,  Color.WHITE,  Color.BLUE],
]


# ═══════════════════════════════════════════════════════════════════════════════
# Player board
# ═══════════════════════════════════════════════════════════════════════════════

class PlayerBoard:
    """One player's board: pattern lines, wall, floor line, and score.

    Official Azul rules implemented here:
      - Pattern lines hold tiles being prepared for the wall.
        Each line i can hold at most i+1 tiles, all of the same colour.
      - The wall is a 5×5 grid.  Each cell belongs to exactly one colour
        (the colour in WALL_LAYOUT at that position).
      - The floor line accumulates penalty tiles (and possibly the START token).
        The first 7 floor spaces have penalties printed on the board.
    """

    def __init__(self):
        self.pattern_lines = [[] for _ in range(5)]   # line i → list of tiles
        self.wall          = [[None] * 5 for _ in range(5)]  # None = empty
        self.floor_line    = []                         # may include "START"
        self.score         = 0


    # ── Pattern-line queries ──────────────────────────────────────────────

    def can_place_in_pattern(self, line_idx: int, color: Color) -> bool:
        """Return True if *color* can legally be added to the given pattern line.

        Conditions:
          1. line_idx must be 0-4.
          2. The pattern line must not already be full (size < max_size).
          3. If the line already has tiles, they must be of the same colour.
          4. That colour must not already be on the wall in that row.
        """
        if line_idx < 0 or line_idx > 4:
            return False
        line     = self.pattern_lines[line_idx]
        max_size = line_idx + 1
        if len(line) >= max_size:
            return False
        if line and line[0] != color:
            return False
        # Check wall: is this colour already placed in this row?
        col = self._wall_col(line_idx, color)
        if col >= 0 and self.wall[line_idx][col] is not None:
            return False
        return True


    def _wall_col(self, row: int, color: Color) -> int:
        """Return the column in *row* that holds *color*, or -1."""
        for c in range(5):
            if WALL_LAYOUT[row][c] == color:
                return c
        return -1


    # ── Adding tiles ──────────────────────────────────────────────────────

    def add_to_pattern(self, line_idx: int, tiles: list[Color]) -> list[Color]:
        """Place *tiles* into the pattern line.  Return overflow (excess tiles).

        If more tiles are given than the line can hold, the extras are
        returned so they can go to the floor line.
        """
        if not tiles:
            return []
        line     = self.pattern_lines[line_idx]
        max_size = line_idx + 1
        space    = max_size - len(line)
        placed   = tiles[:space]
        overflow = tiles[space:]
        line.extend(placed)
        return overflow


    def add_to_floor(self, tiles: list) -> list:
        """Add tile objects (Color or "START") to the floor line at the end.

        The floor line has a physical capacity of 7.  Any extra tiles
        beyond 7 are discarded (returned as overflow).
        """
        space = 7 - len(self.floor_line)
        placed   = tiles[:space]
        overflow = tiles[space:]
        self.floor_line.extend(placed)
        return overflow


    # ── Wall tiling (end of each round) ───────────────────────────────────

    def place_on_wall(self, line_idx: int, lid: list) -> int:
        """Move a completed pattern line (len == line_idx+1) to the wall.

        Rules (official):
          - Only the *rightmost* tile in a full pattern line is placed
            on the wall.  The remaining tiles go to the lid.
          - The tile goes to the cell in that row whose colour matches.
          - Score = 1 for the tile itself plus 1 for each connected tile
            horizontally and vertically (adjacent tiles already on wall).

        Returns the points earned this placement, or 0 if incomplete.
        """
        line = self.pattern_lines[line_idx]
        if len(line) != line_idx + 1:
            return 0
        color = line[0]
        col   = self._wall_col(line_idx, color)
        if col < 0 or self.wall[line_idx][col] is not None:
            return 0
        self.wall[line_idx][col] = color
        # Excess tiles go to the lid instead of being discarded
        lid.extend(line[1:])
        self.pattern_lines[line_idx] = []
        pts = self._score_placement(line_idx, col)
        self.score += pts
        return pts


    def _score_placement(self, row: int, col: int) -> int:
        """Score a wall placement according to official Azul rules.

        Count contiguous tiles horizontally and vertically from (row, col),
        including the newly placed tile itself.

        - If only the new tile (no neighbours on either axis): 1 point.
        - If neighbours only on one axis: length of that contiguous line.
        - If neighbours on both axes: sum of horizontal + vertical lengths.
        """
        # Horizontal
        hor = 1
        c = col - 1
        while c >= 0 and self.wall[row][c] is not None:
            hor += 1; c -= 1
        c = col + 1
        while c < 5 and self.wall[row][c] is not None:
            hor += 1; c += 1
        # Vertical
        ver = 1
        r = row - 1
        while r >= 0 and self.wall[r][col] is not None:
            ver += 1; r -= 1
        r = row + 1
        while r < 5 and self.wall[r][col] is not None:
            ver += 1; r += 1

        if hor == 1 and ver == 1:
            return 1
        if ver == 1:
            return hor
        if hor == 1:
            return ver
        return hor + ver


    def discard_floor(self, lid: list) -> int:
        """Clear the floor line and return the total penalty (negative or 0).

        The first 7 tiles in the floor line each incur a penalty according
        to FLOOR_PENALTIES: -1, -1, -2, -2, -2, -3, -3.
        Extra beyond 7 (overflow from a previous round) are simply discarded
        with no additional penalty.

        Tile colours go to the lid for later recycling.  The START token
        (a unique game marker, not a tile) is simply discarded.
        """
        penalty = 0
        for i in range(min(len(self.floor_line), len(FLOOR_PENALTIES))):
            penalty += FLOOR_PENALTIES[i]
        for item in self.floor_line:
            if isinstance(item, Color):
                lid.append(item)
        self.floor_line = []
        return penalty


    # ── End-game queries ─────────────────────────────────────────────────

    def has_complete_row(self) -> bool:
        """Return True if any horizontal wall row is fully filled."""
        for r in range(5):
            if all(self.wall[r][c] is not None for c in range(5)):
                return True
        return False


    def count_complete_rows(self) -> int:
        return sum(
            1 for r in range(5)
            if all(self.wall[r][c] is not None for c in range(5))
        )

    def count_complete_cols(self) -> int:
        return sum(
            1 for c in range(5)
            if all(self.wall[r][c] is not None for r in range(5))
        )

    def count_complete_colors(self) -> int:
        """Return the number of colours that appear in every row.

        A colour set is complete if that colour tile exists in all 5 rows.
        """
        count = 0
        for color in Color:
            if all(
                any(self.wall[r][c] == color for c in range(5))
                for r in range(5)
            ):
                count += 1
        return count


# ═══════════════════════════════════════════════════════════════════════════════
# Game state
# ═══════════════════════════════════════════════════════════════════════════════

class GameState:
    """Holds the complete state of an Azul game for 2 players.

    Rules overview:
      - 100 tiles (5 colours × 20) are in the bag at game start.
      - Each round: 5 factories are filled with 4 random tiles each.
        A START token is placed in the centre.
      - Players alternate taking one colour from a factory (remaining tiles
        go to the centre) or from the centre.  First to take from centre
        gets the START token on their floor line.
      - Taken tiles may be placed on a pattern line or sent to the floor.
      - When every factory and the centre is empty, wall tiling happens:
        completed pattern lines transfer their tile to the wall; floor
        penalties are applied.
      - The game ends when a player completes a horizontal row on the wall.
        End-game bonuses are added: +2 per complete row, +7 per complete
        column, +10 per complete colour set.
      - Highest score wins; tie-break: most complete rows; then: draw.

    Determinism:
      - The class accepts an optional *seed*.  If provided, a
        `random.Random(seed)` instance is used for all shuffles / draws.
      - If *seed* is None, the module-level `random` is used (not seeded).
    """

    def __init__(self, seed: int | None = None):
        # Random generator for deterministic replay
        self._rng = random.Random(seed) if seed is not None else random

        self.players   = [PlayerBoard(), PlayerBoard()]
        self.factories = [[] for _ in range(FACTORY_COUNT)]
        self.center    = []          # includes "START" token when active
        self.bag       = []
        self.lid       = []          # discarded tiles (overflow, passed tiles)

        self.starting_player  = 0     # who starts THIS round
        self.current_player   = 0     # whose turn it is
        self.phase            = "factory_offer"   # | "wall_tiling"
        self.round            = 1
        self.last_round       = False
        self.game_over        = False
        self.winner           = -1    # -1 = draw, 0 = player 0, 1 = player 1

        # Track whether each player has already taken from centre this round
        # (to know who gets the START token on their first centre take).
        self._taken_from_center = [False, False]

        # End-game bonus breakdown (stored for snapshots)
        self._end_bonuses = [{}, {}]

        # Initialise bag
        self._init_bag()


    # ── Initialisation ───────────────────────────────────────────────────

    def _init_bag(self):
        """Create the bag: 20 tiles of each of the 5 colours = 100 tiles."""
        self.bag = []
        for _ in range(TILES_PER_COLOR):
            for color in Color:
                self.bag.append(color)
        self._rng.shuffle(self.bag)


    def start_round(self):
        """Set up the next round: fill factories, place START token.

        The centre gets a START token.  Both players are marked as
        not yet having taken from centre.
        """
        self.center = ["START"]
        self._taken_from_center = [False, False]
        self._fill_factories()


    def _fill_factories(self):
        """Fill each factory with up to 4 tiles from the bag.

        If the bag is empty before filling starts, the lid is
        recycled first.  If the bag runs out during filling,
        factories simply get fewer tiles (some may get 0).
        """
        if not self.bag:
            self._recycle_lid()
        for i in range(FACTORY_COUNT):
            self.factories[i] = []
            for _ in range(4):
                if not self.bag:
                    break
                self.factories[i].append(self.bag.pop())


    def _recycle_lid(self):
        """Move all lid tiles back into the bag and shuffle.

        The START token (if present) is discarded — it must never
        go back into the bag or into factories.
        """
        if not self.lid:
            return
        for item in self.lid:
            if isinstance(item, Color):
                self.bag.append(item)
            # "START" strings are discarded
        self.lid = []
        self._rng.shuffle(self.bag)


    # ── Move validation ──────────────────────────────────────────────────

    def can_take_from_factory(self, player_idx: int, factory_idx: int,
                              color: Color) -> bool:
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


    def can_take_from_center(self, player_idx: int, color: Color) -> bool:
        if self.phase != "factory_offer":
            return False
        if player_idx != self.current_player:
            return False
        centre_tiles = [t for t in self.center if isinstance(t, Color)]
        return color in centre_tiles


    # ── Executing moves ──────────────────────────────────────────────────

    def take_from_factory(self, player_idx: int, factory_idx: int,
                          color: Color) -> list[Color] | None:
        """Take all tiles of *color* from *factory_idx*.

        Remaining tiles in that factory are moved to the centre.
        Returns the list of taken tiles, or None if the move is illegal.
        """
        if not self.can_take_from_factory(player_idx, factory_idx, color):
            return None
        factory            = self.factories[factory_idx]
        taken              = [t for t in factory if t == color]
        remaining          = [t for t in factory if t != color]
        self.factories[factory_idx] = []
        self.center.extend(remaining)
        return taken


    def take_from_center(self, player_idx: int,
                         color: Color) -> tuple[list[Color], bool] | None:
        """Take all tiles of *color* from the centre.

        Returns (taken_tiles, got_start_token).
        The START token is awarded to the first player each round who
        takes from the centre; it goes on their floor line.
        """
        if not self.can_take_from_center(player_idx, color):
            return None
        centre_colors = [t for t in self.center if isinstance(t, Color)]
        taken = [t for t in centre_colors if t == color]
        # Rebuild centre: keep START token, keep other colours
        self.center = [t for t in self.center if not (isinstance(t, Color) and t == color)]
        # Check START token
        got_start = False
        if not self._taken_from_center[player_idx]:
            self._taken_from_center[player_idx] = True
            if "START" in self.center:
                self.center.remove("START")
                got_start = True
        return taken, got_start


    def place_on_pattern_line(self, player_idx: int, line_idx: int,
                              tiles: list[Color]) -> list[Color]:
        """Place *tiles* into a pattern line.  Return overflow (→ floor).

        If *line_idx* is -1, all tiles go directly to floor (no pattern line).
        """
        if line_idx < 0 or line_idx > 4:
            return tiles  # all to floor
        player = self.players[player_idx]
        if not tiles:
            return []
        if not player.can_place_in_pattern(line_idx, tiles[0]):
            return tiles
        return player.add_to_pattern(line_idx, tiles)


    def execute_move(self, player_idx: int, source_type: str,
                     source_idx: int, color: Color,
                     line_idx: int) -> bool:
        """Execute a full move: take tiles, place on pattern/floor, advance turn.

        This is the main entry point for applying a Move to the game state.
        Returns True on success, False on illegal move.
        """
        if source_type == "factory":
            tiles = self.take_from_factory(player_idx, source_idx, color)
            if tiles is None:
                return False
        elif source_type == "center":
            result = self.take_from_center(player_idx, color)
            if result is None:
                return False
            tiles, got_start = result
            if got_start:
                overflow = self.players[player_idx].add_to_floor(["START"])
                if overflow:
                    self.lid.extend(overflow)  # START beyond cap → discard
        else:
            return False

        if not tiles:
            # No tiles of that colour (shouldn't happen if validation passed)
            self.advance_turn()
            return True

        overflow = self.place_on_pattern_line(player_idx, line_idx, tiles)
        if overflow:
            discard = self.players[player_idx].add_to_floor(overflow)
            if discard:
                self.lid.extend(discard)
        self.advance_turn()
        return True


    # ── Turn management ──────────────────────────────────────────────────

    def advance_turn(self):
        """End the current turn.  If the drafting phase is over, start wall
        tiling instead of switching to the next player."""
        if self._is_drafting_over():
            self.phase = "wall_tiling"
            return
        self.current_player = 1 - self.current_player


    def _is_drafting_over(self) -> bool:
        """Return True when all factories and the centre are empty (of tiles)."""
        if any(self.factories):
            return False
        centre_tiles = [t for t in self.center if isinstance(t, Color)]
        return not centre_tiles


    # ── Wall tiling (end of round) ───────────────────────────────────────

    def resolve_wall_tiling(self):
        """End-of-round procedure.

        For each player:
          1. Each full pattern line places its tile on the wall (scoring).
          2. The floor line is cleared and penalties applied.

        Then check for end-game.  If the game continues, set up the next
        round.
        """
        for p in range(2):
            player = self.players[p]
            for line_idx in range(5):
                if len(player.pattern_lines[line_idx]) == line_idx + 1:
                    player.place_on_wall(line_idx, self.lid)
            penalty = player.discard_floor(self.lid)
            player.score = max(0, player.score + penalty)
        self._check_end_game()
        if not self.game_over:
            self._prepare_next_round()


    def _check_end_game(self):
        """Check if any player has completed a horizontal wall row.

        Official rule: when a player completes a wall row, the game ends
        at the conclusion of the current round.  End-game bonuses are
        then awarded.
        """
        for p in range(2):
            if self.players[p].has_complete_row():
                self.last_round = True
        if self.last_round:
            self.game_over = True
            self._calculate_final_scores()


    def _calculate_final_scores(self):
        """Add end-game bonuses to BOTH players' scores.

        Official bonuses:
          - +2 for each complete horizontal row
          - +7 for each complete vertical column
          - +10 for each complete colour set (the colour appears in all 5 rows)

        The winner is the player with the highest final score.
        Tie-break: most complete horizontal rows.  Still tied: draw.
        """
        self._end_bonuses = [{}, {}]
        for p in range(2):
            player = self.players[p]
            hr = player.count_complete_rows()
            vc = player.count_complete_cols()
            fc = player.count_complete_colors()
            self._end_bonuses[p] = {"rows": hr, "cols": vc, "colors": fc}
            player.score += hr * 2
            player.score += vc * 7
            player.score += fc * 10
        # Determine winner
        s0, s1 = self.players[0].score, self.players[1].score
        if s0 > s1:
            self.winner = 0
        elif s1 > s0:
            self.winner = 1
        else:
            h0 = self.players[0].count_complete_rows()
            h1 = self.players[1].count_complete_rows()
            if h0 > h1:
                self.winner = 0
            elif h1 > h0:
                self.winner = 1
            else:
                self.winner = -1


    def _prepare_next_round(self):
        """Advance to the next round.

        1. Leftover tiles in factories and centre go to the lid.
        2. The starting player alternates.
        3. Factories are refilled from the (replenished) bag.
        """
        # Collect leftover factory tiles into lid
        for f in self.factories:
            self.lid.extend(f)
        # Collect leftover centre tiles (non-START) into lid
        for t in self.center:
            if isinstance(t, Color):
                self.lid.append(t)
        self.phase = "factory_offer"
        self.round += 1
        self.starting_player = 1 - self.starting_player
        self.current_player = self.starting_player
        self.start_round()


    # ── State snapshots (for replay / save) ──────────────────────────────

    def get_state_snapshot(self) -> dict:
        """Serialise the current game state to a JSON-compatible dict."""
        bonus = getattr(self, "_end_bonuses", [{}, {}])
        return {
            "factories": [[c.value for c in f] for f in self.factories],
            "center": [
                c if isinstance(c, str) else c.value
                for c in self.center
            ],
            "bag": [c.value for c in self.bag],
            "lid": [c.value if isinstance(c, Color) else c for c in self.lid],
            "players": [
                {
                    "pattern_lines": [
                        [c.value for c in pl]
                        for pl in self.players[i].pattern_lines
                    ],
                    "wall": [
                        [c.value if c is not None else None for c in row]
                        for row in self.players[i].wall
                    ],
                    "floor_line": [
                        c.value if isinstance(c, Color) else c
                        for c in self.players[i].floor_line
                    ],
                    "score": self.players[i].score,
                    "bonus_rows":   bonus[i].get("rows", 0),
                    "bonus_cols":   bonus[i].get("cols", 0),
                    "bonus_colors": bonus[i].get("colors", 0),
                }
                for i in range(2)
            ],
            "current_player":  self.current_player,
            "starting_player": self.starting_player,
            "phase":           self.phase,
            "round":           self.round,
            "game_over":       self.game_over,
            "winner":          self.winner,
        }


    def load_state_snapshot(self, snapshot: dict):
        """Restore game state from a snapshot dict."""
        self.factories = [[Color(c) for c in f] for f in snapshot["factories"]]
        self.center = []
        for c in snapshot["center"]:
            if isinstance(c, str):
                self.center.append(c)
            else:
                self.center.append(Color(c))
        for i in range(2):
            p = snapshot["players"][i]
            self.players[i].pattern_lines = [
                [Color(c) for c in pl] for pl in p["pattern_lines"]
            ]
            self.players[i].wall = [
                [Color(c) if c is not None else None for c in row]
                for row in p["wall"]
            ]
            self.players[i].floor_line = []
            for c in p["floor_line"]:
                if isinstance(c, str):
                    self.players[i].floor_line.append(c)
                else:
                    self.players[i].floor_line.append(Color(c))
            self.players[i].score = p["score"]
        self.current_player  = snapshot["current_player"]
        self.starting_player = snapshot["starting_player"]
        self.phase           = snapshot["phase"]
        self.round           = snapshot["round"]
        self.game_over       = snapshot["game_over"]
        self.winner          = snapshot["winner"]
