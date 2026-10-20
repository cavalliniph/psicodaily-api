# F5/feature 20: cada acao sensivel deixa uma linha em AUDITORIA, com o IP do cliente.
from datetime import date, datetime, time, timedelta

import pytest

from apoio import PACIENTE, PROFISSIONAL, executar
from services.auth_service import criar_hash_senha

IP = {'X-Forwarded-For': '203.0.113.7'}


@pytest.fixture
def novas(ultima_auditoria):
    """Linhas de AUDITORIA criadas pelo teste, em ordem."""
    return lambda: executar('''SELECT USUARIO_ID, ACAO, ENTIDADE, ENTIDADE_ID, IP FROM AUDITORIA
        WHERE AUDITORIA_ID > ? ORDER BY AUDITORIA_ID''', (ultima_auditoria,))


@pytest.fixture
def conta_do_paciente():
    """Senha do paciente conhecida (Senha@123) no teste; senha e e-mail originais voltam no fim."""
    senha, email = executar('SELECT SENHA, EMAIL FROM USUARIO WHERE ID_USUARIO = ?', (PACIENTE,))[0]
    executar('UPDATE USUARIO SET SENHA = ? WHERE ID_USUARIO = ?', (criar_hash_senha('Senha@123'), PACIENTE))
    yield email
    executar('UPDATE USUARIO SET SENHA = ?, EMAIL = ? WHERE ID_USUARIO = ?', (senha, email, PACIENTE))


def test_login_falha_e_sucesso_com_ip(anonimo, conta_do_paciente, novas):
    anonimo.post('/api/auth/login', json={'email': conta_do_paciente, 'senha': 'Errada@1'}, headers=IP)
    assert novas()[-1] == (PACIENTE, 'LOGIN_FALHA', 'USUARIO', PACIENTE, '203.0.113.7'), novas()
    anonimo.post('/api/auth/login', json={'email': 'ninguem@exemplo.com', 'senha': 'x'}, headers=IP)
    assert novas()[-1] == (None, 'LOGIN_FALHA', None, None, '203.0.113.7'), novas()
    assert anonimo.post('/api/auth/login', json={'email': conta_do_paciente, 'senha': 'Senha@123'}).status_code == 200
    assert novas()[-1][:4] == (PACIENTE, 'LOGIN', 'USUARIO', PACIENTE), novas()


def test_senha_alterada(paciente, conta_do_paciente, novas):
    r = paciente.post('/api/auth/alterar_senha_logado', json={'senha_atual': 'Senha@123', 'nova_senha': 'Nova@1234'})
    assert r.status_code == 200, r.get_json()
    assert novas()[-1][:4] == (PACIENTE, 'SENHA_ALTERADA', 'USUARIO', PACIENTE), novas()


def test_email_so_audita_quando_muda(paciente, conta_do_paciente, novas):
    assert paciente.patch('/api/usuarios/me', json={'email': conta_do_paciente}).status_code == 200
    assert novas() == []
    assert paciente.patch('/api/usuarios/me', json={'email': 'auditoria.teste@exemplo.com'}).status_code == 200
    assert novas()[-1][:4] == (PACIENTE, 'EMAIL_ALTERADO', 'USUARIO', PACIENTE), novas()


def test_sessao_prontuario_e_encaminhamento(paciente, profissional, agenda_vazia, sessoes, encaminhamentos, novas):
    inicio = datetime.combine(date.today() + timedelta(days=3), time(15))
    corpo = {'id_profissional': PROFISSIONAL, 'timestamp_inicio': inicio.isoformat(),
             'timestamp_fim': (inicio + timedelta(hours=1)).isoformat()}
    r = paciente.post('/api/consultas/', json=corpo)
    assert r.status_code == 201, r.get_json()
    sid = r.get_json()['sessao']['sessao_id']
    sessoes.append(sid)
    assert novas()[-1][:4] == (PACIENTE, 'SESSAO_AGENDADA', 'SESSAO', sid), novas()

    # Acao que falha nao deixa rastro: a linha sai junto com o rollback
    total = len(novas())
    assert paciente.post('/api/consultas/', json=corpo).status_code == 409
    assert len(novas()) == total, novas()

    r = profissional.patch(f'/api/consultas/{sid}', json={'link_reuniao': 'https://meet.exemplo.com/x'})
    assert r.status_code == 200 and r.get_json()['sessao']['link_reuniao'] == 'https://meet.exemplo.com/x', r.get_json()
    assert novas()[-1][:4] == (PROFISSIONAL, 'SESSAO_ALTERADA', 'SESSAO', sid), novas()

    # O vinculo para o prontuario vem da sessao acima
    assert profissional.get(f'/api/prontuario/{PACIENTE}').status_code == 200
    assert novas()[-1][:4] == (PROFISSIONAL, 'PRONTUARIO_ACESSO', 'USUARIO', PACIENTE), novas()

    r = profissional.post('/api/encaminhamentos/', json={'id_usuario': PACIENTE, 'motivo': 'Teste de auditoria'})
    assert r.status_code in (200, 201), r.get_json()
    eid = executar('SELECT MAX(ENCAMINHAMENTO_ID) FROM ENCAMINHAMENTO WHERE PACIENTE_ID = ?', (PACIENTE,))[0][0]
    encaminhamentos.append(eid)
    assert novas()[-1][:4] == (PROFISSIONAL, 'ENCAMINHAMENTO_CRIADO', 'ENCAMINHAMENTO', eid), novas()
