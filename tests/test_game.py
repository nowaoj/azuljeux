import random
from game import GameState, Color, PlayerBoard, FACTORY_COUNT, TILES_PER_COLOR


class TestGameState:
    def test_init(self):
        gs = GameState()
        assert len(gs.players) == 2
        assert len(gs.factories) == FACTORY_COUNT
        assert gs.center == []
        assert gs.phase == "factory_offer"
        assert gs.round == 1
        assert not gs.game_over

    def test_init_bag(self):
        gs = GameState()
        gs.init_bag()
        assert len(gs.bag) == 5 * TILES_PER_COLOR
        assert all(isinstance(c, Color) for c in gs.bag)

    def test_fill_factories(self):
        gs = GameState()
        gs.init_bag()
        gs.start_round()
        for f in gs.factories:
            assert len(f) == 4

    def test_start_round_includes_start_token(self):
        gs = GameState()
        gs.init_bag()
        gs.start_round()
        assert "START" in gs.center

    def test_take_from_factory(self):
        gs = GameState()
        gs.init_bag()
        gs.start_round()
        factory = gs.factories[0]
        color = factory[0]
        tiles = gs.take_from_factory(0, 0, color)
        assert tiles is not None
        assert all(t == color for t in tiles)
        assert gs.factories[0] == []
        remaining = [t for t in factory if t != color]
        for t in remaining:
            assert t in gs.center

    def test_take_from_center_first_gets_start(self):
        gs = GameState()
        gs.init_bag()
        gs.start_round()
        gs.taken_from_center = [False, False]
        center_color = [c for c in gs.center if isinstance(c, Color)]
        if center_color:
            color = center_color[0]
            result = gs.take_from_center(0, color)
            assert result is not None
            tiles, got_start = result
            if got_start:
                assert len(gs.players[0].floor_line) == 1

    def test_start_token_respects_floor_capacity(self):
        gs = GameState()
        gs.init_bag()
        gs.start_round()
        gs.players[0].floor_line = ["RED", "RED", "RED", "RED", "RED", "RED"]
        gs.current_player_action("center", Color.RED, 0)
        assert len(gs.players[0].floor_line) <= 7

    def test_can_place_in_pattern(self):
        board = PlayerBoard()
        assert board.can_place_in_pattern(0, Color.BLUE)
        board.pattern_lines[0] = [Color.BLUE]
        assert not board.can_place_in_pattern(0, Color.BLUE)
        assert not board.can_place_in_pattern(0, Color.RED)

    def test_wall_placement_scoring_single(self):
        board = PlayerBoard()
        board.pattern_lines[0] = [Color.BLUE]
        score = board.place_on_wall(0)
        assert score == 1
        assert board.wall[0][0] == Color.BLUE

    def test_wall_placement_scoring_horizontal(self):
        board = PlayerBoard()
        board.wall[0][0] = Color.BLUE
        board.pattern_lines[0] = [Color.WHITE]
        board.pattern_lines[0] = [Color.WHITE] * 1
        board.wall[0][4] = None
        score = board.place_on_wall(0)
        score = 0
        board = PlayerBoard()
        board.wall[0][0] = Color.BLUE
        board.pattern_lines[0] = [Color.YELLOW]
        score = board.place_on_wall(0)
        assert score == 2

    def test_game_over_on_complete_row(self):
        gs = GameState()
        gs.init_bag()
        p = gs.players[0]
        for c in range(5):
            p.wall[0][c] = WALL_LAYOUT[0][c]
        gs.check_end_game()
        assert gs.last_round

    def test_final_scoring_bonuses(self):
        gs = GameState()
        gs.init_bag()
        p = gs.players[0]
        for c in range(5):
            p.wall[0][c] = WALL_LAYOUT[0][c]
        gs.game_over = True
        gs.calculate_final_scores()
        assert gs.players[0].score >= 2

    def test_play_full_game(self):
        random.seed(42)
        gs = GameState()
        gs.init_bag()
        gs.start_round()
        turn = 0
        while not gs.game_over and turn < 500:
            if gs.phase == "wall_tiling":
                gs.resolve_wall_tiling()
                continue
            for fi, f in enumerate(gs.factories):
                if f:
                    color = f[0]
                    for li in range(5):
                        if gs.players[gs.current_player].can_place_in_pattern(li, color):
                            gs.current_player_action("factory", fi, color, li)
                            break
                    else:
                        gs.current_player_action("factory", fi, color, -1)
                    break
            else:
                color = [c for c in gs.center if isinstance(c, Color)]
                if color:
                    c = color[0]
                    for li in range(5):
                        if gs.players[gs.current_player].can_place_in_pattern(li, c):
                            gs.current_player_action("center", c, li)
                            break
                    else:
                        gs.current_player_action("center", c, -1)
            turn += 1
        assert gs.game_over or turn < 500

    def test_state_snapshot_roundtrip(self):
        gs1 = GameState()
        gs1.init_bag()
        gs1.start_round()
        snap = gs1.get_state_snapshot()
        gs2 = GameState()
        gs2.load_state_snapshot(snap)
        assert gs2.factories == gs1.factories
        assert gs2.center == gs1.center
        assert gs2.current_player == gs1.current_player
        assert gs2.round == gs1.round


class TestPlayerBoard:
    def test_discard_floor(self):
        board = PlayerBoard()
        board.floor_line = [Color.BLUE, Color.YELLOW, Color.RED]
        penalty = board.discard_floor()
        assert penalty < 0
        assert board.floor_line == []

    def test_has_complete_row(self):
        board = PlayerBoard()
        assert not board.has_complete_row()
        for c in range(5):
            board.wall[0][c] = WALL_LAYOUT[0][c]
        assert board.has_complete_row()

    def test_count_horizontal_rows(self):
        board = PlayerBoard()
        assert board.count_horizontal_rows() == 0
        for c in range(5):
            board.wall[0][c] = WALL_LAYOUT[0][c]
        assert board.count_horizontal_rows() == 1

    def test_count_vertical_cols(self):
        board = PlayerBoard()
        assert board.count_vertical_cols() == 0
        for r in range(5):
            board.wall[r][0] = WALL_LAYOUT[r][0]
        assert board.count_vertical_cols() == 1

    def test_count_full_colors(self):
        board = PlayerBoard()
        assert board.count_full_colors() == 0


from game import WALL_LAYOUT
