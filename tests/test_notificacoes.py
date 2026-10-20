# F3: notificacoes gravadas por notificar() e lidas pelo proprio usuario.
import pytest

from apoio import OUTRO_PACIENTE, PACIENTE
from database.db import transacao
from services import notificacoes_service


def notificar(usuario_id, titulo, dados=None):
    with transacao() as cur:
        email = notificacoes_service.notificar(cur, usuario_id, 'VAGA_LISTA_ESPERA', titulo, 'Mensagem “com” acento – e emoji 😊', dados)
        cur.execute('SELECT MAX(NOTIFICACAO_ID) FROM NOTIFICACAO')
        return cur.fetchone()[0], email


def test_notificar_grava_e_devolve_o_email_sem_enviar(ultima_notificacao):
    nid, email = notificar(PACIENTE, 'Título', {'sessao_id': 1})
    assert nid > ultima_notificacao
    assert email[0] == 'paciente.teste@exemplo.com' and email[1] == 'Título', email
    assert email[2].startswith('Olá, Bruno Paciente Teste.') and 'emoji 😊' in email[2], email
    with pytest.raises(AssertionError):
        notificacoes_service.notificar(None, PACIENTE, 'XPTO', 'Titulo', 'Mensagem')


def test_listar_paginar_e_marcar_lidas(anonimo, paciente, outro_paciente, ultima_notificacao):
    antes = paciente.get('/api/notificacoes/').get_json()['nao_lidas']
    ids = [notificar(PACIENTE, f'N{i}', {'i': i})[0] for i in range(3)]
    do_outro = notificar(OUTRO_PACIENTE, 'Do outro')[0]

    assert anonimo.get('/api/notificacoes/').status_code == 401
    r = paciente.get('/api/notificacoes/?limite=2')
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'private, no-store'
    pagina = r.get_json()
    assert [n['notificacao_id'] for n in pagina['notificacoes']] == ids[:0:-1], pagina
    assert pagina['nao_lidas'] == antes + 3 and pagina['proximo_cursor'] == ids[1], pagina
    primeira = pagina['notificacoes'][0]
    assert (primeira['tipo'], primeira['titulo'], primeira['dados'], primeira['lida']) == ('VAGA_LISTA_ESPERA', 'N2', {'i': 2}, False)
    assert primeira['mensagem'] == 'Mensagem “com” acento – e emoji 😊'
    pagina = paciente.get(f'/api/notificacoes/?limite=2&antes={ids[1]}').get_json()
    assert pagina['notificacoes'][0]['notificacao_id'] == ids[0], pagina

    # So marca as proprias: a do outro paciente fica intacta
    r = paciente.post('/api/notificacoes/lidas', json={'ids': [ids[0], do_outro]})
    assert r.status_code == 200 and r.get_json()['atualizadas'] == 1, r.get_json()
    assert outro_paciente.get('/api/notificacoes/').get_json()['notificacoes'][0]['lida'] is False
    assert paciente.post('/api/notificacoes/lidas').get_json()['atualizadas'] == antes + 2
    assert paciente.get('/api/notificacoes/').get_json()['nao_lidas'] == 0


@pytest.mark.parametrize('corpo', [{'ids': []}, {'ids': 'x'}, {'ids': [1, '2']}, {'ids': [True]},
                                   {'ids': list(range(101))}, {'outro': 1}, ['lista']])
def test_marcar_lidas_invalido(paciente, corpo):
    assert paciente.post('/api/notificacoes/lidas', json=corpo).status_code == 400


@pytest.mark.parametrize('query', ['limite=0', 'limite=101', 'antes=0', 'limite=x'])
def test_paginacao_invalida(paciente, query):
    assert paciente.get(f'/api/notificacoes/?{query}').status_code == 400
