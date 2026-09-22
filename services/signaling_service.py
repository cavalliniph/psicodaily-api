from collections import defaultdict
import json

class SignalingService:
    def __init__(self):
        self.rooms = defaultdict(set)

    def handle_connection(self, ws):
        current_room = None

        try:
            while True:
                raw_message = ws.receive()

                if raw_message is None:
                    break

                message = json.loads(raw_message)
                message_type = message.get("type")

                if message_type == "join":
                    current_room = message["room"]
                    self.join(ws, current_room)

                elif message_type in {
                    "offer",
                    "answer",
                    "ice-candidate",
                }:
                    self.broadcast(
                        ws,
                        current_room,
                        message
                    )

        finally:
            if current_room:
                self.leave(ws, current_room)
    def join(self, ws, room):
        self.rooms[room].add(ws)

    def leave(self, ws, room):
        self.rooms[room].discard(ws)

        if not self.rooms[room]:
            del self.rooms[room]

    def broadcast(self, sender, room, message):
        if not room or room not in self.rooms:
            return

        data = json.dumps(message)

        for connection in self.rooms[room]:
            if connection != sender:
                connection.send(data)

signaling_service = SignalingService()
