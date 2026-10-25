# 9: assinatura do profissional 22. Cada mes e uma cobranca avulsa na Arkhé; o job confirma as pagas e gera o Pix
# da renovacao; sem plano valido o profissional some da busca; video, lista de espera e conteudos sao travados por plano.
from datetime import date, datetime, time, timedelta

import pytest

from apoio import PROFISSIONAL, executar
from services import assinaturas_service, notificacoes_service, pagamentos_service

HOJE = date.today()
CARTAO = {'numero_cartao': '4111111111111111', 'validade': '12/2030', 'cvv': '123', 'tipo': 'CREDITO'}
VIDEO = 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'


@pytest.fixture(autouse=True)
def sem_email(monkeypatch):
    monkeypatch.setattr(notificacoes_service.email_service, 'enviar_email_async', lambda *email: None)


@pytest.fixture
def assinatura():
    """Troca a assinatura do 22 no teste (`dias` ate o vencimento) e restaura no fim; as cobrancas criadas saem."""
    colunas = 'PLANO, VALIDA_ATE, RENOVAR, PLANO_PROXIMO'
    original = executar(f'SELECT {colunas} FROM ASSINATURA WHERE PROFISSIONAL_ID = ?', (PROFISSIONAL,))[0]
    ultima = executar('SELECT COALESCE(MAX(COBRANCA_ID), 0) FROM COBRANCA_ASSINATURA')[0][0]

    def definir(plano, dias=10, renovar=True, proximo=None):
        executar(f"UPDATE ASSINATURA SET {colunas.replace(',', ' = ?,')} = ? WHERE PROFISSIONAL_ID = ?",
                 (plano, HOJE + timedelta(days=dias), renovar, proximo, PROFISSIONAL))

    yield definir
    executar('DELETE FROM COBRANCA_ASSINATURA WHERE COBRANCA_ID > ?', (ultima,))
    executar(f"UPDATE ASSINATURA SET {colunas.replace(',', ' = ?,')} = ? WHERE PROFISSIONAL_ID = ?", (*original, PROFISSIONAL))


@pytest.fixture
def arkhe(monkeypatch):
    """Arkhé falsa: cada cobranca ou venda ganha um id novo; `status[id]` = 1 marca a cobranca como paga."""
    estado = {'status': {}, 'chamadas': [], 'ultimo_id': 880000000}

    def responder(method, path, body=None, bruto=False, cabecalhos=None):
        estado['chamadas'].append((method, path, body))
        if path.endswith('/pdf'):
            return 200, b'%PDF-teste'
        if method == 'GET':
            id_cobranca = int(path.rsplit('/', 1)[1])
            return 200, {'id_cobranca': id_cobranca, 'status': estado['status'].get(id_cobranca, 0)}
        estado['ultimo_id'] += 1
        if path == '/api/v1/vendas/cartao':
            return 201, {'aprovado': True, 'id_compra': estado['ultimo_id'], 'valor': body['valor']}
        return 201, {'id_cobranca': estado['ultimo_id'], 'valor': body['valor'], 'status': 0,
                     'codigo_pagamento': f'ARKHEPIX:{estado["ultimo_id"]}'}

    monkeypatch.setattr(pagamentos_service, '_arkhe_request', responder)
    return estado


@pytest.fixture
def video():
    original = executar('SELECT VIDEO_URL FROM PROFISSIONAL WHERE USUARIO_ID = ?', (PROFISSIONAL,))[0][0]
    executar('UPDATE PROFISSIONAL SET VIDEO_URL = ? WHERE USUARIO_ID = ?', (VIDEO, PROFISSIONAL))
    yield
    executar('UPDATE PROFISSIONAL SET VIDEO_URL = ? WHERE USUARIO_ID = ?', (original, PROFISSIONAL))


def estado():
    return executar('SELECT PLANO, VALIDA_ATE, RENOVAR, PLANO_PROXIMO FROM ASSINATURA WHERE PROFISSIONAL_ID = ?',
                    (PROFISSIONAL,))[0]


def cobrancas():
    return executar('''SELECT PLANO, METODO, VALOR_CENTAVOS, STATUS FROM COBRANCA_ASSINATURA
        WHERE PROFISSIONAL_ID = ? ORDER BY COBRANCA_ID''', (PROFISSIONAL,))


def avisos(ultima_notificacao):
    return [tipo for tipo, in executar('SELECT TIPO FROM NOTIFICACAO WHERE NOTIFICACAO_ID > ? AND USUARIO_ID = ?',
                                      (ultima_notificacao, PROFISSIONAL))]


def test_planos_e_permissoes(anonimo, paciente):
    planos = anonimo.get('/api/assinaturas/planos').get_json()['planos']
    assert [(p['plano'], p['preco_centavos']) for p in planos] == [
        ('ESSENCIAL', 5000), ('PROFISSIONAL', 10000), ('PREMIUM', 15000)], planos
    assert anonimo.get('/api/assinaturas/me').status_code == 401
    assert paciente.get('/api/assinaturas/me').status_code == 403


def test_pix_ativa_o_plano_quando_pago(profissional, assinatura, arkhe, ultima_notificacao):
    assinatura('ESSENCIAL', dias=-1)  # vencida
    r = profissional.post('/api/assinaturas/me', json={'plano': 'PROFISSIONAL'})
    assert r.status_code == 201, r.get_json()
    corpo = r.get_json()
    assert corpo['cobranca']['metodo'] == 'PIX' and corpo['assinatura']['ativa'] is False, corpo
    assert arkhe['chamadas'][-1] == ('POST', '/api/v1/cobrancas/pix', {'valor': 100.0})

    # Pedir de novo reaproveita o Pix aberto em vez de criar outro
    de_novo = profissional.post('/api/assinaturas/me', json={'plano': 'PROFISSIONAL'}).get_json()
    assert de_novo['cobranca']['cobranca_id'] == corpo['cobranca']['cobranca_id']
    assert cobrancas() == [('PROFISSIONAL', 'PIX', 10000, 'PENDENTE')]

    arkhe['status'][corpo['cobranca']['id_cobranca']] = 1
    me = profissional.get('/api/assinaturas/me').get_json()['assinatura']
    assert (me['plano'], me['ativa'], me['valida_ate'], me['cobrancas_pendentes'], me['periodo_gratis']) == (
        'PROFISSIONAL', True, (HOJE + timedelta(days=30)).isoformat(), [], False), me
    assert avisos(ultima_notificacao) == ['ASSINATURA_ATIVA']


def test_cartao_aprova_na_hora_e_upgrade_reinicia_o_ciclo(profissional, admin, assinatura, arkhe, ultima_notificacao):
    assinatura('ESSENCIAL', dias=20)
    antes = admin.get('/api/admin/metricas?dias=7').get_json()['assinaturas']
    r = profissional.post('/api/assinaturas/me', json={'plano': 'PREMIUM', 'metodo': 'CARTAO', 'cartao': CARTAO})
    assert r.status_code == 201, r.get_json()
    assert arkhe['chamadas'][-1] == ('POST', '/api/v1/vendas/cartao', {**CARTAO, 'parcelas': 1, 'valor': 150.0})
    # Sem proporcional: os 20 dias do Essencial nao viram credito
    assert estado() == ('PREMIUM', HOJE + timedelta(days=30), True, None)
    assert cobrancas() == [('PREMIUM', 'CARTAO', 15000, 'PAGO')]
    # A receita da assinatura entra nas metricas do admin, fora do faturamento das consultas
    depois = admin.get('/api/admin/metricas?dias=7').get_json()['assinaturas']
    assert depois['receita_centavos'] == antes['receita_centavos'] + 15000, depois
    assert depois['ativas_por_plano']['PREMIUM'] == antes['ativas_por_plano']['PREMIUM'] + 1, depois


def test_renovar_o_mesmo_plano_continua_do_fim_do_ciclo(profissional, assinatura, arkhe, ultima_notificacao):
    assinatura('PROFISSIONAL', dias=5)
    profissional.post('/api/assinaturas/me', json={'plano': 'PROFISSIONAL', 'metodo': 'CARTAO', 'cartao': CARTAO})
    assert estado() == ('PROFISSIONAL', HOJE + timedelta(days=35), True, None)


def test_downgrade_fica_para_a_renovacao_e_cancelar_desliga(profissional, assinatura, arkhe):
    assinatura('PREMIUM', dias=10)
    r = profissional.post('/api/assinaturas/me', json={'plano': 'ESSENCIAL'})
    assert r.status_code == 200 and r.get_json()['cobranca'] is None, r.get_json()
    assert estado() == ('PREMIUM', HOJE + timedelta(days=10), True, 'ESSENCIAL')
    assert not any(method == 'POST' for method, _, _ in arkhe['chamadas'])

    cancelada = profissional.post('/api/assinaturas/me/cancelar').get_json()['assinatura']
    assert (cancelada['renovar'], cancelada['plano_proximo'], cancelada['ativa']) == (False, None, True), cancelada
    assinatura('PREMIUM', dias=-1)
    assert profissional.post('/api/assinaturas/me/cancelar').status_code == 404


@pytest.mark.parametrize('corpo', [
    {}, {'plano': 'OURO'}, {'plano': 'PREMIUM', 'metodo': 'DINHEIRO'}, {'plano': 'PREMIUM', 'metodo': 'CARTAO'},
    {'plano': 'PREMIUM', 'extra': 1},
])
def test_pedido_invalido_nao_chama_a_arkhe(profissional, assinatura, arkhe, corpo):
    assert profissional.post('/api/assinaturas/me', json=corpo).status_code == 400
    assert arkhe['chamadas'] == []


def test_boleto_tem_pdf_so_para_o_dono(profissional, psiquiatra, assinatura, arkhe):
    assinatura('ESSENCIAL', dias=-1)
    cobranca = profissional.post('/api/assinaturas/me', json={'plano': 'ESSENCIAL', 'metodo': 'BOLETO'}).get_json()['cobranca']
    pedido = arkhe['chamadas'][-1][2]
    assert pedido['documento_pagador'] and pedido['data_vencimento'] == (HOJE + timedelta(days=3)).isoformat(), pedido
    pdf = profissional.get(f'/api/assinaturas/me/cobranca/{cobranca["cobranca_id"]}/pdf')
    assert pdf.status_code == 200 and pdf.data == b'%PDF-teste'
    assert psiquiatra.get(f'/api/assinaturas/me/cobranca/{cobranca["cobranca_id"]}/pdf').status_code == 404


def test_job_gera_o_pix_da_renovacao_uma_vez_e_confirma_o_pago(assinatura, arkhe, ultima_notificacao):
    # Vence em 2 dias com downgrade agendado: a renovacao ja sai no plano novo
    assinatura('PREMIUM', dias=2, proximo='ESSENCIAL')
    assinaturas_service.processar()
    assert cobrancas() == [('ESSENCIAL', 'PIX', 5000, 'PENDENTE')]
    assert avisos(ultima_notificacao) == ['ASSINATURA_RENOVACAO']
    aviso = executar('SELECT MENSAGEM FROM NOTIFICACAO WHERE NOTIFICACAO_ID > ? AND USUARIO_ID = ?',
                     (ultima_notificacao, PROFISSIONAL))[0][0]
    assert f'ARKHEPIX:{arkhe["ultimo_id"]}' in aviso, aviso

    assinaturas_service.processar()
    assert len(cobrancas()) == 1, 'o job gerou o Pix da renovacao duas vezes'

    arkhe['status'][arkhe['ultimo_id']] = 1
    assinaturas_service.processar()
    assert estado() == ('ESSENCIAL', HOJE + timedelta(days=32), True, None)
    assert cobrancas() == [('ESSENCIAL', 'PIX', 5000, 'PAGO')]


def test_job_nao_renova_quem_cancelou_nem_quem_vence_depois(assinatura, arkhe):
    assinatura('PREMIUM', dias=2, renovar=False)
    assinaturas_service.processar()
    assinatura('PREMIUM', dias=4)
    assinaturas_service.processar()
    assert cobrancas() == []


def test_sem_plano_some_da_busca_e_nao_recebe_agendamento(anonimo, paciente, assinatura):
    assinatura('ESSENCIAL', dias=-1)
    assert anonimo.get(f'/api/profissionais/{PROFISSIONAL}').status_code == 404
    busca = anonimo.get('/api/profissionais/?page_size=100').get_json()['profissionais']
    assert PROFISSIONAL not in [p['id_usuario'] for p in busca]
    recomendados = paciente.get('/api/profissionais/recomendados').get_json()['profissionais']
    assert PROFISSIONAL not in [p['id_usuario'] for p in recomendados]
    inicio = datetime.combine(HOJE + timedelta(days=3), time(10))
    r = paciente.post('/api/consultas/', json={'id_profissional': PROFISSIONAL, 'timestamp_inicio': inicio.isoformat(),
                                               'timestamp_fim': (inicio + timedelta(hours=1)).isoformat()})
    assert r.status_code == 409, r.get_json()

    # Vence hoje: ainda vale o dia todo
    assinatura('ESSENCIAL', dias=0)
    assert anonimo.get(f'/api/profissionais/{PROFISSIONAL}').status_code == 200


def test_travas_e_beneficios_por_plano(anonimo, paciente, profissional, assinatura, video):
    assinatura('ESSENCIAL')
    perfil = anonimo.get(f'/api/profissionais/{PROFISSIONAL}').get_json()['profissionais']
    assert (perfil['video_url'], perfil['patrocinado'], 'plano' in perfil) == (None, False, False), perfil
    inicio = datetime.combine(HOJE + timedelta(days=3), time(10))
    espera = paciente.post('/api/lista-espera/', json={'id_profissional': PROFISSIONAL, 'inicio': inicio.isoformat(),
                                                      'fim': (inicio + timedelta(hours=2)).isoformat()})
    assert espera.status_code == 409, espera.get_json()
    conteudo = profissional.post('/api/conteudos/', json={'titulo': 'Ansiedade', 'corpo': 'Texto'})
    assert conteudo.status_code == 403 and conteudo.get_json()['plano_necessario'] == 'PREMIUM', conteudo.get_json()
    assert anonimo.get(f'/api/profissionais/{PROFISSIONAL}/conteudos').get_json()['conteudos'] == []
    assert profissional.get('/api/profissionais/me/desempenho').status_code == 403

    assinatura('PROFISSIONAL')
    assert anonimo.get(f'/api/profissionais/{PROFISSIONAL}').get_json()['profissionais']['video_url'] == VIDEO
    relatorio = profissional.get('/api/profissionais/me/desempenho?dias=7').get_json()
    assert {'visualizacoes', 'visualizacoes_por_dia', 'consultas', 'agendamentos_feitos', 'novos_favoritos'} <= set(relatorio)
    assert 'conversao' not in relatorio and 'periodo_anterior' not in relatorio, relatorio

    assinatura('PREMIUM')
    assert anonimo.get(f'/api/profissionais/{PROFISSIONAL}').get_json()['profissionais']['patrocinado'] is True
    relatorio = profissional.get('/api/profissionais/me/desempenho?dias=7').get_json()
    assert 'conversao' in relatorio and 'consultas' in relatorio['periodo_anterior'], relatorio
    assert profissional.get('/api/profissionais/me/desempenho?dias=15').status_code == 400


def test_desempenho_conta_as_visitas_ao_perfil(anonimo, profissional, assinatura):
    assinatura('PROFISSIONAL')
    antes = profissional.get('/api/profissionais/me/desempenho?dias=7').get_json()['visualizacoes']
    anonimo.get(f'/api/profissionais/{PROFISSIONAL}')
    anonimo.get(f'/api/profissionais/{PROFISSIONAL}')
    assert profissional.get('/api/profissionais/me/desempenho?dias=7').get_json()['visualizacoes'] == antes + 2
