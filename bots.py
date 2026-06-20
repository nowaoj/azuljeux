from abc import ABC, abstractmethod
import random
from typing import NamedTuple

from game import Color, FLOOR_PENALTIES, WALL_LAYOUT, GameState

AzulState = GameState


class Move(NamedTuple):
    source_type: str
    source_idx: int
    color: Color
    line_idx: int


WR = 1
WC = 3
WK = 5


def _get_wall_col(row: int, color: Color) -> int:
    """Return the wall column index for a given row and color."""
    for c in range(5):
        if WALL_LAYOUT[row][c] == color:
            return c
    return -1


def _compute_wall_score(wall: list[list[Color | None]], row: int, col: int) -> int:
    """Return the immediate score S for placing a tile at (row, col) on the wall."""
    hor = 1
    c = col - 1
    while c >= 0 and wall[row][c] is not None:
        hor += 1
        c -= 1
    c = col + 1
    while c < 5 and wall[row][c] is not None:
        hor += 1
        c += 1
    ver = 1
    r = row - 1
    while r >= 0 and wall[r][col] is not None:
        ver += 1
        r -= 1
    r = row + 1
    while r < 5 and wall[r][col] is not None:
        ver += 1
        r += 1
    if hor == 1 and ver == 1:
        return 1
    if hor > 1 and ver == 1:
        return hor
    if ver > 1 and hor == 1:
        return ver
    return hor + ver


def _get_valid_lines(game: GameState, player_idx: int, color: Color) -> list[int]:
    """Return pattern line indices where the given colour can be placed."""
    player = game.players[player_idx]
    return [i for i in range(5) if player.can_place_in_pattern(i, color)]


def get_legal_moves(game: GameState, player_idx: int) -> list[Move]:
    """Generate all legal moves for the player."""
    moves: list[Move] = []
    for f_idx, factory in enumerate(game.factories):
        if not factory:
            continue
        for color in set(factory):
            valid_lines = _get_valid_lines(game, player_idx, color)
            for line in valid_lines:
                moves.append(Move("factory", f_idx, color, line))
            moves.append(Move("factory", f_idx, color, -1))
    center_colors = [t for t in game.center if isinstance(t, Color)]
    for color in set(center_colors):
        valid_lines = _get_valid_lines(game, player_idx, color)
        for line in valid_lines:
            moves.append(Move("center", -1, color, line))
        moves.append(Move("center", -1, color, -1))
    return moves


def evaluate_move(
    game: GameState, player_idx: int, move: Move,
) -> tuple[int, int, int, int, int, bool]:
    """Return (S, P, R, C, K, completes) for a given move."""
    player = game.players[player_idx]

    if move.source_type == "factory":
        taken = sum(1 for t in game.factories[move.source_idx] if t == move.color)
    else:
        taken = sum(1 for t in game.center if isinstance(t, Color) and t == move.color)

    if move.line_idx == -1:
        tiles_placed = 0
        overflow = taken
    else:
        pattern_line = player.pattern_lines[move.line_idx]
        max_size = move.line_idx + 1
        existing = len(pattern_line)
        placed = min(taken, max_size - existing)
        tiles_placed = placed
        overflow = taken - placed

    P = 0
    got_start = (
        move.source_type == "center"
        and not game.taken_from_center[player_idx]
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

    S = 0
    completes = False
    if move.line_idx >= 0:
        new_len = len(player.pattern_lines[move.line_idx]) + tiles_placed
        if new_len == move.line_idx + 1:
            completes = True
            wall_col = _get_wall_col(move.line_idx, move.color)
            if wall_col >= 0 and player.wall[move.line_idx][wall_col] is None:
                S = _compute_wall_score(player.wall, move.line_idx, wall_col)

    wall_col = _get_wall_col(move.line_idx, move.color) if move.line_idx >= 0 else -1
    if move.line_idx >= 0 and wall_col >= 0:
        row_tiles = sum(1 for c in range(5) if player.wall[move.line_idx][c] is not None)
        R = row_tiles + (1 if completes else 0)
        col_tiles = sum(1 for r in range(5) if player.wall[r][wall_col] is not None)
        C = col_tiles + (1 if completes else 0)
    else:
        R = 0
        C = 0

    K = sum(1 for r in range(5) for c in range(5) if player.wall[r][c] == move.color)
    if completes:
        K += 1

    return S, P, R, C, K, completes


class Bot(ABC):
    """Abstract base for all bots."""

    @abstractmethod
    def choose_move(self, game: GameState, player_idx: int) -> Move | None:
        ...

    @property
    def name(self) -> str:
        return type(self).__name__


class GreedyBot(Bot):
    """Greedy immediate-value maximiser."""

    def choose_move(self, game: GameState, player_idx: int) -> Move | None:
        moves = get_legal_moves(game, player_idx)
        if not moves:
            return None

        scored: list[tuple[int, bool, Move]] = []
        for move in moves:
            S, P, _, _, _, _ = evaluate_move(game, player_idx, move)
            V = S - P
            row = move.line_idx
            row_key = row if row >= 0 else -999
            avoids_floor = P == 0
            scored.append((-V, -row_key, -avoids_floor, move))

        scored.sort(key=lambda x: (x[0], x[1], x[2]))
        best_V_key = scored[0][0]
        best_row_key = scored[0][1]
        best_avoid_key = scored[0][2]
        tied = [
            s for s in scored
            if s[0] == best_V_key and s[1] == best_row_key and s[2] == best_avoid_key
        ]
        return random.choice(tied)[3]


class PlannedBot(Bot):
    """Weighted utility planner."""

    def __init__(self, Wr: int = WR, Wc: int = WC, Wk: int = WK) -> None:
        self.Wr = Wr
        self.Wc = Wc
        self.Wk = Wk

    def choose_move(self, game: GameState, player_idx: int) -> Move | None:
        moves = get_legal_moves(game, player_idx)
        if not moves:
            return None

        scored: list[tuple[int, bool, int, Move]] = []
        for move in moves:
            S, P, R, C, K, completes = evaluate_move(game, player_idx, move)
            V = S - P + R * self.Wr + C * self.Wc + K * self.Wk
            row = move.line_idx
            row_key = row if row >= 0 else 999
            scored.append((-V, not completes, row_key, move))

        scored.sort(key=lambda x: (x[0], x[1], x[2]))
        best_V_key = scored[0][0]
        best_comp_key = scored[0][1]
        best_row_key = scored[0][2]
        tied = [
            s for s in scored
            if s[0] == best_V_key and s[1] == best_comp_key and s[2] == best_row_key
        ]
        return tied[0][3]


class FixedPriorityOpponent(Bot):
    """Avoid the floor when possible; otherwise pick the move with the smallest floor penalty (ties broken randomly)."""

    def choose_move(self, game: GameState, player_idx: int) -> Move | None:
        moves = get_legal_moves(game, player_idx)
        if not moves:
            return None

        no_floor = [m for m in moves if m.line_idx >= 0]
        if no_floor:
            return random.choice(no_floor)

        evals = [(move, evaluate_move(game, player_idx, move)[1]) for move in moves]
        min_p = min(p for _, p in evals)
        best = [move for move, p in evals if p == min_p]
        return random.choice(best)


class RandomBot(Bot):
    """Picks a random target line/colour and takes the largest available source."""

    def __init__(self) -> None:
        self.target_line: int | None = None
        self.target_color: Color | None = None

    def choose_move(self, game: GameState, player_idx: int) -> Move | None:
        moves = get_legal_moves(game, player_idx)
        if not moves:
            return None
        player = game.players[player_idx]

        if self.target_line is not None:
            line = player.pattern_lines[self.target_line]
            if len(line) == self.target_line + 1:
                self.target_line = None
                self.target_color = None
            else:
                wall_col = _get_wall_col(self.target_line, self.target_color)
                if wall_col < 0 or player.wall[self.target_line][wall_col] is not None:
                    self.target_line = None
                    self.target_color = None
                elif not any(
                    m for m in moves
                    if m.color == self.target_color and m.line_idx == self.target_line
                ):
                    self.target_line = None
                    self.target_color = None

        if self.target_line is None:
            valid_targets = [(m.line_idx, m.color) for m in moves if m.line_idx >= 0]
            if not valid_targets:
                floor_moves = [m for m in moves if m.line_idx == -1]
                return random.choice(floor_moves) if floor_moves else moves[0]
            self.target_line, self.target_color = random.choice(valid_targets)

        best_move: Move | None = None
        best_count = -1
        for m in moves:
            if m.color == self.target_color and m.line_idx == self.target_line:
                if m.source_type == "factory":
                    count = sum(1 for t in game.factories[m.source_idx] if t == m.color)
                else:
                    count = sum(1 for t in game.center if isinstance(t, Color) and t == m.color)
                if count > best_count:
                    best_count = count
                    best_move = m

        return best_move if best_move is not None else (moves[0] if moves else None)
