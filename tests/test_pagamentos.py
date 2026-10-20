# F2: cobranca ligada a sessao, so os participantes consultam, o Pix pendente e reaproveitado e o pagamento confirma a sessao.
from datetime import datetime, timedelta

import pytest

from apoio import PACIENTE, PROFISSIONAL, executar
from services import notificacoes_service, pagamentos_service

ID_COBRANCA = 987654321


@pytest.fixture
def arkhe(monkeypatch):
    """Arkhé falsa: guarda as chamadas e responde com o status de `estado['status']`."""
    estado = {'status': 0, 'chamadas': []}

    def responder(method, path, body=None):
        estado['chamadas'].append((method, path))
        return 200, {'id_cobranca': ID_COBRANCA, 'valor': 150.0, 'codigo_pagamento': 'ARKHEPIX:TESTE',
                     'status': estado['status'], 'tipo_cobranca': 1}

    monkeypatch.setattr(pagamentos_service, '_arkhe_request', responder)
    monkeypatch.setattr(notificacoes_service.email_service, 'enviar_email_async', lambda *email: None)
    return estado


@pytest.fixture
def sessao(sessoes):
    inicio = (datetime.now() + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
    sid = executar('''INSERT INTO SESSAO (PACIENTE_ID, PROFISSIONAL_ID, DATA_HORA_INICIO, DATA_HORA_FIM, STATUS, VALOR_CENTAVOS)
        VALUES (?, ?, ?, ?, 'AGENDADO', 15000) RETURNING SESSAO_ID''', (PACIENTE, PROFISSIONAL, inicio, inicio + timedelta(hours=1)))[0][0]
    sessoes.append(sid)  # o PAGAMENTO sai junto (cascade)
    return sid


def test_fluxo_do_pix(arkhe, sessao, paciente, outro_paciente, profissional, ultima_notificacao):
    assert paciente.post('/api/pagamentos/cobranca', json={'id_sessao': sessao}).status_code == 201
    assert executar('SELECT VALOR_CENTAVOS, STATUS FROM PAGAMENTO WHERE SESSAO_ID = ?', (sessao,)) == [(15000, 'PENDENTE')]

    # Segunda tentativa reaproveita o Pix pendente em vez de criar outro
    assert paciente.post('/api/pagamentos/cobranca', json={'id_sessao': sessao}).status_code == 201
    assert [m for m, _ in arkhe['chamadas']] == ['POST', 'GET'], arkhe

    # So paciente e profissional da sessao consultam (S8)
    assert outro_paciente.get(f'/api/pagamentos/cobranca/{ID_COBRANCA}').status_code == 404
    assert profissional.get(f'/api/pagamentos/cobranca/{ID_COBRANCA}').status_code == 200

    arkhe['status'] = 1
    assert paciente.get(f'/api/pagamentos/cobranca/{ID_COBRANCA}').get_json()['cobranca']['status'] == 1
    assert executar('SELECT STATUS FROM PAGAMENTO WHERE SESSAO_ID = ?', (sessao,)) == [('PAGO',)]
    assert executar('SELECT STATUS FROM SESSAO WHERE SESSAO_ID = ?', (sessao,)) == [('CONFIRMADO',)]
    avisos = executar('SELECT USUARIO_ID, TIPO FROM NOTIFICACAO WHERE NOTIFICACAO_ID > ?', (ultima_notificacao,))
    assert avisos == [(PROFISSIONAL, 'PAGAMENTO_CONFIRMADO')], avisos

    # Consultar de novo nao notifica outra vez; pagar de novo e recusado
    paciente.get(f'/api/pagamentos/cobranca/{ID_COBRANCA}')
    assert len(executar('SELECT 1 FROM NOTIFICACAO WHERE NOTIFICACAO_ID > ?', (ultima_notificacao,))) == 1
    assert paciente.post('/api/pagamentos/cobranca', json={'id_sessao': sessao}).status_code == 409
