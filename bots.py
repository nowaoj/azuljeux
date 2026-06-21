"""Bot implementations for Azul.

Each bot inherits from the abstract `Bot` class and must implement
`choose_move()`.  After calling `choose_move()` the following instance
attributes are available for inspection / storage:

  * `last_reason`      — human-readable explanation of the chosen move.
  * `last_evaluations` — list of dicts, one per legal move, each containing
    the full evaluation breakdown (S, P, R, C, K, V, …).

This design lets the simulation / replay layer capture exactly what the
bot considered and why it chose what it did.
"""

from abc import ABC, abstractmethod
import random
from typing import NamedTuple

from game import Color, FLOOR_PENALTIES, WALL_LAYOUT, GameState


# ── Move type ─────────────────────────────────────────────────────────────────

class Move(NamedTuple):
    """A single action a bot can take.

    Fields:
      source_type : "factory" | "center"
      source_idx  : factory index (0-4) when source is a factory; -1 for centre.
      color       : the colour being taken.
      line_idx    : target pattern line (0-4), or -1 for floor.
    """
    source_type: str
    source_idx: int
    color: Color
    line_idx: int


# ── Default weights for PlannedBot ────────────────────────────────────────────

WR = 1   # weight for row progress  (bonus +2  at game end)
WC = 3   # weight for column progress (bonus +7  at game end)
WK = 5   # weight for colour-set progress (bonus +10 at game end)

# Weights are proportional to the final bonus values so that PlannedBot
# prioritises progress toward larger bonuses proportionally.


# ═══════════════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════════════

def _wall_column(row: int, color: Color) -> int:
    """Return the column index in *row* where *color* belongs on the wall."""
    for c in range(5):
        if WALL_LAYOUT[row][c] == color:
            return c
    return -1


def _score_placement_on_wall(wall: list[list[Color | None]],
                             row: int, col: int) -> int:
    """Compute the points a newly placed tile at (row, col) would earn.

    Uses the same logic as PlayerBoard._score_placement.
    """
    hor = 1
    c = col - 1
    while c >= 0 and wall[row][c] is not None:
        hor += 1; c -= 1
    c = col + 1
    while c < 5 and wall[row][c] is not None:
        hor += 1; c += 1
    ver = 1
    r = row - 1
    while r >= 0 and wall[r][col] is not None:
        ver += 1; r -= 1
    r = row + 1
    while r < 5 and wall[r][col] is not None:
        ver += 1; r += 1
    if hor == 1 and ver == 1:
        return 1
    if ver == 1:
        return hor
    if hor == 1:
        return ver
    return hor + ver


def get_valid_pattern_lines(game: GameState, player_idx: int,
                            color: Color) -> list[int]:
    """Return all pattern-line indices where *color* can legally be placed."""
    player = game.players[player_idx]
    return [i for i in range(5) if player.can_place_in_pattern(i, color)]


def get_legal_moves(game: GameState, player_idx: int) -> list[Move]:
    """Generate every legal move for *player_idx* in the current state.

    For each colour available in factories or centre, two variants are
    generated: placing on each valid pattern line, and sending directly
    to floor (line_idx = -1).
    """
    moves: list[Move] = []

    # Factories
    for f_idx, factory in enumerate(game.factories):
        if not factory:
            continue
        for color in set(factory):
            for line in get_valid_pattern_lines(game, player_idx, color):
                moves.append(Move("factory", f_idx, color, line))
            moves.append(Move("factory", f_idx, color, -1))

    # Centre (only actual tile colours, not the START token)
    centre_colors = [t for t in game.center if isinstance(t, Color)]
    for color in set(centre_colors):
        for line in get_valid_pattern_lines(game, player_idx, color):
            moves.append(Move("center", -1, color, line))
        moves.append(Move("center", -1, color, -1))

    return moves


def evaluate_move(game: GameState, player_idx: int,
                  move: Move) -> dict:
    """Return a full evaluation dict for a single move.

    Keys in the returned dict:
      move         — the Move itself
      S            — immediate wall points if pattern line fills (0 otherwise)
      P            — floor penalty this round (negative or 0)
      R            — fraction of target row filled after placement (0.0-1.0)
      C            — fraction of target column filled after placement (0.0-1.0)
      K            — fraction of colour set filled on wall after placement (0.0-1.0)
      completes    — True if the pattern line fills (tile goes to wall)
      finishes_game — True if this move would complete a wall row (end game)
      taken        — how many tiles of this colour are available
      overflow     — how many tiles go to floor (excess beyond pattern capacity)
      got_start    — whether this move would acquire the START token
    """
    player = game.players[player_idx]

    # ── How many tiles are available? ────────────────────────────────────
    if move.source_type == "factory":
        taken = sum(1 for t in game.factories[move.source_idx]
                    if t == move.color)
    else:
        taken = sum(1 for t in game.center
                    if isinstance(t, Color) and t == move.color)

    # ── Where do they go? ────────────────────────────────────────────────
    tiles_placed = 0
    overflow = taken
    if move.line_idx >= 0:
        pattern_line = player.pattern_lines[move.line_idx]
        max_size = move.line_idx + 1
        existing = len(pattern_line)
        placed = min(taken, max_size - existing)
        tiles_placed = placed
        overflow = taken - placed

    # ── Floor penalty ────────────────────────────────────────────────────
    P = 0
    got_start = (
        move.source_type == "center"
        and not game._taken_from_center[player_idx]
        and "START" in game.center
    )
    pos = len(player.floor_line)
    if got_start:
        if pos < len(FLOOR_PENALTIES):
            P -= FLOOR_PENALTIES[pos]
        pos += 1
    for _ in range(overflow):
        if pos < len(FLOOR_PENALTIES):
            P -= FLOOR_PENALTIES[pos]
        pos += 1

    # ── Wall points (S) and pattern line completion ──────────────────────
    S = 0
    completes = False
    if move.line_idx >= 0:
        new_len = len(player.pattern_lines[move.line_idx]) + tiles_placed
        if new_len == move.line_idx + 1:
            completes = True
            wall_col = _wall_column(move.line_idx, move.color)
            if wall_col >= 0 and player.wall[move.line_idx][wall_col] is None:
                S = _score_placement_on_wall(player.wall, move.line_idx, wall_col)

    # ── Row / column / colour progress ───────────────────────────────────
    wall_col = _wall_column(move.line_idx, move.color) if move.line_idx >= 0 else -1
    if move.line_idx >= 0 and wall_col >= 0:
        row_tiles = sum(1 for c in range(5)
                        if player.wall[move.line_idx][c] is not None)
        R = (row_tiles + (1 if completes else 0)) / 5.0
        col_tiles = sum(1 for r in range(5)
                        if player.wall[r][wall_col] is not None)
        C = (col_tiles + (1 if completes else 0)) / 5.0
    else:
        R = 0.0
        C = 0.0

    K_raw = sum(1 for r in range(5) for c in range(5)
            if player.wall[r][c] == move.color)
    if completes:
        K_raw += 1
    K = K_raw / 5.0

    # ── Would this finish the game? ──────────────────────────────────────
    finishes_game = _would_complete_wall_row(game, player_idx, move)

    return {
        "move": move,
        "S": S,
        "P": P,
        "R": R,
        "C": C,
        "K": K,
        "completes": completes,
        "finishes_game": finishes_game,
        "taken": taken,
        "overflow": overflow,
        "got_start": got_start,
    }


def _would_complete_wall_row(game: GameState, player_idx: int,
                             move: Move) -> bool:
    """Return True if making *move* would place a tile completing a wall row.

    A wall row is complete when all 5 cells in that row have a tile.
    This triggers end-game, so bots avoid it unless winning.
    """
    if move.line_idx < 0:
        return False
    player = game.players[player_idx]
    pattern_line = player.pattern_lines[move.line_idx]
    max_size = move.line_idx + 1
    if len(pattern_line) >= max_size:
        return False
    if pattern_line and pattern_line[0] != move.color:
        return False
    # How many tiles of this colour are available?
    if move.source_type == "factory":
        taken = sum(1 for t in game.factories[move.source_idx]
                    if t == move.color)
    else:
        taken = sum(1 for t in game.center
                    if isinstance(t, Color) and t == move.color)
    space_left = max_size - len(pattern_line)
    if taken < space_left:
        return False  # pattern line won't fill → nothing reaches the wall
    existing = sum(1 for c in range(5)
                   if player.wall[move.line_idx][c] is not None)
    return existing + 1 == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Bot base class
# ═══════════════════════════════════════════════════════════════════════════════

class Bot(ABC):
    """Abstract base for all bots.

    Subclasses must implement `choose_move()`.  After each call, inspect:
      * `self.last_reason`       — str explaining the decision.
      * `self.last_evaluations`  — list of evaluation dicts (see `evaluate_move`)
        for EVERY legal move that was considered.
    """

    def __init__(self):
        self.last_reason       = ""
        self.last_evaluations  = []

    @abstractmethod
    def choose_move(self, game: GameState, player_idx: int) -> Move | None:
        ...

    @property
    def name(self) -> str:
        return type(self).__name__


# ═══════════════════════════════════════════════════════════════════════════════
# GreedyBot
# ═══════════════════════════════════════════════════════════════════════════════

class GreedyBot(Bot):
    """Maximises immediate net value: V = S − P.

    Decision rule:
      1. Generate all legal moves.
      2. Remove moves that would complete a wall row (end the game)
         UNLESS currently winning.
      3. Score each remaining move: V = S − P.
      4. Pick the move with the highest V.
         Tie-breaks (in order):
           a. Higher pattern line (fill big rows first — more tiles needed).
           b. Avoid floor penalty (P == 0).
           c. Random among remaining ties.
    """

    def choose_move(self, game: GameState, player_idx: int) -> Move | None:
        moves = get_legal_moves(game, player_idx)
        if not moves:
            self.last_reason = "No legal moves available"
            self.last_evaluations = []
            return None

        # Evaluate every move
        evals = [evaluate_move(game, player_idx, m) for m in moves]
        # ── Filter wall-completing moves unless winning ──────────────────
        # If ALL moves would end the game, we must pick one anyway
        # (the game must keep going until a row is actually completed).
        is_winning = (
            game.players[player_idx].score
            > game.players[1 - player_idx].score
        )
        reason_parts = []

        if not is_winning:
            before = len(evals)
            safe = [e for e in evals if not e["finishes_game"]]
            filtered = before - len(safe)
            if safe:
                evals = safe
                if filtered:
                    reason_parts.append(
                        f"Filtered {filtered} wall-completing move(s) (not winning)")
            else:
                # ALL moves would end the game — forced to pick one anyway
                reason_parts.append(
                    f"All moves would end game (forced to complete a row)")

        # ── Score ────────────────────────────────────────────────────────
        for e in evals:
            e["V"] = e["S"] - e["P"]

        # Sort: V descending → row descending → avoid floor → (random at end)
        def sort_key(e):
            row = e["move"].line_idx
            row_key = row if row >= 0 else -999
            return (-e["V"], -row_key, -(1 if e["P"] == 0 else 0))

        evals.sort(key=sort_key)
        best_val = evals[0]["V"]
        best_row = evals[0]["move"].line_idx
        best_floor = (evals[0]["P"] == 0)

        # Find all tied by the first 3 criteria

        tied = [e for e in evals
                if e["V"] == best_val
                and e["move"].line_idx == best_row
                and (e["P"] == 0) == best_floor]

        chosen = random.choice(tied)

        # ── Build reason ─────────────────────────────────────────────────
        reason_parts.append(f"V={chosen['V']} (highest)")
        if len(tied) > 1:
            # Same V, same row, same floor-avoid → random tie-break
            reason_parts.append("random among tied")
        else:
            # Check if there were ties at each level
            same_v = [e for e in evals if e["V"] == best_val]
            if len(same_v) > 1:
                if any(e["move"].line_idx != best_row for e in same_v):
                    reason_parts.append(f"row tie-break: line {best_row}")
                if any((e["P"] == 0) != best_floor for e in same_v):
                    reason_parts.append("avoids floor penalty")

        self.last_reason = ", ".join(reason_parts)
        self.last_evaluations = evals
        return chosen["move"]


# ═══════════════════════════════════════════════════════════════════════════════
# PlannedBot
# ═══════════════════════════════════════════════════════════════════════════════

class PlannedBot(Bot):
    """Weighted utility planner: V = S − P + R·Wr + C·Wc + K·Wk.

    Extends the immediate-value approach by valuing progress toward the
    three end-game bonuses (complete rows, columns, colour sets).

    Weights default to Wr=1, Wc=3, Wk=5, proportional to the bonus
    values (+2, +7, +10).

    Decision rule:
      1. Generate all legal moves.
      2. Remove moves that would complete a wall row UNLESS winning.
      3. Score: V = S − P + R·Wr + C·Wc + K·Wk.
      4. Pick highest V.
         Tie-breaks:
           a. Prefer moves that complete a pattern line (tile → wall).
           b. Lowest pattern line (fill small rows first — easier).
           c. Deterministic (first in sorted order).
    """

    def __init__(self, Wr: int = WR, Wc: int = WC, Wk: int = WK):
        super().__init__()
        self.Wr = Wr
        self.Wc = Wc
        self.Wk = Wk

    def choose_move(self, game: GameState, player_idx: int) -> Move | None:
        moves = get_legal_moves(game, player_idx)
        if not moves:
            self.last_reason = "No legal moves available"
            self.last_evaluations = []
            return None

        evals = [evaluate_move(game, player_idx, m) for m in moves]

        # ── Filter wall-completing moves unless winning ──────────────────
        # If ALL moves would end the game, we must pick one anyway
        # (the game must keep going until a row is actually completed).
        is_winning = (
            game.players[player_idx].score
            > game.players[1 - player_idx].score
        )
        reason_parts = []

        if not is_winning:
            before = len(evals)
            safe = [e for e in evals if not e["finishes_game"]]
            filtered = before - len(safe)
            if safe:
                evals = safe
                if filtered:
                    reason_parts.append(
                        f"Filtered {filtered} wall-completing move(s) (not winning)")
            else:
                # ALL moves would end the game — forced to pick one anyway
                reason_parts.append(
                    f"All moves would end game (forced to complete a row)")

        # ── Score ────────────────────────────────────────────────────────
        for e in evals:
            e["V"] = (e["S"] - e["P"]
                      + e["R"] * self.Wr
                      + e["C"] * self.Wc
                      + e["K"] * self.Wk)

        # Sort: V descending → completes first → lowest row → deterministic
        def sort_key(e):
            row = e["move"].line_idx
            row_key = row if row >= 0 else 999
            return (-e["V"], 0 if e["completes"] else 1, row_key)

        evals.sort(key=sort_key)
        tied = [e for e in evals
                if e["V"] == evals[0]["V"]
                and e["completes"] == evals[0]["completes"]
                and e["move"].line_idx == evals[0]["move"].line_idx]
        chosen = tied[0]

        # ── Build reason ─────────────────────────────────────────────────
        formula = (f"V=S-P+R·{self.Wr}+C·{self.Wc}+K·{self.Wk}="
                   f"{chosen['S']}-{chosen['P']}+"
                   f"{chosen['R']}·{self.Wr}+"
                   f"{chosen['C']}·{self.Wc}+"
                   f"{chosen['K']}·{self.Wk}="
                   f"{chosen['V']}")
        reason_parts.append(formula)
        if chosen["completes"]:
            reason_parts.append("completes pattern line (priority 2)")

        # Tie-break info
        same_v = [e for e in evals if e["V"] == chosen["V"]]
        if len(same_v) > 1:
            if any(e["completes"] != chosen["completes"] for e in same_v):
                reason_parts.append("prefers completing row")
            if any(e["move"].line_idx != chosen["move"].line_idx
                   for e in same_v):
                reason_parts.append(
                    f"lower row tie-break: line {chosen['move'].line_idx}")

        self.last_reason = "; ".join(reason_parts)
        self.last_evaluations = evals
        return chosen["move"]


# ═══════════════════════════════════════════════════════════════════════════════
# RandomBot
# ═══════════════════════════════════════════════════════════════════════════════

class RandomBot(Bot):
    """Picks uniformly at random among legal moves, never completing a wall row.

    Decision rule:
      1. Generate all legal moves.
      2. Remove any that would complete a wall row (end the game).
      3. Pick uniformly at random from the remainder.
    """

    def choose_move(self, game: GameState, player_idx: int) -> Move | None:
        moves = get_legal_moves(game, player_idx)
        if not moves:
            self.last_reason = "No legal moves available"
            self.last_evaluations = []
            return None

        evals = [evaluate_move(game, player_idx, m) for m in moves]

        # ── Filter wall-completing moves ─────────────────────────────────
        # If ALL moves would end the game, pick one anyway.
        before = len(evals)
        safe = [e for e in evals if not e["finishes_game"]]
        filtered = before - len(safe)
        if safe:
            evals = safe
        else:
            # ALL moves would end the game — forced to pick one
            evals = evals  # keep wall-completing moves

        n = len(evals)
        chosen = random.choice(evals)
        reason_parts = [f"Random choice among {n} legal move(s)"]
        if filtered and safe:
            reason_parts.append(f"({filtered} wall-completing filtered)")
        elif not safe:
            reason_parts.append("(all moves would end game, forced)")

        # Attach V = S - P for display consistency, even though RandomBot
        # doesn't actually use it for decision-making.
        for e in evals:
            e["V"] = e["S"] - e["P"]

        self.last_reason = "; ".join(reason_parts)
        self.last_evaluations = evals
        return chosen["move"]
