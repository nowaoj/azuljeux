import json
import socket
import threading
from enum import Enum

class MessageType(Enum):
    CONNECTED = "connected"
    GAME_START = "game_start"
    ACTION = "action"
    STATE_UPDATE = "state_update"
    ERROR = "error"
    DISCONNECT = "disconnect"

HOST = "0.0.0.0"
PORT = 5555
MSG_DELIM = b"\n"


def encode_msg(msg):
    data = json.dumps(msg) + "\n"
    return data.encode("utf-8")


def decode_msg(data):
    return json.loads(data.decode("utf-8"))


class GameServer:
    def __init__(self, game_state, on_state_change=None):
        self.game = game_state
        self.on_state_change = on_state_change
        self.server_socket = None
        self.client_socket = None
        self.running = False
        self.client_ready = False

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((HOST, PORT))
        self.server_socket.listen(1)
        self.server_socket.settimeout(0.5)
        self.running = True
        thread = threading.Thread(target=self._accept_loop, daemon=True)
        thread.start()

    def _accept_loop(self):
        while self.running:
            try:
                client, addr = self.server_socket.accept()
                self.client_socket = client
                self.client_socket.settimeout(0.5)
                self.client_ready = True
                self.send(MessageType.CONNECTED, {"player": 1})
                self.broadcast_state()
                if self.on_state_change:
                    self.on_state_change("client_connected", None)
                listen = threading.Thread(target=self._listen_client, daemon=True)
                listen.start()
            except socket.timeout:
                continue
            except OSError:
                break

    def _listen_client(self):
        buffer = b""
        while self.running and self.client_socket:
            try:
                data = self.client_socket.recv(4096)
                if not data:
                    break
                buffer += data
                while MSG_DELIM in buffer:
                    msg_bytes, buffer = buffer.split(MSG_DELIM, 1)
                    msg = decode_msg(msg_bytes)
                    self._handle_message(msg)
            except socket.timeout:
                continue
            except (ConnectionResetError, OSError):
                break
        self.client_ready = False

    def _handle_message(self, msg):
        msg_type = msg.get("type")
        if msg_type == "action":
            self._handle_action(msg.get("data", {}))

    def _handle_action(self, data):
        action_type = data.get("action_type")
        args = data.get("args", [])
        success = self.game.current_player_action(action_type, *args)
        if success:
            snapshot = self.game.get_state_snapshot()
            self.broadcast_state()
            if self.on_state_change:
                self.on_state_change("state_update", snapshot)
            if self.game.phase == "wall_tiling":
                self.game.resolve_wall_tiling()
                snapshot = self.game.get_state_snapshot()
                self.broadcast_state()
                if self.on_state_change:
                    self.on_state_change("state_update", snapshot)
        else:
            self.send(MessageType.ERROR, {"message": "Action invalide"})

    def broadcast_state(self):
        snapshot = self.game.get_state_snapshot()
        self.send(MessageType.STATE_UPDATE, snapshot)

    def send(self, msg_type, data=None):
        if not self.client_socket:
            return
        msg = {"type": msg_type.value}
        if data is not None:
            msg["data"] = data
        try:
            self.client_socket.sendall(encode_msg(msg))
        except OSError:
            pass

    def send_to_self(self, msg_type, data=None):
        if self.on_state_change:
            self.on_state_change(msg_type.value, data)

    def stop(self):
        self.running = False
        if self.client_socket:
            try:
                self.send(MessageType.DISCONNECT)
                self.client_socket.close()
            except OSError:
                pass
        if self.server_socket:
            self.server_socket.close()


class GameClient:
    def __init__(self, on_state_change=None):
        self.socket = None
        self.running = False
        self.on_state_change = on_state_change

    def connect(self, host_ip):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(5)
        try:
            self.socket.connect((host_ip, PORT))
            self.socket.settimeout(0.5)
            self.running = True
            listen = threading.Thread(target=self._listen, daemon=True)
            listen.start()
            return True
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            return False

    def _listen(self):
        buffer = b""
        while self.running and self.socket:
            try:
                data = self.socket.recv(4096)
                if not data:
                    break
                buffer += data
                while MSG_DELIM in buffer:
                    msg_bytes, buffer = buffer.split(MSG_DELIM, 1)
                    msg = decode_msg(msg_bytes)
                    self._handle_message(msg)
            except socket.timeout:
                continue
            except (ConnectionResetError, OSError):
                break
        self.running = False

    def _handle_message(self, msg):
        msg_type = msg.get("type")
        data = msg.get("data")
        if self.on_state_change:
            self.on_state_change(msg_type, data)

    def send_action(self, action_type, *args):
        if not self.socket:
            return
        msg = {
            "type": MessageType.ACTION.value,
            "data": {
                "action_type": action_type,
                "args": args,
            },
        }
        try:
            self.socket.sendall(encode_msg(msg))
        except OSError:
            pass

    def disconnect(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
