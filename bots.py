from abc import ABC, abstractmethod
import random
from game import Color, FLOOR_PENALTIES, WALL_LAYOUT


def get_legal_moves(game, player_idx):
    moves = []
    for f_idx, factory in enumerate(game.factories):
        if not factory:
            continue
        for color in set(factory):
            valid_lines = _get_valid_lines(game, player_idx, color)
            for line in valid_lines:
                moves.append(("factory", f_idx, color, line))
            moves.append(("factory", f_idx, color, -1))
    center_colors = [t for t in game.center if isinstance(t, Color)]
    for color in set(center_colors):
        valid_lines = _get_valid_lines(game, player_idx, color)
        for line in valid_lines:
            moves.append(("center", -1, color, line))
        moves.append(("center", -1, color, -1))
    return moves


def _get_valid_lines(game, player_idx, color):
    player = game.players[player_idx]
    return [i for i in range(5) if player.can_place_in_pattern(i, color)]


def _get_wall_col(row, color):
    for c in range(5):
        if WALL_LAYOUT[row][c] == color:
            return c
    return -1


def _compute_wall_score(wall, row, col):
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


def evaluate_move(game, player_idx, move):
    source_type, source_idx, color, line_idx = move
    player = game.players[player_idx]

    if source_type == "factory":
        taken = sum(1 for t in game.factories[source_idx] if t == color)
    else:
        taken = sum(1 for t in game.center if isinstance(t, Color) and t == color)

    if line_idx == -1:
        tiles_placed = 0
        overflow = taken
    else:
        pattern_line = player.pattern_lines[line_idx]
        max_size = line_idx + 1
        existing = len(pattern_line)
        placed = min(taken, max_size - existing)
        tiles_placed = placed
        overflow = taken - placed

    P = 0
    got_start = (source_type == "center"
                 and not game.taken_from_center[player_idx]
                 and "START" in game.center)
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
    if line_idx >= 0:
        new_len = len(player.pattern_lines[line_idx]) + tiles_placed
        if new_len == line_idx + 1:
            completes = True
            wall_col = _get_wall_col(line_idx, color)
            if wall_col >= 0 and player.wall[line_idx][wall_col] is None:
                S = _compute_wall_score(player.wall, line_idx, wall_col)

    R = len(player.pattern_lines[line_idx]) + tiles_placed if line_idx >= 0 else 0

    if line_idx >= 0:
        wall_col = _get_wall_col(line_idx, color)
        if wall_col >= 0:
            C = sum(1 for r in range(5) if player.wall[r][wall_col] is not None)
        else:
            C = 0
    else:
        C = 0

    K = sum(1 for r in range(5) for c in range(5) if player.wall[r][c] == color)

    return S, P, R, C, K, completes


class Bot(ABC):
    @abstractmethod
    def select_move(self, game, player_idx):
        pass

    @property
    def name(self):
        return type(self).__name__


class RandomBot(Bot):
    def select_move(self, game, player_idx):
        moves = get_legal_moves(game, player_idx)
        return random.choice(moves) if moves else None


class GreedyBot(Bot):
    def select_move(self, game, player_idx):
        moves = get_legal_moves(game, player_idx)
        best = []
        best_V = -10**9
        best_row = -2
        for move in moves:
            S, P, _, _, _, _ = evaluate_move(game, player_idx, move)
            V = S - P
            _, _, _, row = move
            row_val = row if row >= 0 else -1
            if V > best_V or (V == best_V and row_val > best_row):
                best_V = V
                best_row = row_val
                best = [move]
            elif V == best_V and row_val == best_row:
                best.append(move)
        return best[0] if best else (moves[0] if moves else None)


class PlannedBot(Bot):
    def __init__(self, Wr=1, Wc=3, Wk=5):
        self.Wr = Wr
        self.Wc = Wc
        self.Wk = Wk

    def select_move(self, game, player_idx):
        moves = get_legal_moves(game, player_idx)
        best = []
        best_V = -10**9
        best_finishes = False
        best_row = 999
        for move in moves:
            S, P, R, C, K, completes = evaluate_move(game, player_idx, move)
            V = S - P + R * self.Wr + C * self.Wc + K * self.Wk
            _, _, _, row = move
            row_val = row if row >= 0 else 999

            better = False
            if V > best_V:
                better = True
            elif V == best_V:
                if completes and not best_finishes:
                    better = True
                elif completes == best_finishes:
                    if row_val < best_row:
                        better = True
                    elif row_val == best_row:
                        best.append(move)

            if better:
                best_V = V
                best_finishes = completes
                best_row = row_val
                best = [move]

        return best[0] if best else (moves[0] if moves else None)
