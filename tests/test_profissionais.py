# Precisa do Firebird no ar: python tests/test_profissionais.py
# Usa o profissional 22 e o paciente 23 do banco local; desfaz tudo o que cria.
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
from database.db import get_connection
from services.auth_service import gerar_token

PROFISSIONAL, PACIENTE, OUTRO_PACIENTE = 22, 23, 25


def executar(sql, params=()):
    con = get_connection()
    cur = con.cursor()
    cur.execute(sql, params)
    linha = cur.fetchone() if cur.description else None
    con.commit()
    con.close()
    return linha


def cliente(id_usuario, papel):
    c = app.test_client()
    with app.app_context():
        c.set_cookie('access_token', gerar_token({'id_usuario': id_usuario, 'usuario_role': papel}))
    return c


def busca(query=''):
    r = anonimo.get('/api/profissionais/?page_size=100' + query)
    return r.status_code, {p['id_usuario']: p for p in (r.get_json() or {}).get('profissionais', [])}


def nova_sessao(paciente, status, inicio, fim):
    return executar('''INSERT INTO SESSAO (PACIENTE_ID, PROFISSIONAL_ID, DATA_HORA_INICIO, DATA_HORA_FIM,
        STATUS, VALOR_CENTAVOS) VALUES (?, ?, ?, ?, ?, 12000) RETURNING SESSAO_ID''',
                    (paciente, PROFISSIONAL, inicio, fim, status))[0]


anonimo = app.test_client()
profissional = cliente(PROFISSIONAL, 'PSICOLOGO')
paciente = cliente(PACIENTE, 'PACIENTE')
outro_paciente = cliente(OUTRO_PACIENTE, 'PACIENTE')
original = executar('SELECT ABORDAGEM, MODALIDADE FROM PROFISSIONAL WHERE USUARIO_ID = ?', (PROFISSIONAL,))
sessoes = []

try:
    # 1. Campos novos na listagem e no detalhe
    status, lista = busca()
    assert status == 200, status
    for campo in ('especialidade', 'abordagem', 'modalidade', 'avaliacao', 'total_avaliacoes'):
        assert campo in lista[PROFISSIONAL], campo
    detalhe = anonimo.get(f'/api/profissionais/{PROFISSIONAL}').get_json()['profissionais']
    assert detalhe['total_avaliacoes'] == 0 and detalhe['avaliacao'] is None, detalhe

    # 2. PATCH /me normaliza e valida
    r = profissional.patch('/api/profissionais/me', json={'abordagem': 'tcc', 'modalidade': 'online'})
    assert r.status_code == 200, r.get_json()
    p = busca()[1][PROFISSIONAL]
    assert (p['abordagem'], p['modalidade']) == ('TCC', 'ONLINE'), p
    assert profissional.patch('/api/profissionais/me', json={'abordagem': 'xyz'}).status_code == 400
    assert profissional.patch('/api/profissionais/me', json={'modalidade': 'hibrido'}).status_code == 400
    assert profissional.patch('/api/profissionais/me', json={'abordagem': 5}).status_code == 400
    assert profissional.patch('/api/profissionais/me', json={'outro': 1}).status_code == 400
    assert profissional.patch('/api/profissionais/me', json={'abordagem': 'Psicanalise'}).status_code == 200
    assert busca()[1][PROFISSIONAL]['abordagem'] == 'Psicanálise'

    # 3. Filtros
    assert PROFISSIONAL in busca('&abordagem=psicanálise')[1]
    assert busca('&abordagem=TCC') == (200, {})
    assert busca('&abordagem=xyz')[0] == 400
    assert PROFISSIONAL in busca('&modalidade=Online')[1]
    assert PROFISSIONAL not in busca('&modalidade=Presencial')[1]
    assert profissional.patch('/api/profissionais/me', json={'modalidade': 'ambas'}).status_code == 200
    assert PROFISSIONAL in busca('&modalidade=Presencial')[1] and PROFISSIONAL in busca('&modalidade=Online')[1]
    assert busca('&modalidade=xyz')[0] == 400
    for invalido in ('6', '0', 'abc', 'nan'):
        assert busca('&avaliacao_min=' + invalido)[0] == 400, invalido
    assert PROFISSIONAL not in busca('&avaliacao_min=1')[1]  # sem avaliacao fica de fora

    # 4. Avaliacao
    realizada = nova_sessao(PACIENTE, 'REALIZADO', datetime(2026, 9, 1, 10), datetime(2026, 9, 1, 11))
    realizada2 = nova_sessao(PACIENTE, 'REALIZADO', datetime(2026, 9, 2, 10), datetime(2026, 9, 2, 11))
    agendada = nova_sessao(PACIENTE, 'AGENDADO', datetime(2030, 1, 1, 10), datetime(2030, 1, 1, 11))
    sessoes += [realizada, realizada2, agendada]
    url = f'/api/consultas/{realizada}/avaliacao'

    assert anonimo.post(url, json={'nota': 5}).status_code == 401
    assert profissional.post(url, json={'nota': 5}).status_code == 403
    assert outro_paciente.post(url, json={'nota': 5}).status_code == 404
    assert paciente.post(f'/api/consultas/{agendada}/avaliacao', json={'nota': 5}).status_code == 409
    for corpo in ({'nota': 6}, {'nota': 0}, {'nota': True}, {'nota': 4.5}, {'nota': '5'}, {},
                  {'nota': 5, 'extra': 1}, {'nota': 5, 'comentario': 'x' * 501}, {'nota': 5, 'comentario': 3}):
        assert paciente.post(url, json=corpo).status_code == 400, corpo

    r = paciente.post(url, json={'nota': 5, 'comentario': '  otima  '})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['avaliacao'] == {'sessao_id': realizada, 'nota': 5}
    assert paciente.post(url, json={'nota': 3}).status_code == 409
    assert paciente.post(f'/api/consultas/{realizada2}/avaliacao', json={'nota': 4}).status_code == 201

    p = busca()[1][PROFISSIONAL]
    assert p['avaliacao'] == 4.5 and isinstance(p['avaliacao'], float) and p['total_avaliacoes'] == 2, p
    assert PROFISSIONAL in busca('&avaliacao_min=4.5')[1]
    assert PROFISSIONAL not in busca('&avaliacao_min=5')[1]
    assert anonimo.get(f'/api/profissionais/{PROFISSIONAL}').get_json()['profissionais']['avaliacao'] == 4.5

    consultas = {c['sessao_id']: c for c in paciente.get('/api/consultas/').get_json()['consultas']}
    assert consultas[realizada]['nota_avaliacao'] == 5 and consultas[agendada]['nota_avaliacao'] is None

    # 5. Filtros antigos e combinacao
    assert PROFISSIONAL in busca('&preco_max=15000&especialidade=Psicologia&abordagem=Psicanalise')[1]
    assert PROFISSIONAL not in busca('&preco_max=100')[1]
    assert busca('&disponibilidade_inicio=2026-09-29T10:00&disponibilidade_fim=2026-09-29T11:00')[0] == 200
    total = anonimo.get('/api/profissionais/?avaliacao_min=4').get_json()['total']
    assert total == 1, total

    # Vazio/null limpa
    assert profissional.patch('/api/profissionais/me', json={'abordagem': '', 'modalidade': None}).status_code == 200
    p = busca()[1][PROFISSIONAL]
    assert p['abordagem'] is None and p['modalidade'] is None, p
finally:
    for sessao in sessoes:
        executar('DELETE FROM SESSAO WHERE SESSAO_ID = ?', (sessao,))  # cascade apaga a AVALIACAO
    executar('UPDATE PROFISSIONAL SET ABORDAGEM = ?, MODALIDADE = ? WHERE USUARIO_ID = ?', (*original, PROFISSIONAL))

print('ok: filtros, campos novos e avaliacao de profissionais')
