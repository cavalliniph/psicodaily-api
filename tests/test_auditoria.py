# Precisa do Firebird no ar: python tests/test_auditoria.py
# F5/feature 20: cada acao sensivel deixa uma linha em AUDITORIA, com o IP do cliente.
# Usa o profissional 22 e o paciente 23; desfaz tudo o que cria (inclusive senha e e-mail).
import os
import sys
from datetime import date, datetime, time, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
from database.db import get_connection
from services.auth_service import criar_hash_senha, gerar_token

PROFISSIONAL, PACIENTE = 22, 23
IP = {'X-Forwarded-For': '203.0.113.7'}


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


def novas():
    return executar('''SELECT USUARIO_ID, ACAO, ENTIDADE, ENTIDADE_ID, IP FROM AUDITORIA
        WHERE AUDITORIA_ID > ? ORDER BY AUDITORIA_ID''', (ultima,))


def ultima_acao():
    linhas = novas()
    return linhas[-1] if linhas else None


ultima = executar('SELECT COALESCE(MAX(AUDITORIA_ID), 0) FROM AUDITORIA')[0][0]
senha_original, email_original = executar('SELECT SENHA, EMAIL FROM USUARIO WHERE ID_USUARIO = ?', (PACIENTE,))[0]
agenda = executar('SELECT DIA_SEMANA, HORA_INICIO, HORA_FIM FROM DISPONIBILIDADE WHERE PROFISSIONAL_ID = ?', (PROFISSIONAL,))
paciente, profissional, anonimo = cliente(PACIENTE, 'PACIENTE'), cliente(PROFISSIONAL, 'PSICOLOGO'), app.test_client()
sessoes, encaminhamentos = [], []

try:
    executar('UPDATE USUARIO SET SENHA = ? WHERE ID_USUARIO = ?', (criar_hash_senha('Senha@123'), PACIENTE))
    executar('DELETE FROM DISPONIBILIDADE WHERE PROFISSIONAL_ID = ?', (PROFISSIONAL,))

    # Login: falha (usuario existente e inexistente) e sucesso, com o IP do X-Forwarded-For
    anonimo.post('/api/auth/login', json={'email': email_original, 'senha': 'Errada@1'}, headers=IP)
    assert ultima_acao() == (PACIENTE, 'LOGIN_FALHA', 'USUARIO', PACIENTE, '203.0.113.7'), novas()
    anonimo.post('/api/auth/login', json={'email': 'ninguem@exemplo.com', 'senha': 'x'}, headers=IP)
    assert ultima_acao() == (None, 'LOGIN_FALHA', None, None, '203.0.113.7'), novas()
    assert anonimo.post('/api/auth/login', json={'email': email_original, 'senha': 'Senha@123'}).status_code == 200
    assert ultima_acao()[:4] == (PACIENTE, 'LOGIN', 'USUARIO', PACIENTE), novas()

    r = paciente.post('/api/auth/alterar_senha_logado', json={'senha_atual': 'Senha@123', 'nova_senha': 'Nova@1234'})
    assert r.status_code == 200, r.get_json()
    assert ultima_acao()[:4] == (PACIENTE, 'SENHA_ALTERADA', 'USUARIO', PACIENTE), novas()

    # Sessao agendada e alterada
    inicio = datetime.combine(date.today() + timedelta(days=3), time(15))
    corpo = {'id_profissional': PROFISSIONAL, 'timestamp_inicio': inicio.isoformat(),
             'timestamp_fim': (inicio + timedelta(hours=1)).isoformat()}
    r = paciente.post('/api/consultas/', json=corpo)
    assert r.status_code == 201, r.get_json()
    sid = r.get_json()['sessao']['sessao_id']
    sessoes.append(sid)
    assert ultima_acao()[:4] == (PACIENTE, 'SESSAO_AGENDADA', 'SESSAO', sid), novas()
    # Acao que falha nao deixa rastro: a linha sai junto com o rollback
    total = len(novas())
    assert paciente.post('/api/consultas/', json=corpo).status_code == 409
    assert len(novas()) == total, novas()
    r = profissional.patch(f'/api/consultas/{sid}', json={'link_reuniao': 'https://meet.exemplo.com/x'})
    assert r.status_code == 200 and r.get_json()['sessao']['link_reuniao'] == 'https://meet.exemplo.com/x', r.get_json()
    assert ultima_acao()[:4] == (PROFISSIONAL, 'SESSAO_ALTERADA', 'SESSAO', sid), novas()

    assert profissional.get(f'/api/prontuario/{PACIENTE}').status_code == 200
    assert ultima_acao()[:4] == (PROFISSIONAL, 'PRONTUARIO_ACESSO', 'USUARIO', PACIENTE), novas()

    r = profissional.post('/api/encaminhamentos/', json={'id_usuario': PACIENTE, 'motivo': 'Teste de auditoria'})
    assert r.status_code in (200, 201), r.get_json()
    eid = executar('SELECT MAX(ENCAMINHAMENTO_ID) FROM ENCAMINHAMENTO WHERE PACIENTE_ID = ?', (PACIENTE,))[0][0]
    encaminhamentos.append(eid)
    assert ultima_acao()[:4] == (PROFISSIONAL, 'ENCAMINHAMENTO_CRIADO', 'ENCAMINHAMENTO', eid), novas()

    # E-mail: so audita quando muda de fato
    total = len(novas())
    assert paciente.patch('/api/usuarios/me', json={'email': email_original}).status_code == 200
    assert len(novas()) == total, novas()
    assert paciente.patch('/api/usuarios/me', json={'email': 'auditoria.teste@exemplo.com'}).status_code == 200
    assert ultima_acao()[:4] == (PACIENTE, 'EMAIL_ALTERADO', 'USUARIO', PACIENTE), novas()

    print('ok: auditoria')
finally:
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute('UPDATE USUARIO SET SENHA = ?, EMAIL = ? WHERE ID_USUARIO = ?', (senha_original, email_original, PACIENTE))
        for eid in encaminhamentos:
            cur.execute('DELETE FROM ENCAMINHAMENTO WHERE ENCAMINHAMENTO_ID = ?', (eid,))
        for sid in sessoes:
            cur.execute('DELETE FROM SESSAO WHERE SESSAO_ID = ?', (sid,))
        cur.execute('DELETE FROM DISPONIBILIDADE WHERE PROFISSIONAL_ID = ?', (PROFISSIONAL,))
        cur.executemany('INSERT INTO DISPONIBILIDADE (PROFISSIONAL_ID, DIA_SEMANA, HORA_INICIO, HORA_FIM) VALUES (?, ?, ?, ?)',
                        [(PROFISSIONAL, *linha) for linha in agenda])
        cur.execute('DELETE FROM AUDITORIA WHERE AUDITORIA_ID > ?', (ultima,))
        con.commit()
    finally:
        con.close()
