import json
import threading

from simple_websocket import ConnectionClosed

RELAYED = {"offer", "answer", "ice-candidate"}


class SignalingService:
    def __init__(self):
        # sala -> {ws: participante publico ({id_usuario, nome})}
        self.rooms = {}
        # ponytail: um lock para todas as salas e envios; por sala se houver muitas chamadas simultaneas
        self.lock = threading.Lock()

    def presentes(self, room):
        with self.lock:
            return {p["id_usuario"] for p in self.rooms.get(room, {}).values()}

    def handle_connection(self, ws, room, participante):
        self.join(ws, room, participante)
        try:
            while True:
                raw_message = ws.receive()
                if raw_message is None:
                    break
                try:
                    message = json.loads(raw_message)
                except ValueError:
                    continue
                if isinstance(message, dict) and message.get("type") in RELAYED:
                    self.broadcast(ws, room, message)
        except ConnectionClosed:
            pass
        finally:
            self.leave(ws, room)

    def join(self, ws, room, participante):
        with self.lock:
            sala = self.rooms.setdefault(room, {})
            ja_na_sala = list(sala.values())
            sala[ws] = participante
            self._send(ws, {"type": "peers", "participantes": ja_na_sala})
            self._send_others(ws, room, {"type": "peer-joined", **participante})

    def leave(self, ws, room):
        with self.lock:
            sala = self.rooms.get(room, {})
            participante = sala.pop(ws, None)
            if participante:
                self._send_others(ws, room, {"type": "peer-left", **participante})
            if not sala:
                self.rooms.pop(room, None)

    def broadcast(self, sender, room, message):
        with self.lock:
            self._send_others(sender, room, message)

    def _send_others(self, sender, room, message):
        for connection in self.rooms.get(room, {}):
            if connection is not sender:
                self._send(connection, message)

    @staticmethod
    def _send(connection, message):
        try:
            connection.send(json.dumps(message))
        except ConnectionClosed:
            # O receive() dessa conexao vai terminar e chamar leave().
            pass


signaling_service = SignalingService()
