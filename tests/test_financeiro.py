# 32: financeiro do profissional (10% da plataforma + taxa do cartao da Arkhé) e repasses fechados e pagos pelo admin.
from datetime import datetime, timedelta

import pytest

from apoio import PACIENTE, PROFISSIONAL, executar
from services import notificacoes_service, pagamentos_service


@pytest.fixture(autouse=True)
def sem_email(monkeypatch):
    monkeypatch.setattr(notificacoes_service.email_service, 'enviar_email_async', lambda *email: None)


@pytest.fixture
def consulta(sessoes):
    """Sessao de R$ 150 do paciente com o profissional, ja paga; `taxa` e a da Arkhé em centavos."""
    def criar(status='REALIZADO', metodo='PIX', taxa=None, dias=-1):
        inicio = (datetime.now() + timedelta(days=dias)).replace(second=0, microsecond=0)
        sid = executar('''INSERT INTO SESSAO (PACIENTE_ID, PROFISSIONAL_ID, DATA_HORA_INICIO, DATA_HORA_FIM, STATUS,
            VALOR_CENTAVOS) VALUES (?, ?, ?, ?, ?, 15000) RETURNING SESSAO_ID''',
                       (PACIENTE, PROFISSIONAL, inicio, inicio + timedelta(hours=1), status))[0][0]
        sessoes.append(sid)  # PAGAMENTO e REEMBOLSO saem junto (cascade)
        executar('''INSERT INTO PAGAMENTO (SESSAO_ID, ID_COBRANCA_ARKHE, METODO, VALOR_CENTAVOS, STATUS, PAGO_EM,
            TAXA_ARKHE_CENTAVOS) VALUES (?, ?, ?, 15000, 'PAGO', CURRENT_TIMESTAMP, ?)''', (sid, 900000000 + sid, metodo, taxa))
        return sid
    return criar


def reembolsar(sessao_id):
    executar('''INSERT INTO REEMBOLSO (PAGAMENTO_ID, VALOR_CENTAVOS)
        SELECT PAGAMENTO_ID, VALOR_CENTAVOS FROM PAGAMENTO WHERE SESSAO_ID = ?''', (sessao_id,))


@pytest.fixture
def repasses():
    """Apaga os repasses criados pelo teste (o PAGAMENTO fica com REPASSE_ID nulo)."""
    ultimo = executar('SELECT COALESCE(MAX(REPASSE_ID), 0) FROM REPASSE')[0][0]
    yield
    executar('DELETE FROM REPASSE WHERE REPASSE_ID > ?', (ultimo,))


@pytest.fixture
def arkhe(monkeypatch):
    estado = {'chamadas': [], 'resposta': (201, {'id_movimentacao': 777, 'valor': 127.5})}

    def responder(method, path, body=None, bruto=False, cabecalhos=None):
        estado['chamadas'].append((method, path, body, cabecalhos))
        return estado['resposta']

    monkeypatch.setattr(pagamentos_service, '_arkhe_request', responder)
    return estado


def test_ganhos_separa_taxas_e_situacoes(profissional, paciente, consulta):
    credito = consulta(metodo='CARTAO', taxa=750)
    futura = consulta(status='AGENDADO', dias=2)
    reembolsada = consulta()
    reembolsar(reembolsada)

    corpo = profissional.get('/api/pagamentos/ganhos?dias=30').get_json()
    por_sessao = {c['sessao_id']: c for c in corpo['consultas']}
    assert {chave: por_sessao[credito][chave] for chave in ('taxa_plataforma_centavos', 'taxa_cartao_centavos',
                                                             'liquido_centavos', 'situacao')} == {
        'taxa_plataforma_centavos': 1500, 'taxa_cartao_centavos': 750, 'liquido_centavos': 12750, 'situacao': 'A_RECEBER'}
    assert (por_sessao[futura]['liquido_centavos'], por_sessao[futura]['situacao']) == (13500, 'AGUARDANDO_CONSULTA')
    assert por_sessao[reembolsada]['situacao'] == 'REEMBOLSADO'
    # O reembolsado aparece na lista, mas nao soma
    assert corpo['resumo'] == {'consultas_realizadas': 2, 'recebido_centavos': 30000, 'taxa_plataforma_centavos': 3000,
                               'taxa_cartao_centavos': 750, 'liquido_centavos': 26250}
    assert corpo['saldo'] == {'aguardando_consulta_centavos': 13500, 'a_receber_centavos': 12750, 'em_repasse_centavos': 0}

    assert paciente.get('/api/pagamentos/ganhos').status_code == 403
    assert profissional.get('/api/pagamentos/ganhos?dias=2').status_code == 400


def test_admin_fecha_e_paga_repasse(admin, profissional, consulta, repasses, arkhe, ultima_notificacao):
    credito = consulta(metodo='CARTAO', taxa=750)
    futura = consulta(status='AGENDADO', dias=2)
    reembolsada = consulta()
    reembolsar(reembolsada)

    resposta = admin.post('/api/admin/repasses')
    assert resposta.status_code == 201, resposta.get_json()
    [repasse] = [r for r in resposta.get_json()['repasses'] if r['profissional_id'] == PROFISSIONAL]
    assert (repasse['valor_centavos'], repasse['consultas']) == (12750, 1)
    vinculados = executar('SELECT SESSAO_ID FROM PAGAMENTO WHERE REPASSE_ID = ?', (repasse['repasse_id'],))
    assert vinculados == [(credito,)], (vinculados, futura, reembolsada)
    assert admin.post('/api/admin/repasses').status_code == 409

    ganhos = profissional.get('/api/pagamentos/ganhos').get_json()
    assert ganhos['saldo']['em_repasse_centavos'] == 12750
    [listado] = [r for r in admin.get('/api/admin/repasses?status=PENDENTE').get_json()['repasses']
                 if r['repasse_id'] == repasse['repasse_id']]
    cpf = executar('SELECT CPF FROM USUARIO WHERE ID_USUARIO = ?', (PROFISSIONAL,))[0][0]
    assert listado['profissional']['cpf'] == cpf and listado['consultas'] == 1

    pago = admin.post(f"/api/admin/repasses/{repasse['repasse_id']}/pagar", json={})
    assert pago.status_code == 200 and pago.get_json()['repasse']['id_movimentacao_arkhe'] == 777
    assert arkhe['chamadas'] == [('POST', '/api/v1/pagamentos/pix', {'tipo_chave': 'cpf', 'chave_pix': cpf, 'valor': 127.5},
                                  {'X-Idempotency-Key': f"psicodaily-repasse-{repasse['repasse_id']}"})]
    situacoes = {c['sessao_id']: c['situacao'] for c in profissional.get('/api/pagamentos/ganhos').get_json()['consultas']}
    assert situacoes[credito] == 'REPASSADO'
    avisos = executar('SELECT USUARIO_ID, TIPO FROM NOTIFICACAO WHERE NOTIFICACAO_ID > ?', (ultima_notificacao,))
    assert (PROFISSIONAL, 'REPASSE_PAGO') in avisos
    acoes = {a for (a,) in executar('''SELECT ACAO FROM AUDITORIA WHERE ENTIDADE = 'REPASSE' AND ENTIDADE_ID = ?''',
                                    (repasse['repasse_id'],))}
    assert acoes == {'REPASSE_CRIADO', 'REPASSE_PAGO'}
    assert admin.post(f"/api/admin/repasses/{repasse['repasse_id']}/pagar", json={'manual': True}).status_code == 409


def test_repasses_so_para_admin(admin, profissional):
    assert profissional.get('/api/admin/repasses').status_code == 403
    assert profissional.post('/api/admin/repasses').status_code == 403
    assert admin.get('/api/admin/repasses?status=XPTO').status_code == 400
    assert admin.post('/api/admin/repasses/999999/pagar', json={'manual': True}).status_code == 404


def test_reembolsado_sai_do_faturamento_e_dos_ganhos_do_mes(admin, profissional, consulta):
    sid = consulta(dias=-0.01)  # pago agora, para cair no mes corrente
    faturamento = admin.get('/api/admin/metricas?dias=7').get_json()['faturamento_centavos']
    ganhos_mes = profissional.get('/api/dashboard/').get_json()['ganhos_mes_centavos']
    reembolsar(sid)
    assert admin.get('/api/admin/metricas?dias=7').get_json()['faturamento_centavos'] == faturamento - 15000
    assert profissional.get('/api/dashboard/').get_json()['ganhos_mes_centavos'] == ganhos_mes - 15000
