# Precisa do Firebird no ar: python tests/test_admin.py
# F8/feature 25: so ADMIN acessa /api/admin; metricas do periodo e consulta do log de auditoria.
# Usa o profissional 22 e o paciente 23; desfaz tudo o que cria.
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
from database.db import get_connection
from services.auth_service import gerar_token

PROFISSIONAL, PACIENTE, ADMIN = 22, 23, 26


def executar(sql, params=()):
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute(sql, params)
        linhas = cur.fetchall() if cur.description else None
        con.commit()
        return linhas
    finally:
        con.close()


def cliente(id_usuario, papel):
    c = app.test_client()
    with app.app_context():
        c.set_cookie('access_token', gerar_token({'id_usuario': id_usuario, 'usuario_role': papel}))
    return c


admin, paciente, profissional = cliente(ADMIN, 'ADMIN'), cliente(PACIENTE, 'PACIENTE'), cliente(PROFISSIONAL, 'PSICOLOGO')
ultima = executar('SELECT COALESCE(MAX(AUDITORIA_ID), 0) FROM AUDITORIA')[0][0]
sessoes = []

try:
    # Acesso: so ADMIN, inclusive na listagem de usuarios que ja existia
    for rota in ('/api/admin/metricas', '/api/admin/auditoria', '/api/usuarios/'):
        assert app.test_client().get(rota).status_code == 401, rota
        assert paciente.get(rota).status_code == 403, rota
        assert profissional.get(rota).status_code == 403, rota
    assert admin.get('/api/usuarios/').status_code == 200

    # Metricas: uma sessao REALIZADO ontem com avaliacao entra no faturamento, na contagem e na media
    assert admin.get('/api/admin/metricas?dias=15').status_code == 400
    antes = admin.get('/api/admin/metricas?dias=7').get_json()
    assert set(antes['consultas_por_status']) == {'AGENDADO', 'CONFIRMADO', 'REALIZADO', 'CANCELADO'}, antes
    assert set(antes['usuarios_ativos']) == {'PACIENTE', 'PSICOLOGO', 'PSIQUIATRA', 'ADMIN'}, antes
    ontem = (datetime.now() - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    sid = executar('''INSERT INTO SESSAO (PACIENTE_ID, PROFISSIONAL_ID, DATA_HORA_INICIO, DATA_HORA_FIM, STATUS, VALOR_CENTAVOS)
        VALUES (?, ?, ?, ?, 'REALIZADO', 12345) RETURNING SESSAO_ID''', (PACIENTE, PROFISSIONAL, ontem, ontem + timedelta(hours=1)))[0][0]
    sessoes.append(sid)
    executar('INSERT INTO AVALIACAO (SESSAO_ID, PACIENTE_ID, PROFISSIONAL_ID, NOTA) VALUES (?, ?, ?, 5)', (sid, PACIENTE, PROFISSIONAL))
    r = admin.get('/api/admin/metricas?dias=7')
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'private, no-store'
    depois = r.get_json()
    assert depois['faturamento_centavos'] == antes['faturamento_centavos'] + 12345, depois
    assert depois['consultas_por_status']['REALIZADO'] == antes['consultas_por_status']['REALIZADO'] + 1, depois
    assert depois['avaliacao']['total'] == antes['avaliacao']['total'] + 1 and depois['avaliacao']['media'] is not None, depois

    # Auditoria: filtros por usuario e acao, paginacao por cursor, acao invalida
    for acao in ('LOGIN', 'LOGIN_FALHA', 'LOGIN'):
        executar('INSERT INTO AUDITORIA (USUARIO_ID, ACAO, ENTIDADE, ENTIDADE_ID, IP) VALUES (?, ?, ?, ?, ?)',
                 (PACIENTE, acao, 'USUARIO', PACIENTE, '203.0.113.9'))
    novas = [linha[0] for linha in executar('SELECT AUDITORIA_ID FROM AUDITORIA WHERE AUDITORIA_ID > ? ORDER BY AUDITORIA_ID DESC', (ultima,))]
    pagina = admin.get(f'/api/admin/auditoria?usuario_id={PACIENTE}&acao=LOGIN&limite=1').get_json()
    assert [i['auditoria_id'] for i in pagina['auditoria']] == [novas[0]], pagina
    assert pagina['auditoria'][0]['ip'] == '203.0.113.9' and pagina['proximo_cursor'] == novas[0], pagina
    pagina = admin.get(f'/api/admin/auditoria?usuario_id={PACIENTE}&acao=LOGIN&limite=1&antes={novas[0]}').get_json()
    assert [i['auditoria_id'] for i in pagina['auditoria']] == [novas[2]], pagina
    assert admin.get('/api/admin/auditoria?acao=XPTO').status_code == 400
    assert admin.get('/api/admin/auditoria?limite=0').status_code == 400
    assert admin.get('/api/admin/auditoria?usuario_id=abc').status_code == 400

    print('ok: admin')
finally:
    for sid in sessoes:
        executar('DELETE FROM SESSAO WHERE SESSAO_ID = ?', (sid,))
    executar('DELETE FROM AUDITORIA WHERE AUDITORIA_ID > ?', (ultima,))
