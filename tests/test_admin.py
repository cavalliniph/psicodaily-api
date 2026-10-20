# F8/feature 25: so ADMIN acessa /api/admin; metricas do periodo e consulta do log de auditoria.
from datetime import datetime, timedelta

import pytest

from apoio import PACIENTE, PROFISSIONAL, executar


@pytest.mark.parametrize('rota', ['/api/admin/metricas', '/api/admin/auditoria', '/api/usuarios/'])
def test_so_admin_acessa(rota, anonimo, paciente, profissional, admin):
    assert anonimo.get(rota).status_code == 401
    assert paciente.get(rota).status_code == 403
    assert profissional.get(rota).status_code == 403
    assert admin.get(rota).status_code == 200


def test_metricas_do_periodo(admin, sessoes):
    # Uma sessao REALIZADO ontem, paga e avaliada, entra no faturamento, na contagem e na media
    assert admin.get('/api/admin/metricas?dias=15').status_code == 400
    antes = admin.get('/api/admin/metricas?dias=7').get_json()
    assert set(antes['consultas_por_status']) == {'AGENDADO', 'CONFIRMADO', 'REALIZADO', 'CANCELADO'}, antes
    assert set(antes['usuarios_ativos']) == {'PACIENTE', 'PSICOLOGO', 'PSIQUIATRA', 'ADMIN'}, antes
    ontem = (datetime.now() - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    sid = executar('''INSERT INTO SESSAO (PACIENTE_ID, PROFISSIONAL_ID, DATA_HORA_INICIO, DATA_HORA_FIM, STATUS, VALOR_CENTAVOS)
        VALUES (?, ?, ?, ?, 'REALIZADO', 12345) RETURNING SESSAO_ID''', (PACIENTE, PROFISSIONAL, ontem, ontem + timedelta(hours=1)))[0][0]
    sessoes.append(sid)
    executar('INSERT INTO AVALIACAO (SESSAO_ID, PACIENTE_ID, PROFISSIONAL_ID, NOTA) VALUES (?, ?, ?, 5)', (sid, PACIENTE, PROFISSIONAL))
    executar('''INSERT INTO PAGAMENTO (SESSAO_ID, ID_COBRANCA_ARKHE, VALOR_CENTAVOS, STATUS, PAGO_EM)
        VALUES (?, ?, 12345, 'PAGO', ?)''', (sid, 900000000 + sid, ontem))

    r = admin.get('/api/admin/metricas?dias=7')
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'private, no-store'
    depois = r.get_json()
    assert depois['faturamento_centavos'] == antes['faturamento_centavos'] + 12345, depois
    assert depois['consultas_por_status']['REALIZADO'] == antes['consultas_por_status']['REALIZADO'] + 1, depois
    assert depois['avaliacao']['total'] == antes['avaliacao']['total'] + 1 and depois['avaliacao']['media'] is not None, depois


def test_auditoria_filtros_e_paginacao(admin, ultima_auditoria):
    for acao in ('LOGIN', 'LOGIN_FALHA', 'LOGIN'):
        executar('INSERT INTO AUDITORIA (USUARIO_ID, ACAO, ENTIDADE, ENTIDADE_ID, IP) VALUES (?, ?, ?, ?, ?)',
                 (PACIENTE, acao, 'USUARIO', PACIENTE, '203.0.113.9'))
    novas = [linha[0] for linha in executar('SELECT AUDITORIA_ID FROM AUDITORIA WHERE AUDITORIA_ID > ? ORDER BY AUDITORIA_ID DESC',
                                            (ultima_auditoria,))]
    pagina = admin.get(f'/api/admin/auditoria?usuario_id={PACIENTE}&acao=LOGIN&limite=1').get_json()
    assert [i['auditoria_id'] for i in pagina['auditoria']] == [novas[0]], pagina
    assert pagina['auditoria'][0]['ip'] == '203.0.113.9' and pagina['proximo_cursor'] == novas[0], pagina
    pagina = admin.get(f'/api/admin/auditoria?usuario_id={PACIENTE}&acao=LOGIN&limite=1&antes={novas[0]}').get_json()
    assert [i['auditoria_id'] for i in pagina['auditoria']] == [novas[2]], pagina


@pytest.mark.parametrize('query', ['acao=XPTO', 'limite=0', 'usuario_id=abc'])
def test_auditoria_parametro_invalido(admin, query):
    assert admin.get(f'/api/admin/auditoria?{query}').status_code == 400
