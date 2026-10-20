# S3 (codigo com validade e tentativas), S4 (token com exp e invalidado pela troca de senha).
import time as relogio

import jwt
import pytest

import config
from apoio import PACIENTE, checar, executar
from services import auth_service


@pytest.fixture
def codigos(monkeypatch):
    """Codigos que seriam enviados por e-mail."""
    enviados = []
    monkeypatch.setattr(auth_service.email_service, 'enviar_email_codigo_async',
                        lambda email, nome, codigo, finalidade: enviados.append(codigo))
    return enviados


def token_antigo(**extra):
    """Token do paciente emitido um minuto atras (antes de qualquer troca de senha do teste)."""
    agora = int(relogio.time())
    payload = {'id_usuario': PACIENTE, 'usuario_role': 'PACIENTE', 'iat': agora - 60, 'exp': agora + 3600, **extra}
    return {'Authorization': 'Bearer ' + jwt.encode(payload, config.SECRET_KEY, algorithm='HS256')}


def trocar(cliente, email, codigo, senha='Nova@1234'):
    return cliente.post('/api/auth/alterar_senha', json={'email': email, 'codigo': codigo, 'senha': senha})


def test_codigo_expirado_nao_serve(anonimo, conta_do_paciente, codigos):
    checar(anonimo.post('/api/auth/esqueci_senha', json={'email': conta_do_paciente}), 200)
    executar('UPDATE USUARIO SET CODIGO_EXPIRA_EM = DATEADD(-1 MINUTE TO CURRENT_TIMESTAMP) WHERE ID_USUARIO = ?',
             (PACIENTE,))
    assert 'expirado' in checar(trocar(anonimo, conta_do_paciente, codigos[-1]), 401, 'error')['error']
    checar(trocar(anonimo, conta_do_paciente, codigos[-1]), 401, 'error')


def test_codigo_invalidado_na_quinta_falha(anonimo, conta_do_paciente, codigos):
    checar(anonimo.post('/api/auth/esqueci_senha', json={'email': conta_do_paciente}), 200)
    certo = codigos[-1]
    errado = f'{(int(certo) + 1) % 1000000:06d}'
    for _ in range(auth_service.MAXIMO_TENTATIVAS):
        checar(trocar(anonimo, conta_do_paciente, errado), 401, 'error')
    # A contagem sobrevive ao erro (commit antes da excecao) e o codigo certo deixa de valer
    checar(trocar(anonimo, conta_do_paciente, certo), 401, 'error')
    # Um codigo novo zera a contagem
    checar(anonimo.post('/api/auth/esqueci_senha', json={'email': conta_do_paciente}), 200)
    checar(trocar(anonimo, conta_do_paciente, codigos[-1]), 200, 'message')


def test_troca_de_senha_derruba_tokens_antigos(anonimo, conta_do_paciente, codigos):
    checar(anonimo.get('/api/usuarios/me', headers=token_antigo()), 200, 'usuario')
    checar(anonimo.post('/api/auth/esqueci_senha', json={'email': conta_do_paciente}), 200)
    checar(trocar(anonimo, conta_do_paciente, codigos[-1]), 200, 'message')
    checar(anonimo.get('/api/usuarios/me', headers=token_antigo()), 401, 'error')
    checar(trocar(anonimo, conta_do_paciente, codigos[-1]), 401, 'error')  # codigo usado nao volta
    checar(anonimo.post('/api/auth/login', json={'email': conta_do_paciente, 'senha': 'Nova@1234'}), 200, 'usuario')
    checar(anonimo.get('/api/usuarios/me'), 200, 'usuario')


def test_troca_logada_renova_o_cookie(anonimo, conta_do_paciente):
    r = anonimo.post('/api/auth/alterar_senha_logado', headers=token_antigo(),
                     json={'senha_atual': 'Senha@123', 'nova_senha': 'Nova@1234'})
    checar(r, 200, 'message')
    assert 'Max-Age=28800' in r.headers['Set-Cookie'], r.headers['Set-Cookie']
    checar(anonimo.get('/api/usuarios/me', headers=token_antigo()), 401, 'error')
    checar(anonimo.get('/api/usuarios/me'), 200, 'usuario')  # o cookie novo vale


def test_token_vencido_ou_sem_exp(anonimo):
    agora = int(relogio.time())
    assert checar(anonimo.get('/api/usuarios/me', headers=token_antigo(exp=agora - 1)), 401)['error'] == 'Expired token'
    sem_exp = jwt.encode({'id_usuario': PACIENTE, 'usuario_role': 'PACIENTE'}, config.SECRET_KEY, algorithm='HS256')
    checar(anonimo.get('/api/usuarios/me', headers={'Authorization': 'Bearer ' + sem_exp}), 401, 'error')

