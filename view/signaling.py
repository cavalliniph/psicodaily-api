from flask import Blueprint
from extensions.websocket import sock
from services.signaling_service import signaling_service

signaling_bp = Blueprint('signaling', __name__)

@sock.route("/ws/signaling", bp=signaling_bp)
def signaling(ws):
    print("WS CONECTADO")

    try:
        signaling_service.handle_connection(ws)

    except Exception as e:
        print("ERRO WS:", repr(e))

    finally:
        print("WS DESCONECTADO")
