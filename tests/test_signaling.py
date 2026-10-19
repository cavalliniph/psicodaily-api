# Precisa do Firebird no ar: python tests/test_signaling.py
# Sobe o app numa porta local e conecta clientes WebSocket como o front.
# Usa o profissional 22 e os pacientes 23 e 25 do banco local; desfaz tudo o que cria.
import json
import os
import sys
import threading
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import simple_websocket
from werkzeug.serving import make_server

from app import app
from database.db import get_connection
from services import consultas_service
from services.auth_service import gerar_token

PROFISSIONAL, PACIENTE, OUTRO_PACIENTE = 22, 23, 25
PORTA = 5057


def executar(sql, params=()):
    con = get_connection()
    cur = con.cursor()
    cur.execute(sql, params)
    linha = cur.fetchone() if cur.description else None
    con.commit()
    con.close()
    return linha


def nova_sessao(inicio, fim):
    return executar('''INSERT INTO SESSAO (PACIENTE_ID, PROFISSIONAL_ID, DATA_HORA_INICIO, DATA_HORA_FIM,
        STATUS, VALOR_CENTAVOS) VALUES (?, ?, ?, ?, 'AGENDADO', 100) RETURNING SESSAO_ID''',
                    (PACIENTE, PROFISSIONAL, inicio, fim))[0]


def conectar(id_usuario, papel, sessao_id):
    token = gerar_token({'id_usuario': id_usuario, 'usuario_role': papel})
    ws = simple_websocket.Client.connect(f'ws://127.0.0.1:{PORTA}/ws/signaling?sessao_id={sessao_id}',
                                         headers={'Cookie': f'access_token={token}'})
    clientes.append(ws)
    return ws


def receber(ws):
    texto = ws.receive(timeout=3)
    assert texto is not None, 'nada recebido em 3s'
    return json.loads(texto)


def fechado_pelo_servidor(ws):
    try:
        return ws.receive(timeout=3) is None
    except simple_websocket.ConnectionClosed:
        return True


emails = []
clientes = []
consultas_service.email_service.enviar_email_async = lambda destino, assunto, corpo: emails.append((destino, assunto, corpo))

servidor = make_server('127.0.0.1', PORTA, app, threaded=True)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
agora = datetime.now().replace(second=0, microsecond=0)
sessoes = []

try:
    sessao = nova_sessao(agora - timedelta(minutes=5), agora + timedelta(minutes=50))
    futura = nova_sessao(agora + timedelta(days=1), agora + timedelta(days=1, hours=1))
    sessoes += [sessao, futura]
    email_profissional = executar('SELECT EMAIL FROM USUARIO WHERE ID_USUARIO = ?', (PROFISSIONAL,))[0]

    # Quem nao participa ou chega fora da janela e desconectado
    assert fechado_pelo_servidor(conectar(OUTRO_PACIENTE, 'PACIENTE', sessao))
    assert fechado_pelo_servidor(conectar(PACIENTE, 'PACIENTE', futura))
    assert emails == [], emails

    # 1. Paciente entra sozinho: sala vazia e o profissional recebe um e-mail
    paciente = conectar(PACIENTE, 'PACIENTE', sessao)
    assert receber(paciente) == {'type': 'peers', 'participantes': []}
    assert len(emails) == 1 and emails[0][0] == email_profissional, emails
    assert f'/videochamada/{sessao}' in emails[0][2], emails[0][2]

    # 2. Reconectar nao repete o e-mail
    paciente.close()
    paciente = conectar(PACIENTE, 'PACIENTE', sessao)
    assert receber(paciente)['participantes'] == []
    assert len(emails) == 1, emails

    # 3. Profissional entra: os dois ficam sabendo, sem e-mail (o paciente ja esta la)
    profissional = conectar(PROFISSIONAL, 'PSICOLOGO', sessao)
    peers = receber(profissional)
    assert peers['type'] == 'peers' and [p['id_usuario'] for p in peers['participantes']] == [PACIENTE], peers
    entrou = receber(paciente)
    assert entrou['type'] == 'peer-joined' and entrou['id_usuario'] == PROFISSIONAL and entrou['nome'], entrou
    assert 'email' not in entrou and 'email' not in peers['participantes'][0], (entrou, peers)
    assert len(emails) == 1, emails

    # 4. Repasse de offer/ICE continua; JSON invalido e tipo desconhecido sao ignorados
    paciente.send('nao e json')
    paciente.send(json.dumps({'type': 'outro'}))
    offer = {'type': 'offer', 'data': {'type': 'offer', 'sdp': 'v=0'}}
    paciente.send(json.dumps(offer))
    assert receber(profissional) == offer
    ice = {'type': 'ice-candidate', 'data': {'candidate': 'x'}}
    profissional.send(json.dumps(ice))
    assert receber(paciente) == ice

    # 5. Quem fica e avisado da saida
    profissional.close()
    saiu = receber(paciente)
    assert saiu['type'] == 'peer-left' and saiu['id_usuario'] == PROFISSIONAL, saiu
    paciente.close()

    print('ok: presenca na sala, aviso por e-mail e repasse do signaling')
finally:
    # Cliente aberto segura o processo: fecha todos para uma falha terminar o teste
    for ws in clientes:
        try:
            ws.close()
        except Exception:
            pass
    for sessao_id in sessoes:
        executar('DELETE FROM SESSAO WHERE SESSAO_ID = ?', (sessao_id,))
    servidor.shutdown()
