# 24: paciente cancela com reembolso integral ate 15 min antes; profissional cancela a qualquer hora, tambem com
# reembolso; o admin devolve o dinheiro por Pix da Arkhé ou marca como pago por fora.
from datetime import datetime, timedelta

import pytest

from apoio import OUTRO_PACIENTE, PACIENTE, PROFISSIONAL, executar
from services import notificacoes_service, pagamentos_service


@pytest.fixture(autouse=True)
def sem_email(monkeypatch):
    monkeypatch.setattr(notificacoes_service.email_service, 'enviar_email_async', lambda *email: None)


@pytest.fixture
def nova_sessao(sessoes):
    """Cria uma sessao do paciente com o profissional daqui a `minutos`; pago=True grava um pagamento de R$ 150."""
    def criar(minutos=2 * 24 * 60, pago=True):
        inicio = (datetime.now() + timedelta(minutes=minutos)).replace(second=0, microsecond=0)
        sid = executar('''INSERT INTO SESSAO (PACIENTE_ID, PROFISSIONAL_ID, DATA_HORA_INICIO, DATA_HORA_FIM, STATUS,
            VALOR_CENTAVOS) VALUES (?, ?, ?, ?, 'AGENDADO', 15000) RETURNING SESSAO_ID''',
                       (PACIENTE, PROFISSIONAL, inicio, inicio + timedelta(hours=1)))[0][0]
        sessoes.append(sid)  # PAGAMENTO e REEMBOLSO saem junto (cascade)
        if pago:
            executar('''INSERT INTO PAGAMENTO (SESSAO_ID, ID_COBRANCA_ARKHE, METODO, VALOR_CENTAVOS, STATUS, PAGO_EM)
                VALUES (?, ?, 'CARTAO', 15000, 'PAGO', CURRENT_TIMESTAMP)''', (sid, 900000000 + sid))
        return sid, inicio
    return criar


@pytest.fixture
def na_lista_de_espera():
    criadas = []

    def entrar(inicio):
        criadas.append(executar('''INSERT INTO LISTA_ESPERA (PACIENTE_ID, PROFISSIONAL_ID, INICIO_DESEJADO, FIM_DESEJADO)
            VALUES (?, ?, ?, ?) RETURNING LISTA_ESPERA_ID''',
                                (OUTRO_PACIENTE, PROFISSIONAL, inicio - timedelta(hours=1), inicio + timedelta(hours=2)))[0][0])
    yield entrar
    for lista_espera_id in criadas:
        executar('DELETE FROM LISTA_ESPERA WHERE LISTA_ESPERA_ID = ?', (lista_espera_id,))


@pytest.fixture
def arkhe(monkeypatch):
    """Arkhé falsa para Pix de saida e consulta de cobranca: `respostas[path]` = (status, corpo)."""
    estado = {'chamadas': [], 'respostas': {}}

    def responder(method, path, body=None, bruto=False, cabecalhos=None):
        estado['chamadas'].append((method, path, body, cabecalhos))
        return estado['respostas'][path]

    monkeypatch.setattr(pagamentos_service, '_arkhe_request', responder)
    return estado


def _reembolsos(sessao_id):
    return executar('''SELECT r.VALOR_CENTAVOS, r.STATUS FROM REEMBOLSO r JOIN PAGAMENTO p ON p.PAGAMENTO_ID = r.PAGAMENTO_ID
        WHERE p.SESSAO_ID = ?''', (sessao_id,))


def _avisos(desde):
    return executar('SELECT USUARIO_ID, TIPO, MENSAGEM FROM NOTIFICACAO WHERE NOTIFICACAO_ID > ? ORDER BY NOTIFICACAO_ID',
                    (desde,))


def test_paciente_cancela_com_reembolso_integral(paciente, nova_sessao, na_lista_de_espera, ultima_notificacao):
    sid, inicio = nova_sessao()
    na_lista_de_espera(inicio)
    resposta = paciente.post(f'/api/consultas/{sid}/cancelar')
    assert resposta.status_code == 200, resposta.get_json()
    corpo = resposta.get_json()
    assert corpo['sessao']['status'] == 'CANCELADO' and corpo['reembolso_centavos'] == 15000
    assert _reembolsos(sid) == [(15000, 'PENDENTE')]
    assert [(u, t) for u, t, _ in _avisos(ultima_notificacao)] == [
        (OUTRO_PACIENTE, 'VAGA_LISTA_ESPERA'), (PROFISSIONAL, 'SESSAO_CANCELADA')]
    assert executar("SELECT 1 FROM AUDITORIA WHERE ACAO = 'SESSAO_CANCELADA' AND ENTIDADE_ID = ?", (sid,))
    assert paciente.post(f'/api/consultas/{sid}/cancelar').status_code == 409


def test_sem_pagamento_cancela_sem_reembolso(paciente, nova_sessao, ultima_notificacao):
    sid, _ = nova_sessao(pago=False)
    assert paciente.post(f'/api/consultas/{sid}/cancelar').get_json()['reembolso_centavos'] == 0
    assert _reembolsos(sid) == []


def test_so_ate_15_minutos_antes(paciente, nova_sessao, ultima_notificacao):
    perto, _ = nova_sessao(minutos=10)
    resposta = paciente.post(f'/api/consultas/{perto}/cancelar')
    assert resposta.status_code == 409 and '15 minutos' in resposta.get_json()['error']
    assert executar('SELECT STATUS FROM SESSAO WHERE SESSAO_ID = ?', (perto,)) == [('AGENDADO',)]
    folga, _ = nova_sessao(minutos=20)
    assert paciente.post(f'/api/consultas/{folga}/cancelar').status_code == 200


def test_so_o_paciente_da_sessao(anonimo, outro_paciente, profissional, nova_sessao):
    sid, _ = nova_sessao()
    assert anonimo.post(f'/api/consultas/{sid}/cancelar').status_code == 401
    assert profissional.post(f'/api/consultas/{sid}/cancelar').status_code == 403
    assert outro_paciente.post(f'/api/consultas/{sid}/cancelar').status_code == 404


def test_profissional_cancela_reembolsa_e_avisa_o_paciente(profissional, nova_sessao, ultima_notificacao):
    sid, _ = nova_sessao(minutos=5)  # o profissional nao tem o limite de 15 min
    assert profissional.patch(f'/api/consultas/{sid}', json={'status': 'CANCELADO'}).status_code == 200
    assert _reembolsos(sid) == [(15000, 'PENDENTE')]
    [(usuario, tipo, mensagem)] = _avisos(ultima_notificacao)
    assert (usuario, tipo) == (PACIENTE, 'SESSAO_CANCELADA') and 'devolvido integralmente' in mensagem


def test_pix_pago_depois_do_cancelamento_vira_reembolso(paciente, nova_sessao, arkhe, ultima_notificacao):
    sid, _ = nova_sessao(pago=False)
    executar('''INSERT INTO PAGAMENTO (SESSAO_ID, ID_COBRANCA_ARKHE, METODO, VALOR_CENTAVOS)
        VALUES (?, ?, 'PIX', 15000)''', (sid, 900000000 + sid))
    paciente.post(f'/api/consultas/{sid}/cancelar')
    arkhe['respostas'][f'/api/v1/cobrancas/pix/{900000000 + sid}'] = (200, {'id_cobranca': 900000000 + sid, 'status': 1})
    assert paciente.get(f'/api/pagamentos/cobranca/{900000000 + sid}').status_code == 200
    assert _reembolsos(sid) == [(15000, 'PENDENTE')]
    assert executar('SELECT STATUS FROM SESSAO WHERE SESSAO_ID = ?', (sid,)) == [('CANCELADO',)]
    assert all(tipo != 'PAGAMENTO_CONFIRMADO' for _, tipo, _ in _avisos(ultima_notificacao))


def test_admin_paga_reembolso_pela_arkhe(admin, paciente, nova_sessao, arkhe, ultima_notificacao):
    sid, _ = nova_sessao()
    paciente.post(f'/api/consultas/{sid}/cancelar')
    [reembolso] = [r for r in admin.get('/api/admin/reembolsos?status=PENDENTE').get_json()['reembolsos']
                   if r['sessao_id'] == sid]
    rid = reembolso['reembolso_id']
    cpf = executar('SELECT CPF FROM USUARIO WHERE ID_USUARIO = ?', (PACIENTE,))[0][0]
    assert reembolso['paciente']['cpf'] == cpf and reembolso['valor_centavos'] == 15000

    # Integracao nao liberada pelo outro grupo: mostra o motivo e continua pendente
    arkhe['respostas']['/api/v1/pagamentos/pix'] = (403, {'mensagem': 'Esta integracao nao esta habilitada para pagamentos de saida'})
    falha = admin.post(f'/api/admin/reembolsos/{rid}/pagar', json={})
    assert falha.status_code == 502 and 'nao esta habilitada' in falha.get_json()['error']
    assert _reembolsos(sid) == [(15000, 'PENDENTE')]

    arkhe['respostas']['/api/v1/pagamentos/pix'] = (201, {'id_movimentacao': 555, 'valor': 150.0})
    pago = admin.post(f'/api/admin/reembolsos/{rid}/pagar', json={})
    assert pago.status_code == 200 and pago.get_json()['reembolso']['id_movimentacao_arkhe'] == 555
    assert arkhe['chamadas'][-1] == ('POST', '/api/v1/pagamentos/pix',
                                     {'tipo_chave': 'cpf', 'chave_pix': cpf, 'valor': 150.0},
                                     {'X-Idempotency-Key': f'psicodaily-reembolso-{rid}'})
    assert _reembolsos(sid) == [(15000, 'PAGO')]
    assert (PACIENTE, 'REEMBOLSO_PAGO') in [(u, t) for u, t, _ in _avisos(ultima_notificacao)]
    assert executar("SELECT 1 FROM AUDITORIA WHERE ACAO = 'REEMBOLSO_PAGO' AND ENTIDADE_ID = ?", (rid,))
    assert admin.post(f'/api/admin/reembolsos/{rid}/pagar', json={'manual': True}).status_code == 409


def test_admin_marca_reembolso_pago_por_fora(admin, paciente, nova_sessao, arkhe):
    sid, _ = nova_sessao()
    paciente.post(f'/api/consultas/{sid}/cancelar')
    rid = executar('''SELECT r.REEMBOLSO_ID FROM REEMBOLSO r JOIN PAGAMENTO p ON p.PAGAMENTO_ID = r.PAGAMENTO_ID
        WHERE p.SESSAO_ID = ?''', (sid,))[0][0]
    assert admin.post(f'/api/admin/reembolsos/{rid}/pagar', json={'manual': 'sim'}).status_code == 400
    assert admin.post(f'/api/admin/reembolsos/{rid}/pagar', json={'manual': True}).status_code == 200
    assert arkhe['chamadas'] == []
    assert _reembolsos(sid) == [(15000, 'PAGO')]


def test_reembolsos_so_para_admin(admin, paciente):
    assert paciente.get('/api/admin/reembolsos').status_code == 403
    assert paciente.post('/api/admin/reembolsos/1/pagar', json={}).status_code == 403
    assert admin.get('/api/admin/reembolsos?status=XPTO').status_code == 400
    assert admin.post('/api/admin/reembolsos/999999/pagar', json={'manual': True}).status_code == 404
