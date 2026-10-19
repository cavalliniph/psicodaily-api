from flask import Blueprint, request
from extensions.websocket import sock
from services.auth_service import decodificar_token
from services.consultas_service import pode_entrar_na_sala
from services.signaling_service import signaling_service

signaling_bp = Blueprint('signaling', __name__)


@sock.route("/ws/signaling", bp=signaling_bp)
def signaling(ws):
    try:
        token = request.cookies.get("access_token")
        id_usuario = decodificar_token(token).get("id_usuario") if token else None
        try:
            sessao_id = int(request.args.get("sessao_id", ""))
        except (TypeError, ValueError):
            sessao_id = None

        # pode_entrar_na_sala ja devolveu a conexao do banco: a chamada pode durar uma hora.
        if not id_usuario or not sessao_id or not pode_entrar_na_sala(id_usuario, sessao_id):
            ws.close()
            return

        signaling_service.handle_connection(ws, f"sessao:{sessao_id}")
    except Exception as e:
        print("ERRO WS:", repr(e))
        ws.close()
