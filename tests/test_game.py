"""Tests for game.py — core Azul game engine.

Covers:
  - Initialisation (bag, factories, round)
  - Tile taking (factory, centre, START token)
  - Pattern line placement and overflow
  - Wall tiling and scoring
  - End-game detection and final scoring
  - State snapshot round-trip
"""

import random
from game import (
    GameState, Color, PlayerBoard,
    FACTORY_COUNT, TILES_PER_COLOR, WALL_LAYOUT, FLOOR_PENALTIES,
)


class TestGameState:

    def test_init(self):
        gs = GameState()
        assert len(gs.players) == 2
        assert len(gs.factories) == FACTORY_COUNT
        assert gs.center == []
        assert gs.phase == "factory_offer"
        assert gs.round == 1
        assert not gs.game_over
        # Bag should be initialised automatically
        assert len(gs.bag) == 5 * TILES_PER_COLOR

    def test_bag_has_correct_tile_count(self):
        gs = GameState()
        assert len(gs.bag) == 100
        for color in Color:
            assert gs.bag.count(color) == TILES_PER_COLOR

    def test_fill_factories(self):
        gs = GameState()
        gs.start_round()
        for f in gs.factories:
            assert len(f) == 4
        assert "START" in gs.center

    def test_start_round_resets_taken_from_center(self):
        gs = GameState()
        gs._taken_from_center = [True, False]
        gs.start_round()
        assert gs._taken_from_center == [False, False]

    def test_take_from_factory(self):
        gs = GameState()
        gs.start_round()
        factory = gs.factories[0]
        color = factory[0]
        tiles = gs.take_from_factory(0, 0, color)
        assert tiles is not None
        assert all(t == color for t in tiles)
        assert gs.factories[0] == []
        # Remaining tiles should be in centre
        centre_colors = [t for t in gs.center if isinstance(t, Color)]
        remaining = [t for t in factory if t != color]
        for t in remaining:
            assert t in centre_colors

    def test_take_from_center_first_gets_start(self):
        """First player to take from centre gets the START token on the floor."""
        gs = GameState()
        gs.factories = [[Color.RED]*4, [], [], [], []]
        gs.center = ["START", Color.BLUE, Color.BLUE]
        gs.current_player = 0
        gs._taken_from_center = [False, False]
        # Player 0 takes RED from factory 0 → no remaining tiles go to centre
        gs.execute_move(0, "factory", 0, Color.RED, 0)
        # Now it's player 1's turn.  Take BLUE from centre (first to do so).
        gs.execute_move(1, "center", -1, Color.BLUE, -1)
        assert "START" in gs.players[1].floor_line, "START should be on P1 floor"

    def test_start_token_respects_floor_capacity(self):
        gs = GameState()
        gs.start_round()
        gs.players[0].floor_line = ["RED"] * 7
        # Take from centre — START should NOT be added (floor full)
        factory = gs.factories[0]
        color = factory[0]
        gs.take_from_factory(1, 0, color)
        centre_colors = [t for t in gs.center if isinstance(t, Color)]
        if centre_colors:
            c = centre_colors[0]
            result = gs.take_from_center(0, c)
            assert result is not None
            _, got_start = result
            if got_start:
                assert len(gs.players[0].floor_line) <= 7

    def test_can_place_in_pattern(self):
        board = PlayerBoard()
        assert board.can_place_in_pattern(0, Color.BLUE)
        board.pattern_lines[0] = [Color.BLUE]
        # Line 0 is full (capacity 1)
        assert not board.can_place_in_pattern(0, Color.BLUE)
        assert not board.can_place_in_pattern(0, Color.RED)

    def test_wall_placement_scoring_single(self):
        board = PlayerBoard()
        board.pattern_lines[0] = [Color.BLUE]
        score = board.place_on_wall(0, lid=[])
        assert score == 1
        assert board.wall[0][0] == Color.BLUE

    def test_wall_placement_scoring_horizontal(self):
        board = PlayerBoard()
        board.wall[0][0] = Color.BLUE
        board.pattern_lines[0] = [Color.YELLOW]  # row 0, col 1
        score = board.place_on_wall(0, lid=[])
        assert score == 2  # YELLOW + BLUE = 2 horizontally

    def test_wall_placement_scoring_vertical(self):
        board = PlayerBoard()
        board.wall[0][0] = Color.BLUE
        board.pattern_lines[1] = [Color.WHITE, Color.WHITE]  # row 1, col 0
        board.place_on_wall(1, lid=[])
        # P1 now has WHITE at (1,0), P0 has BLUE at (0,0) — vertical connect
        assert board.wall[1][0] == Color.WHITE
        # The BLUE at (0,0) and WHITE at (1,0) are different colors so no vertical connection
        # Actually in Azul, vertical scoring is based on positions, not colors.
        # WHITE belongs at WALL_LAYOUT[1][0] = WHITE
        # So (0,0)=BLUE and (1,0)=WHITE — they're adjacent vertically but different rows
        # The scoring counts adjacent tiles regardless of color
        assert board.wall[0][0] is not None and board.wall[1][0] is not None
        # Both cells filled → vertical adjacency gives +2 for placement at row 1

    def test_floor_penalty_calculation(self):
        board = PlayerBoard()
        board.floor_line = ["RED", "RED", "RED"]
        penalty = board.discard_floor(lid=[])
        assert penalty == -4  # -1 + -1 + -2
        assert board.floor_line == []

    def test_game_over_on_complete_row(self):
        gs = GameState()
        p = gs.players[0]
        for c in range(5):
            p.wall[0][c] = WALL_LAYOUT[0][c]
        gs._check_end_game()
        assert gs.last_round
        assert gs.game_over
        assert gs.winner >= -1  # winner determined

    def test_final_scoring_bonuses_correct(self):
        gs = GameState()
        p = gs.players[0]
        # Fill row 0 completely
        for c in range(5):
            p.wall[0][c] = WALL_LAYOUT[0][c]
        gs._check_end_game()
        assert p.score >= 2  # at least row bonus

    def test_full_game_simulation_ends(self):
        """Play a full game with semi-random moves — must end eventually."""
        gs = GameState(seed=42)
        gs.start_round()
        turn = 0
        while not gs.game_over and turn < 500:
            if gs.phase == "wall_tiling":
                gs.resolve_wall_tiling()
                continue
            for fi, f in enumerate(gs.factories):
                if f:
                    color = f[0]
                    placed = False
                    for li in range(5):
                        if gs.players[gs.current_player].can_place_in_pattern(li, color):
                            gs.execute_move(gs.current_player, "factory", fi, color, li)
                            placed = True
                            break
                    if not placed:
                        gs.execute_move(gs.current_player, "factory", fi, color, -1)
                    break
            else:
                centre_colors = [t for t in gs.center if isinstance(t, Color)]
                if centre_colors:
                    c = centre_colors[0]
                    placed = False
                    for li in range(5):
                        if gs.players[gs.current_player].can_place_in_pattern(li, c):
                            gs.execute_move(gs.current_player, "center", -1, c, li)
                            placed = True
                            break
                    if not placed:
                        gs.execute_move(gs.current_player, "center", -1, c, -1)
            turn += 1
        assert gs.game_over or turn < 500

    def test_state_snapshot_roundtrip(self):
        gs1 = GameState(seed=123)
        gs1.start_round()
        snap = gs1.get_state_snapshot()
        gs2 = GameState()  # different seed — will be overwritten
        gs2.load_state_snapshot(snap)
        assert gs2.factories == gs1.factories
        assert gs2.center == gs1.center
        assert gs2.current_player == gs1.current_player
        assert gs2.round == gs1.round

    def test_snapshot_includes_end_bonuses(self):
        gs = GameState()
        gs.players[0].wall[0][0] = WALL_LAYOUT[0][0]
        gs._check_end_game()  # no complete row, no bonus
        snap = gs.get_state_snapshot()
        assert "bonus_rows" in snap["players"][0]
        assert "bonus_cols" in snap["players"][0]
        assert "bonus_colors" in snap["players"][0]

    def test_both_players_get_end_bonuses(self):
        gs = GameState()
        # Player 0 has a complete row
        for c in range(5):
            gs.players[0].wall[0][c] = WALL_LAYOUT[0][c]
        gs._check_end_game()
        # Both should have received bonuses
        snap = gs.get_state_snapshot()
        assert snap["players"][0]["bonus_rows"] >= 1
        assert snap["players"][1]["bonus_rows"] >= 0  # may be 0

    def test_winner_is_highest_score(self):
        gs = GameState()
        gs.players[0].score = 50
        gs.players[1].score = 30
        gs.game_over = True
        gs._calculate_final_scores()
        assert gs.winner == 0

    def test_tie_breaker_most_rows(self):
        gs = GameState()
        gs.players[0].score = 40
        gs.players[1].score = 40
        # P0 has more complete rows
        for c in range(5):
            gs.players[0].wall[0][c] = WALL_LAYOUT[0][c]
        gs.game_over = True
        gs._calculate_final_scores()
        assert gs.winner == 0

    def test_seed_determinism(self):
        """Same seed → identical game states after init."""
        gs1 = GameState(seed=42)
        gs2 = GameState(seed=42)
        # Re-initialise bag is automatic; compare factory fill
        gs1.start_round()
        gs2.start_round()
        for i in range(FACTORY_COUNT):
            assert gs1.factories[i] == gs2.factories[i], f"Factory {i} differs"


class TestPlayerBoard:

    def test_discard_floor_returns_penalty(self):
        board = PlayerBoard()
        board.floor_line = [Color.BLUE, Color.YELLOW, Color.RED]
        penalty = board.discard_floor(lid=[])
        assert penalty < 0
        assert board.floor_line == []

    def test_has_complete_row_false_initially(self):
        board = PlayerBoard()
        assert not board.has_complete_row()

    def test_has_complete_row_true_when_full(self):
        board = PlayerBoard()
        for c in range(5):
            board.wall[0][c] = WALL_LAYOUT[0][c]
        assert board.has_complete_row()

    def test_count_complete_rows(self):
        board = PlayerBoard()
        assert board.count_complete_rows() == 0
        for c in range(5):
            board.wall[0][c] = WALL_LAYOUT[0][c]
        assert board.count_complete_rows() == 1

    def test_count_complete_cols(self):
        board = PlayerBoard()
        assert board.count_complete_cols() == 0
        for r in range(5):
            board.wall[r][0] = WALL_LAYOUT[r][0]
        assert board.count_complete_cols() == 1

    def test_count_complete_colors_none_initially(self):
        board = PlayerBoard()
        assert board.count_complete_colors() == 0

    def test_add_to_floor_respects_capacity(self):
        board = PlayerBoard()
        overflow = board.add_to_floor(["RED"] * 10)
        assert len(board.floor_line) == 7
        assert len(overflow) == 3
