from flask import Blueprint, request
from extensions.websocket import sock
from services.auth_service import usuario_do_token
from services.consultas_service import avisar_entrada_na_sala, sala_da_sessao
from services.signaling_service import signaling_service
from util.usuarios import origem_permitida, token_da_requisicao

signaling_bp = Blueprint('signaling', __name__)


@sock.route("/ws/signaling", bp=signaling_bp)
def signaling(ws):
    try:
        if not origem_permitida():
            ws.close()
            return
        token = token_da_requisicao()
        id_usuario = usuario_do_token(token).get("id_usuario") if token else None
        try:
            sessao_id = int(request.args.get("sessao_id", ""))
        except (TypeError, ValueError):
            sessao_id = None

        # sala_da_sessao ja devolveu a conexao do banco: a chamada pode durar uma hora.
        sala = sala_da_sessao(id_usuario, sessao_id) if id_usuario and sessao_id else None
        if not sala:
            ws.close()
            return

        room = f"sessao:{sessao_id}"
        avisar_entrada_na_sala(sala, id_usuario, signaling_service.presentes(room))
        participante = sala['participantes'][id_usuario]
        # E-mail fica no servidor; a sala so fica sabendo quem e quem.
        signaling_service.handle_connection(ws, room, {'id_usuario': id_usuario, 'nome': participante['nome']})
    except Exception as e:
        print("ERRO WS:", repr(e))
        ws.close()
