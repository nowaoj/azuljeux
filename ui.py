import pygame
import math
from game import Color, COLOR_NAMES, COLOR_RGB, WALL_LAYOUT, FLOOR_PENALTIES, FACTORY_COUNT

REF_W = 1280
REF_H = 960

BG_COLOR = (40, 42, 48)
PANEL_COLOR = (52, 55, 62)
TEXT_COLOR = (220, 220, 220)
HIGHLIGHT_COLOR = (255, 200, 50)
DIM_TEXT = (150, 150, 150)
PENALTY_COLORS = {
    -1: (200, 100, 100),
    -2: (200, 70, 70),
    -3: (200, 40, 40),
}

COLOR_DISPLAY = {
    Color.BLUE: (0, 140, 220),
    Color.YELLOW: (250, 210, 30),
    Color.RED: (210, 40, 40),
    Color.BLACK: (50, 50, 55),
    Color.WHITE: (230, 225, 215),
}

WALL_COLORS_DISPLAY = {
    Color.BLUE: (0, 100, 170),
    Color.YELLOW: (200, 170, 10),
    Color.RED: (170, 20, 20),
    Color.BLACK: (35, 35, 40),
    Color.WHITE: (200, 195, 185),
}

LIGHT_COLORS = {
    Color.BLUE: (100, 180, 240),
    Color.YELLOW: (255, 230, 100),
    Color.RED: (240, 100, 100),
    Color.BLACK: (100, 100, 105),
    Color.WHITE: (255, 255, 250),
}

VALID_LINE_COLOR = (140, 140, 145)
SELECTED_LINE_COLOR = (170, 170, 175)


def draw_rounded_rect(surface, color, rect, radius=8):
    pygame.draw.rect(surface, color, rect, border_radius=radius)


def draw_tile(surface, color_enum, x, y, size=44, border=True):
    rgb = COLOR_DISPLAY.get(color_enum, (128, 128, 128))
    rect = pygame.Rect(x, y, size, size)
    draw_rounded_rect(surface, rgb, rect, max(3, size // 7))
    if border:
        pygame.draw.rect(surface, (255, 255, 255, 60), rect, max(1, size // 22), border_radius=max(3, size // 7))
    inner = pygame.Rect(x + size // 11 + 1, y + size // 11 + 1, size - size // 5 - 2, size - size // 5 - 2)
    lighter = tuple(min(255, c + 40) for c in rgb)
    draw_rounded_rect(surface, lighter, inner, max(2, size // 11))


def draw_empty_slot(surface, x, y, size=44, color=(60, 62, 68)):
    rect = pygame.Rect(x, y, size, size)
    draw_rounded_rect(surface, color, rect, max(3, size // 7))
    pygame.draw.rect(surface, (70, 72, 78), rect, 1, border_radius=max(3, size // 7))


class AzulUI:
    def __init__(self, is_host=True):
        pygame.init()
        info = pygame.display.Info()
        self.WIDTH = info.current_w
        self.HEIGHT = info.current_h
        self.scale = min(self.WIDTH / REF_W, self.HEIGHT / REF_H)

        self.OPP_BOARD_H = self.s(115)
        self.MY_BOARD_H = self.s(190)

        self.screen = pygame.display.set_mode((self.WIDTH, self.HEIGHT), pygame.FULLSCREEN)
        pygame.display.set_caption("Azul - Jeu à 2 Joueurs")
        self.clock = pygame.time.Clock()

        self.font_large = pygame.font.Font(None, self.s(36))
        self.font_med = pygame.font.Font(None, self.s(28))
        self.font_small = pygame.font.Font(None, self.s(22))

        self.is_host = is_host
        self.my_player = 0 if is_host else 1
        self.opponent = 1 if is_host else 0

        self.state = None
        self.selected_factory = -1
        self.selected_color = None
        self.selected_center = False
        self.valid_lines = []
        self.message = ""
        self.message_timer = 0
        self.selected_dest_row = None
        self.confirm_btn_rect = None
        self.connected = False
        self.game_started = False
        self.waiting_for_opponent = not is_host
        self.connection_status = ""

    def s(self, v):
        return int(v * self.scale + 0.5)

    def set_state(self, state_snapshot):
        self.state = state_snapshot
        self.valid_lines = []
        self.selected_factory = -1
        self.selected_center = False
        self.selected_color = None
        self.selected_dest_row = None
        self.confirm_btn_rect = None

    def set_message(self, msg, duration=120):
        self.message = msg
        self.message_timer = duration

    def update(self):
        if self.message_timer > 0:
            self.message_timer -= 1

    def draw(self):
        self.screen.fill(BG_COLOR)

        if not self.connected:
            self._draw_connection_screen()
        elif not self.game_started:
            self._draw_waiting_screen()
        elif not self.state:
            self._draw_waiting_screen()
        else:
            self._draw_game()

        pygame.display.flip()
        self.clock.tick(60)

    def _draw_connection_screen(self):
        center_x = self.WIDTH // 2
        y = self.HEIGHT // 2 - self.s(60)

        title = self.font_large.render("Azul", True, TEXT_COLOR)
        self.screen.blit(title, (center_x - title.get_width() // 2, y - self.s(40)))

        if self.is_host:
            st = self.font_med.render("Hôte - En attente du joueur 2...", True, TEXT_COLOR)
            ip_text = self.font_small.render("IP locale utilisée pour la connexion", True, DIM_TEXT)
            self.screen.blit(st, (center_x - st.get_width() // 2, y))
            self.screen.blit(ip_text, (center_x - ip_text.get_width() // 2, y + self.s(40)))
        else:
            st = self.font_med.render("Client - Connexion en cours...", True, TEXT_COLOR)
            self.screen.blit(st, (center_x - st.get_width() // 2, y))

        if self.connection_status:
            cs = self.font_small.render(self.connection_status, True, HIGHLIGHT_COLOR)
            self.screen.blit(cs, (center_x - cs.get_width() // 2, y + self.s(80)))

    def _draw_waiting_screen(self):
        center_x = self.WIDTH // 2
        y = self.HEIGHT // 2 - self.s(40)

        if self.state:
            txt = self.font_large.render("Partie en cours...", True, TEXT_COLOR)
            self.screen.blit(txt, (center_x - txt.get_width() // 2, y))
        else:
            txt = self.font_med.render("En attente de l'autre joueur...", True, TEXT_COLOR)
            self.screen.blit(txt, (center_x - txt.get_width() // 2, y))

        if self.connection_status:
            cs = self.font_small.render(self.connection_status, True, HIGHLIGHT_COLOR)
            self.screen.blit(cs, (center_x - cs.get_width() // 2, y + self.s(50)))

    def _draw_game(self):
        if not self.state:
            return

        phase = self.state.get("phase", "")
        rnd = self.state.get("round", 1)
        current = self.state.get("current_player", 0)
        is_my_turn = current == self.my_player

        if phase == "game_over":
            self._draw_game_over()
            return

        header = f"Manche {rnd} - "
        if phase == "factory_offer":
            header += "Phase d'offre"
        else:
            header += "Phase de pose"

        hdr = self.font_large.render(header, True, TEXT_COLOR)
        self.screen.blit(hdr, (self.s(20), self.s(8)))

        turn_text = "\xC0 vous de jouer!" if is_my_turn else "Tour de l'adversaire..."
        turn_color = HIGHLIGHT_COLOR if is_my_turn else DIM_TEXT
        turn = self.font_med.render(turn_text, True, turn_color)
        self.screen.blit(turn, (self.WIDTH - turn.get_width() - self.s(20), self.s(10)))

        factories = self.state.get("factories", [])
        center = self.state.get("center", [])
        players = self.state.get("players", [])

        self._draw_factories(factories, center, is_my_turn)
        my_board_y = self.s(500)
        opp_board_y = self.s(18)
        self._draw_player_board(players[self.my_player], my_board_y, True, is_my_turn)
        self._draw_player_board(players[self.opponent], opp_board_y, False, False)

        if self.selected_color is not None and is_my_turn:
            self._draw_selection_panel()

        if self.message and self.message_timer > 0:
            msg_surf = self.font_med.render(self.message, True, HIGHLIGHT_COLOR)
            mx = (self.WIDTH - msg_surf.get_width()) // 2
            self.screen.blit(msg_surf, (mx, self.HEIGHT - self.s(40)))

    def _draw_factories(self, factories, center, is_my_turn):
        cx = self.WIDTH // 2
        cy = self.s(290)
        factory_radius = self.s(48)

        for i in range(FACTORY_COUNT):
            angle = -math.pi / 2 + (i / FACTORY_COUNT) * 2 * math.pi
            fx = cx + int(factory_radius * 3.2 * math.cos(angle))
            fy = cy + int(factory_radius * 2.0 * math.sin(angle))
            self._draw_factory(fx, fy, i, factories[i], is_my_turn)

        self._draw_center_pile(cx, self.s(430), center, is_my_turn)

    def _draw_factory(self, x, y, idx, tiles, is_my_turn):
        fw = self.s(84)
        fhalf = self.s(42)
        rect = pygame.Rect(x - fhalf, y - fhalf, fw, fw)
        color = HIGHLIGHT_COLOR if (self.selected_factory == idx and is_my_turn) else PANEL_COLOR
        draw_rounded_rect(self.screen, color, rect, self.s(10))
        pygame.draw.rect(self.screen, (80, 82, 88), rect, 2, border_radius=self.s(10))

        label = self.font_small.render(f"F{idx + 1}", True, DIM_TEXT)
        self.screen.blit(label, (x - label.get_width() // 2, y - fhalf + self.s(4)))

        tile_positions = [(-self.s(15), -self.s(15)), (self.s(15), -self.s(15)), (-self.s(15), self.s(15)), (self.s(15), self.s(15))]
        ts = self.s(20)
        for j, tile in enumerate(tiles):
            if j < len(tile_positions):
                tx = x + tile_positions[j][0]
                ty = y + tile_positions[j][1]
                draw_tile(self.screen, Color(tile), tx, ty, ts)

    def _draw_center_pile(self, x, y, center, is_my_turn):
        cw = self.s(160)
        ch = self.s(52)
        rect = pygame.Rect(x - cw // 2, y - ch // 2, cw, ch)
        col = HIGHLIGHT_COLOR if self.selected_center else PANEL_COLOR
        draw_rounded_rect(self.screen, col, rect, self.s(8))
        pygame.draw.rect(self.screen, (80, 82, 88), rect, 2, border_radius=self.s(8))

        lbl = self.font_small.render("Centre", True, DIM_TEXT)
        self.screen.blit(lbl, (x - lbl.get_width() // 2, y - ch // 2 + self.s(6)))

        real_tiles = [c for c in center if not isinstance(c, str)]
        has_start = any(c == "START" for c in center)
        tile_sz = self.s(16)
        start_x = x - (len(real_tiles) * tile_sz) // 2
        for i, tile in enumerate(real_tiles):
            draw_tile(self.screen, Color(tile), start_x + i * tile_sz, y + self.s(4), tile_sz)
        if has_start:
            pygame.draw.circle(self.screen, (255, 200, 50), (x + cw // 2 - self.s(16), y + self.s(10)), self.s(6))
            pygame.draw.circle(self.screen, (255, 255, 255), (x + cw // 2 - self.s(16), y + self.s(10)), self.s(4))

    def _draw_selection_panel(self):
        if self.selected_color is None:
            return

        factories = self.state.get("factories", [])
        center = self.state.get("center", [])

        count = 0
        source_name = ""

        if self.selected_factory >= 0:
            factory_tiles = factories[self.selected_factory]
            count = sum(1 for t in factory_tiles if t == self.selected_color.value)
            source_name = f"F{self.selected_factory + 1}"
        elif self.selected_center:
            real_tiles = [c for c in center if not isinstance(c, str)]
            count = sum(1 for t in real_tiles if t == self.selected_color.value)
            source_name = "Centre"

        pw = self.s(260)
        ph = self.s(55)
        px = self.WIDTH // 2 - pw // 2
        py = self.s(160)

        rect = pygame.Rect(px, py, pw, ph)
        draw_rounded_rect(self.screen, (60, 62, 68), rect, self.s(8))
        pygame.draw.rect(self.screen, (80, 82, 88), rect, 2, border_radius=self.s(8))

        tile_sz = self.s(28)
        draw_tile(self.screen, self.selected_color, px + self.s(12), py + (ph - tile_sz) // 2, tile_sz)

        count_text = self.font_med.render(f"x{count}", True, TEXT_COLOR)
        self.screen.blit(count_text, (px + self.s(50), py + self.s(6)))

        src_text = self.font_small.render(source_name, True, DIM_TEXT)
        self.screen.blit(src_text, (px + self.s(50), py + self.s(28)))

        if self.selected_dest_row is not None:
            dest_text = self.font_small.render(f"Ligne {self.selected_dest_row + 1}", True, TEXT_COLOR)
            self.screen.blit(dest_text, (px + self.s(120), py + self.s(8)))

            btn_w = self.s(90)
            btn_h = self.s(28)
            btn_x = px + pw - btn_w - self.s(10)
            btn_y = py + (ph - btn_h) // 2
            btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
            draw_rounded_rect(self.screen, (70, 140, 70), btn_rect, self.s(5))
            pygame.draw.rect(self.screen, (90, 170, 90), btn_rect, 1, border_radius=self.s(5))

            btn_text = self.font_small.render("Confirmer", True, (255, 255, 255))
            self.screen.blit(btn_text, (btn_x + (btn_w - btn_text.get_width()) // 2, btn_y + (btn_h - btn_text.get_height()) // 2))

            self.confirm_btn_rect = btn_rect
        else:
            self.confirm_btn_rect = None

        hint = self.font_small.render("Cliquez sur une ligne de motif ci-dessous", True, DIM_TEXT)
        self.screen.blit(hint, (px, py + ph + self.s(4)))

    def _draw_player_board(self, player, y_pos, is_me, is_my_turn):
        px = self.s(40)
        pwidth = self.WIDTH - self.s(80)
        board_height = self.MY_BOARD_H if is_me else self.OPP_BOARD_H
        board_rect = pygame.Rect(px, y_pos, pwidth, board_height)
        base_color = (72, 75, 82) if not is_me else (60, 63, 70)
        draw_rounded_rect(self.screen, base_color, board_rect, self.s(10))
        pygame.draw.rect(self.screen, (90, 93, 100), board_rect, 2, border_radius=self.s(10))

        score = player.get("score", 0)
        label_text = f"Joueur {'1' if is_me else '2'} (Vous)" if is_me else f"Joueur {'2' if is_my_turn else '1'}"
        lbl = self.font_med.render(label_text, True, TEXT_COLOR)
        self.screen.blit(lbl, (px + self.s(15), y_pos + self.s(8)))

        sc = self.font_med.render(f"Score: {score}", True, HIGHLIGHT_COLOR)
        self.screen.blit(sc, (px + pwidth - sc.get_width() - self.s(15), y_pos + self.s(8)))

        if is_me and is_my_turn and self.state.get("phase") == "factory_offer":
            instruct = self.font_small.render(
                "Cliquez sur un carreau, choisissez une ligne de motif, puis Confirmer",
                True, (200, 200, 100),
            )
            self.screen.blit(instruct, (px + self.s(15), y_pos + board_height - self.s(18)))

        if is_me:
            self._draw_pattern_lines(player, px + self.s(15), y_pos + self.s(38), self.s(22), self.s(20))
            self._draw_wall(player, px + self.s(160), y_pos + self.s(38), self.s(26))
            self._draw_floor_line(player, px + self.s(15), y_pos + self.s(145))
        else:
            self._draw_pattern_lines(player, px + self.s(15), y_pos + self.s(35), self.s(14), self.s(14))
            self._draw_wall(player, px + self.s(125), y_pos + self.s(35), self.s(16))

    def _draw_pattern_lines(self, player, x, y, row_h, tile_sz):
        pattern_lines = player.get("pattern_lines", [])
        label_offset = self.s(18) if tile_sz > self.s(14) else self.s(14)
        for i in range(5):
            max_size = i + 1
            line_x = x
            line_y = y + i * row_h

            lbl = self.font_small.render(f"{i + 1}:", True, DIM_TEXT)
            self.screen.blit(lbl, (line_x - label_offset, line_y))

            can_use = i in self.valid_lines
            is_selected = (self.selected_dest_row == i)
            for j in range(max_size):
                tx = line_x + j * tile_sz
                if j < len(pattern_lines[i]):
                    draw_tile(self.screen, Color(pattern_lines[i][j]), tx, line_y, tile_sz)
                else:
                    if can_use and j == len(pattern_lines[i]):
                        col = SELECTED_LINE_COLOR if is_selected else VALID_LINE_COLOR
                    else:
                        col = (65, 67, 73)
                    draw_empty_slot(self.screen, tx, line_y, tile_sz, col)

    def _draw_wall(self, player, x, y, ts):
        wall = player.get("wall", [])
        gap = ts + self.s(2)
        for r in range(5):
            for c in range(5):
                wx = x + c * gap
                wy = y + r * gap
                wall_color = WALL_LAYOUT[r][c]
                if wall[r][c] is not None:
                    draw_tile(self.screen, Color(wall[r][c]), wx, wy, ts)
                else:
                    rgb = WALL_COLORS_DISPLAY.get(wall_color, (60, 60, 60))
                    rect = pygame.Rect(wx, wy, ts, ts)
                    lighter = tuple(min(255, c2 + 30) for c2 in rgb)
                    draw_rounded_rect(self.screen, lighter, rect, max(2, ts // 6))
                    pygame.draw.rect(self.screen, (80, 82, 88), rect, 1, border_radius=max(2, ts // 6))

    def _draw_floor_line(self, player, x, y):
        floor_line = player.get("floor_line", [])
        lbl = self.font_small.render("Plancher:", True, DIM_TEXT)
        self.screen.blit(lbl, (x, y))

        ts = self.s(22)
        for i in range(7):
            fx = x + self.s(75) + i * self.s(26)
            if i < len(floor_line):
                tile = floor_line[i]
                if tile == "START":
                    pygame.draw.circle(self.screen, (255, 200, 50), (fx + ts // 2, y + ts // 2), ts // 2)
                    pygame.draw.circle(self.screen, (255, 255, 255), (fx + ts // 2, y + ts // 2), ts // 2 - 2)
                else:
                    draw_tile(self.screen, Color(tile), fx, y, ts)
            else:
                draw_empty_slot(self.screen, fx, y, ts, (55, 57, 63))
            penalty = FLOOR_PENALTIES[i] if i < len(FLOOR_PENALTIES) else 0
            pnl = self.font_small.render(str(penalty), True, PENALTY_COLORS.get(penalty, DIM_TEXT))
            self.screen.blit(pnl, (fx + self.s(6), y + ts + self.s(2)))

    def _draw_game_over(self):
        overlay = pygame.Surface((self.WIDTH, self.HEIGHT))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        cx = self.WIDTH // 2
        cy = self.HEIGHT // 2

        winner = self.state.get("winner", -1)
        p0_score = self.state["players"][0]["score"]
        p1_score = self.state["players"][1]["score"]

        if winner == self.my_player:
            result = "Vous avez gagn\xe9!"
            result_color = (100, 255, 100)
        elif winner == self.opponent:
            result = "L'adversaire a gagn\xe9!"
            result_color = (255, 100, 100)
        else:
            result = "\xc9galit\xe9!"
            result_color = HIGHLIGHT_COLOR

        title = self.font_large.render("Partie termin\xe9e!", True, TEXT_COLOR)
        self.screen.blit(title, (cx - title.get_width() // 2, cy - self.s(80)))

        res = self.font_large.render(result, True, result_color)
        self.screen.blit(res, (cx - res.get_width() // 2, cy - self.s(35)))

        s0 = self.font_med.render(f"Joueur 1: {p0_score} points", True, TEXT_COLOR)
        s1 = self.font_med.render(f"Joueur 2: {p1_score} points", True, TEXT_COLOR)
        self.screen.blit(s0, (cx - s0.get_width() // 2, cy + self.s(10)))
        self.screen.blit(s1, (cx - s1.get_width() // 2, cy + self.s(45)))

        close = self.font_small.render("Appuyez sur ESPACE pour quitter", True, DIM_TEXT)
        self.screen.blit(close, (cx - close.get_width() // 2, cy + self.s(95)))

    def draw_menu(self):
        self.screen.fill(BG_COLOR)
        cx = self.WIDTH // 2

        title = self.font_large.render("AZUL", True, (255, 200, 50))
        self.screen.blit(title, (cx - title.get_width() // 2, self.s(200)))

        subtitle = self.font_med.render("Jeu \xe0 2 Joueurs en ligne", True, (220, 220, 220))
        self.screen.blit(subtitle, (cx - subtitle.get_width() // 2, self.s(250)))

        bw = self.s(240)
        bh = self.s(50)
        bx = cx - bw // 2

        host_rect = pygame.Rect(bx, self.s(340), bw, bh)
        pygame.draw.rect(self.screen, (60, 130, 60), host_rect, border_radius=self.s(8))
        pygame.draw.rect(self.screen, (80, 160, 80), host_rect, 2, border_radius=self.s(8))
        host_txt = self.font_med.render("H\xe9berger la partie", True, (255, 255, 255))
        self.screen.blit(host_txt, (cx - host_txt.get_width() // 2, self.s(340) + self.s(15)))

        join_rect = pygame.Rect(bx, self.s(410), bw, bh)
        pygame.draw.rect(self.screen, (60, 100, 160), join_rect, border_radius=self.s(8))
        pygame.draw.rect(self.screen, (80, 130, 190), join_rect, 2, border_radius=self.s(8))
        join_txt = self.font_med.render("Rejoindre une partie", True, (255, 255, 255))
        self.screen.blit(join_txt, (cx - join_txt.get_width() // 2, self.s(410) + self.s(15)))

        return host_rect, join_rect

    def draw_ip_dialog(self, ip, input_active):
        self.screen.fill(BG_COLOR)
        cx = self.WIDTH // 2

        lbl = self.font_med.render("Adresse IP de l'h\xf4te:", True, (220, 220, 220))
        self.screen.blit(lbl, (cx - lbl.get_width() // 2, self.s(300)))

        iw = self.s(240)
        ih = self.s(40)
        input_rect = pygame.Rect(cx - iw // 2, self.s(340), iw, ih)
        col = (80, 130, 190) if input_active else (70, 72, 78)
        pygame.draw.rect(self.screen, col, input_rect, border_radius=self.s(6))
        pygame.draw.rect(self.screen, (120, 120, 120), input_rect, 2, border_radius=self.s(6))

        ip_surf = self.font_med.render(ip, True, (255, 255, 255))
        self.screen.blit(ip_surf, (cx - ip_surf.get_width() // 2, self.s(350)))

        hint = self.font_small.render("Entrez l'IP puis ENTR\xc9E", True, (150, 150, 150))
        self.screen.blit(hint, (cx - hint.get_width() // 2, self.s(395)))

        if self.connection_status:
            st = self.font_small.render(self.connection_status, True, (255, 200, 50))
            self.screen.blit(st, (cx - st.get_width() // 2, self.s(430)))

    def handle_click(self, pos):
        if not self.state or self.state.get("game_over"):
            return None

        phase = self.state.get("phase", "")
        if phase != "factory_offer":
            return None

        current = self.state.get("current_player", -1)
        if current != self.my_player:
            return None

        if self.selected_dest_row is not None:
            if self.confirm_btn_rect and self.confirm_btn_rect.collidepoint(pos):
                return self._make_action(self.selected_dest_row)

        tile_result = self._check_tile_click(pos)
        if tile_result is not None:
            return tile_result

        if self.selected_color is not None:
            self._check_pattern_click(pos)

        return None

    def _check_tile_click(self, pos):
        factories = self.state.get("factories", [])
        cx = self.WIDTH // 2
        cy = self.s(290)
        factory_radius = self.s(48)

        for i in range(FACTORY_COUNT):
            if not factories[i]:
                continue
            angle = -math.pi / 2 + (i / FACTORY_COUNT) * 2 * math.pi
            fx = cx + int(factory_radius * 3.2 * math.cos(angle))
            fy = cy + int(factory_radius * 2.0 * math.sin(angle))

            tile_positions = [(-self.s(15), -self.s(15)), (self.s(15), -self.s(15)), (-self.s(15), self.s(15)), (self.s(15), self.s(15))]
            ts = self.s(20)
            for j, tile in enumerate(factories[i]):
                if j < len(tile_positions):
                    tx = fx + tile_positions[j][0]
                    ty = fy + tile_positions[j][1]
                    tile_rect = pygame.Rect(tx, ty, ts, ts)
                    if tile_rect.collidepoint(pos):
                        return self._select_color("factory", i, Color(tile))

        center = self.state.get("center", [])
        real_tiles = [c for c in center if not isinstance(c, str)]
        if real_tiles:
            cw = self.s(160)
            ch = self.s(52)
            tile_sz = self.s(16)
            start_x = cx - (len(real_tiles) * tile_sz) // 2
            cy = self.s(430)
            for i, tile in enumerate(real_tiles):
                tx = start_x + i * tile_sz
                ty = cy + self.s(4)
                tile_rect = pygame.Rect(tx, ty, tile_sz, tile_sz)
                if tile_rect.collidepoint(pos):
                    return self._select_color("center", -1, Color(tile))

        return None

    def _select_color(self, source_type, factory_idx, color):
        if source_type == "factory":
            self.selected_factory = factory_idx
            self.selected_center = False
        else:
            self.selected_factory = -1
            self.selected_center = True

        self.selected_color = color
        self.selected_dest_row = None
        self._update_valid_lines()

        if not self.valid_lines:
            return self._make_action(-1)

        return None

    def _check_pattern_click(self, pos):
        player = self.state.get("players", [{}])[self.my_player]
        pattern_lines = player.get("pattern_lines", [])
        x = self.s(55)
        y = self.s(500) + self.s(38)
        tile_sz = self.s(20)
        row_h = self.s(22)

        for i in range(5):
            max_size = i + 1
            line_x = x
            line_y = y + i * row_h

            for j in range(max_size):
                tx = line_x + j * tile_sz
                if j >= len(pattern_lines[i]):
                    tile_rect = pygame.Rect(tx, line_y, tile_sz, row_h)
                    if tile_rect.collidepoint(pos) and i in self.valid_lines:
                        self.selected_dest_row = i
                        return

        return None

    def _update_valid_lines(self):
        if not self.state or self.selected_color is None:
            self.valid_lines = []
            return
        my_board = self.state.get("players", [{}])[self.my_player]
        wall = my_board.get("wall", [])
        pattern_lines = my_board.get("pattern_lines", [])

        self.valid_lines = []
        for i in range(5):
            if len(pattern_lines[i]) >= i + 1:
                continue
            if len(pattern_lines[i]) > 0 and pattern_lines[i][0] != self.selected_color.value:
                continue
            wall_color = WALL_LAYOUT[i]
            for c in range(5):
                if wall_color[c] == self.selected_color and wall[i][c] is not None:
                    break
            else:
                self.valid_lines.append(i)

    def _make_action(self, line_idx):
        if self.selected_factory >= 0:
            action = ("factory", self.selected_factory, self.selected_color.value, line_idx)
        elif self.selected_center:
            action = ("center", self.selected_color.value, line_idx)
        else:
            return None

        self.selected_factory = -1
        self.selected_center = False
        self.selected_color = None
        self.selected_dest_row = None
        self.confirm_btn_rect = None
        self.valid_lines = []
        return action
