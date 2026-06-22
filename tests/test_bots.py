"""Tests for bots.py — bot scoring, tie-breaking, and wall-completion logic."""

from bots import Move, evaluate_move, GreedyBot, PlannedBot, RandomBot
from game import GameState, Color, WALL_LAYOUT


class TestEvaluateMoveFractional:
    """evaluate_move returns R, C, K as fractions (0.0-1.0), not raw counts (0-5)."""

    def test_rcf_are_fractions(self):
        """R, C, K are raw_count / 5 (e.g. 3/5 = 0.6, not 3)."""
        gs = GameState()
        p = gs.players[0]

        # Wall row 2: place BLACK at (2,0), WHITE at (2,1)  →  2 existing
        p.wall[2][0] = WALL_LAYOUT[2][0]  # BLACK
        p.wall[2][1] = WALL_LAYOUT[2][1]  # WHITE
        # Column 3 (YELLOW's column in row 2): place BLACK at (0,3)  →  1 existing
        p.wall[0][3] = WALL_LAYOUT[0][3]  # BLACK
        # No YELLOW anywhere on wall yet  →  0 existing

        # Line 2 (cap 3) with [YELLOW, YELLOW] — taking 1 more YELLOW completes
        p.pattern_lines[2] = [Color.YELLOW, Color.YELLOW]
        gs.factories[0] = [Color.YELLOW]

        move = Move("factory", 0, Color.YELLOW, 2)
        ev = evaluate_move(gs, 0, move)

        # Raw: row=3, col=2, color=1  →  fractions: 3/5, 2/5, 1/5
        assert ev["R"] == 3 / 5.0
        assert ev["C"] == 2 / 5.0
        assert ev["K"] == 1 / 5.0

    def test_plannedbot_v_uses_fractional_rcf(self):
        """PlannedBot's V uses fractional R/C/K:
        e.g. R=3/5, C=2/5, K=1/5, Wr=1, Wc=3, Wk=5
        → contribution = 0.6*1 + 0.4*3 + 0.2*5 = 2.8  (NOT 3+6+5=14)."""
        gs = GameState()
        p = gs.players[0]

        # Same wall setup as above
        p.wall[2][0] = WALL_LAYOUT[2][0]
        p.wall[2][1] = WALL_LAYOUT[2][1]
        p.wall[0][3] = WALL_LAYOUT[0][3]

        p.pattern_lines[2] = [Color.YELLOW, Color.YELLOW]
        gs.factories[0] = [Color.YELLOW]

        bot = PlannedBot(Wr=1, Wc=3, Wk=5)
        chosen = bot.choose_move(gs, 0)
        assert chosen is not None

        # Find the evaluation for the chosen move
        ev = None
        for e in bot.last_evaluations:
            if e["move"] == chosen:
                ev = e
                break
        assert ev is not None

        # Hand-computed values:
        # S = 1 (lone tile, no adjacencies), P = 0
        # R = 3/5 = 0.6, C = 2/5 = 0.4, K = 1/5 = 0.2
        # V = 1 + 0.6*1 + 0.4*3 + 0.2*5 = 1 + 0.6 + 1.2 + 1.0 = 3.8
        assert ev["S"] == 1
        assert ev["P"] == 0
        assert ev["R"] == 3 / 5.0
        assert ev["C"] == 2 / 5.0
        assert ev["K"] == 1 / 5.0

        expected_v = 1 + (3 / 5.0) * 1 + (2 / 5.0) * 3 + (1 / 5.0) * 5  # = 3.8
        assert abs(ev["V"] - expected_v) < 1e-10

        # Confirm the old wrong value would be 15, not 3.8
        old_buggy_v = 1 + 3 * 1 + 2 * 3 + 1 * 5  # = 15
        assert ev["V"] != old_buggy_v


class TestPlannedBotTieBreak:
    """PlannedBot tie-break: highest V → completes → lowest row → deterministic."""

    def test_prefers_completing_move(self):
        """When two moves have equal V, the one completing a pattern line wins."""
        gs = GameState()
        p = gs.players[0]

        # Move A (completes line 0 with RED, S=1, P=0)
        gs.factories[0] = [Color.RED]
        p.pattern_lines[0] = []

        # Move B (floor: line=-1, BLUE, S=0, P=-1)
        gs.center = [Color.BLUE]

        # Both have V=1 when Wr=Wc=Wk=0:
        #   A: V = 1 - 0 + 0 = 1
        #   B: V = 0 - (-1) + 0 = 1
        bot = PlannedBot(Wr=0, Wc=0, Wk=0)
        chosen = bot.choose_move(gs, 0)
        assert chosen is not None
        assert chosen.line_idx == 0   # completes line 0, not floor

    def test_prefers_lower_row(self):
        """Two completing moves with equal V → lower pattern-line index wins."""
        gs = GameState()
        p = gs.players[0]

        # Move A (completes line 0, RED, S=1, P=0)
        gs.factories[0] = [Color.RED]
        p.pattern_lines[0] = []

        # Move B (completes line 1, BLUE, S=1, P=0)
        gs.factories[1] = [Color.BLUE]
        p.pattern_lines[1] = [Color.BLUE]

        bot = PlannedBot(Wr=0, Wc=0, Wk=0)
        chosen = bot.choose_move(gs, 0)
        assert chosen is not None
        assert chosen.line_idx == 0   # lower row wins


class TestGreedyBotTieBreak:
    """GreedyBot tie-break: highest V → highest row → avoid floor → random."""

    def test_prefers_higher_row(self):
        """Two moves with equal V → higher pattern-line index wins."""
        gs = GameState()
        p = gs.players[0]

        # Move A (line 3, RED, completes, S=1, P=0 → V=1)
        gs.factories[0] = [Color.RED]
        p.pattern_lines[3] = [Color.RED, Color.RED, Color.RED]

        # Move B (line 1, BLUE, completes, S=1, P=0 → V=1)
        gs.factories[1] = [Color.BLUE]
        p.pattern_lines[1] = [Color.BLUE]

        bot = GreedyBot()
        chosen = bot.choose_move(gs, 0)
        assert chosen is not None
        assert chosen.line_idx == 3   # higher row

    def test_prefers_avoid_floor(self):
        """Same V and same row → move with P==0 wins."""
        gs = GameState()
        p = gs.players[0]

        # Move A (line 1, RED, completes, S=1, P=0 → V=1, avoids floor)
        gs.factories[0] = [Color.RED]
        p.pattern_lines[1] = [Color.RED]

        # Move B (floor, BLUE, S=0, P=-1 → V=1, hits floor)
        gs.factories[1] = [Color.BLUE]

        bot = GreedyBot()
        chosen = bot.choose_move(gs, 0)
        assert chosen is not None
        assert chosen.line_idx == 1   # not floor

    def test_random_among_full_ties(self):
        """When V, row, and floor-avoid are all tied → random among tied set."""
        gs = GameState()
        p = gs.players[0]

        # Two moves that complete line 0 with RED or BLUE: both S=1, P=0, V=1
        # Line 0 is the same row, both avoid floor → full tie → random
        gs.factories[0] = [Color.RED]
        gs.factories[1] = [Color.BLUE]
        p.pattern_lines[0] = []

        bot = GreedyBot()
        chosen = bot.choose_move(gs, 0)
        assert chosen is not None
        assert chosen.line_idx == 0
        assert chosen.color in (Color.RED, Color.BLUE)


class TestRandomBotFilter:
    """RandomBot filters wall-completing moves unconditionally (no winning exception)."""

    def test_filters_wall_completing_even_when_winning(self):
        """RandomBot excludes wall-completing moves even when the player is winning
        (unlike GreedyBot/PlannedBot which only filter when NOT winning)."""
        gs = GameState()
        p = gs.players[0]

        # Fill 4 cells in row 0 → one more tile completes the wall row
        for c in range(4):
            p.wall[0][c] = WALL_LAYOUT[0][c]
        # Row 0, col 4 is WHITE → taking WHITE to line 0 completes both
        # pattern line AND wall row
        gs.factories[0] = [Color.WHITE]
        p.pattern_lines[0] = []

        # Safe move: RED to line 2 (different row, no wall completion)
        gs.factories[1] = [Color.RED]
        p.pattern_lines[2] = [Color.RED, Color.RED]
        # Also a safe floor move for WHITE
        gs.pattern_lines = p.pattern_lines  # nop, just for safety

        # Player is winning
        p.score = 10
        gs.players[1].score = 0

        # Run multiple times to account for RandomBot's randomness
        # The wall-completing move (WHITE → line 0) must NEVER be chosen
        for _ in range(50):
            bot = RandomBot()
            chosen = bot.choose_move(gs, 0)
            assert chosen is not None
            assert not (chosen.color == Color.WHITE and chosen.line_idx == 0), (
                "RandomBot chose a wall-completing move despite being winning"
            )
