import sys
import socket
import pygame
from game import GameState, Color
from ui import AzulUI
from network import GameServer, GameClient


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


class AzulApp:
    def __init__(self):
        self.ui = AzulUI()
        self.game = None
        self.server = None
        self.client = None
        self.is_host = None
        self.running = True
        self.my_player = 0
        self.state_snapshot = None
        self.client_connected = False

    def run(self):
        self._show_menu()
        while self.running:
            self.ui.update()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    if event.key == pygame.K_SPACE and self._is_game_over():
                        self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._handle_mouse_click(event.pos)

            if self.is_host is None:
                pass
            elif not self.ui.game_started:
                if self.client_connected and self.state_snapshot:
                    self.ui.game_started = True

            self.ui.draw()

        self._cleanup()
        pygame.quit()
        sys.exit()

    def _show_menu(self):
        menu_running = True
        host_rect = None
        join_rect = None

        while menu_running and self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    menu_running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                        menu_running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos

                    if host_rect and host_rect.collidepoint(mx, my):
                        self.is_host = True
                        self.my_player = 0
                        self.ui.is_host = True
                        self.ui.my_player = 0
                        self.ui.opponent = 1
                        self._start_host()
                        menu_running = False
                    elif join_rect and join_rect.collidepoint(mx, my):
                        self.is_host = False
                        self.my_player = 1
                        self.ui.is_host = False
                        self.ui.my_player = 1
                        self.ui.opponent = 0
                        self._show_ip_dialog()
                        menu_running = False

            host_rect, join_rect = self.ui.draw_menu()
            pygame.display.flip()
            self.ui.clock.tick(60)

    def _start_host(self):
        self.game = GameState()
        self.game.init_bag()
        self.game.start_round()

        self.state_snapshot = self.game.get_state_snapshot()
        self.ui.set_state(self.state_snapshot)

        self.server = GameServer(self.game, self._on_host_state_change)
        self.server.start()
        self.ui.connected = True
        self.ui.connection_status = f"IP: {get_local_ip()} - En attente du joueur 2..."
        self.ui.waiting_for_opponent = True

        self.client_connected = False

    def _on_host_state_change(self, msg_type, data):
        if msg_type == "client_connected":
            self.client_connected = True
            self.ui.waiting_for_opponent = False
            self.ui.connection_status = "Joueur 2 connect\xe9!"
        elif msg_type == "state_update":
            self.state_snapshot = data
            self.ui.set_state(data)
            self.ui.game_started = True

    def _show_ip_dialog(self):
        ip = ""
        active = True
        input_active = True

        while active and self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    active = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        active = False
                        self.running = False
                    elif event.key == pygame.K_RETURN:
                        if ip:
                            self._start_client(ip.strip())
                            active = False
                    elif event.key == pygame.K_BACKSPACE:
                        ip = ip[:-1]
                    else:
                        if len(ip) < 20 and (event.unicode.isdigit() or event.unicode == '.'):
                            ip += event.unicode
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    pass

            self.ui.draw_ip_dialog(ip, input_active)

            pygame.display.flip()
            self.ui.clock.tick(60)

    def _start_client(self, host_ip):
        self.client = GameClient(self._on_client_message)
        success = self.client.connect(host_ip)
        if success:
            self.ui.connected = True
            self.ui.waiting_for_opponent = False
        else:
            self.ui.connection_status = "Connexion \xe9chou\xe9e. V\xe9rifiez l'IP."

    def _on_client_message(self, msg_type, data):
        if msg_type == "connected":
            self.my_player = data.get("player", 1)
            self.ui.my_player = self.my_player
            self.ui.opponent = 1 - self.my_player
            self.client_connected = True
        elif msg_type == "state_update":
            self.state_snapshot = data
            self.ui.set_state(data)
            self.ui.game_started = True
        elif msg_type == "error":
            self.ui.set_message(data.get("message", "Erreur"), 180)
        elif msg_type == "disconnect":
            self.ui.set_message("L'adversaire s'est d\xe9connect\xe9", 300)

    def _handle_mouse_click(self, pos):
        if not self.client_connected:
            return
        if self.state_snapshot and self.state_snapshot.get("game_over"):
            return

        action = self.ui.handle_click(pos)
        if action:
            if self.is_host:
                self._execute_host_action(action)
            else:
                self.client.send_action(*action)

    def _execute_host_action(self, action):
        if not self.game:
            return
        action_type = action[0]
        args = action[1:]
        success = self.game.current_player_action(action_type, *args)
        if success:
            self.state_snapshot = self.game.get_state_snapshot()
            self.ui.set_state(self.state_snapshot)
            if self.server:
                self.server.broadcast_state()
            if self.game.phase == "wall_tiling":
                self.game.resolve_wall_tiling()
                self.state_snapshot = self.game.get_state_snapshot()
                self.ui.set_state(self.state_snapshot)
                if self.server:
                    self.server.broadcast_state()

    def _cleanup(self):
        if self.server:
            self.server.stop()
        if self.client:
            self.client.disconnect()

    def _is_game_over(self):
        return self.state_snapshot and self.state_snapshot.get("game_over", False)


if __name__ == "__main__":
    app = AzulApp()
    app.run()
