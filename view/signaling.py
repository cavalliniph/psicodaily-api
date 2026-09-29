from flask import Blueprint, request
from extensions.websocket import sock
from services.signaling_service import signaling_service
from funcao import decodificar_token
from database.db import get_connection
from datetime import datetime, timedelta

signaling_bp = Blueprint('signaling', __name__)

@sock.route("/ws/signaling", bp=signaling_bp)
def signaling(ws):
    print("WS CONECTADO")

    token = request.cookies.get("access_token")

    if not token:   # se nao houver token
        ws.close()
        return

    con = None
    cursor = None

    try:
        payload = decodificar_token(token)

        id_usuario = payload.get("id_usuario")
        try:
            sessao_id = int(request.args.get("sessao_id", ""))
        except (TypeError, ValueError):
            ws.close()
            return

        if not sessao_id:   # nao tem como saber qual a
            ws.close()      # sessao se nao informar
            return

        if not id_usuario:  # se o id_usuario nao for
            ws.close()      # informado no payload
            return

        con = get_connection()
        cursor = con.cursor()

        # pegando id do profissional e paciente
        # pra validar se tem permissao de entrar
        # na chamada
        cursor.execute("""
        SELECT paciente_id, profissional_id, status, data_hora_inicio, data_hora_fim
        FROM SESSAO s
        WHERE sessao_id = ?
        """, (sessao_id,))

        resultado_sessao = cursor.fetchone()

        if not resultado_sessao:
            ws.close()
            return

        participantes = list(resultado_sessao[:2])
        # ^^ estamos aqui transformando numa lista
        # pra facilitar a validacao logo abaixo

        pode_entrar: bool = (id_usuario in participantes
                            and resultado_sessao[2] != "CANCELADO"
                            and resultado_sessao[3] <= datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=15)
                            and resultado_sessao[4] >= datetime.now())

        if not pode_entrar:
            ws.close()
            return

        signaling_service.handle_connection(ws, f"sessao:{sessao_id}")

    except Exception as e:
        print("ERRO WS:", repr(e))
        ws.close()

    finally:
        print("WS DESCONECTADO")
        if cursor is not None:
            cursor.close()
        if con is not None:
            con.close()
