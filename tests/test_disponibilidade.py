# Precisa do Firebird no ar: python tests/test_disponibilidade.py
# F1: agenda do profissional 22, agendamento do paciente 23. Desfaz tudo o que cria.
import os
import sys
from datetime import date, datetime, time, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
from database.db import get_connection
from services.auth_service import gerar_token
from services.disponibilidade_service import dia_semana

PROFISSIONAL, PACIENTE = 22, 23


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


profissional = cliente(PROFISSIONAL, 'PSICOLOGO')
paciente = cliente(PACIENTE, 'PACIENTE')
anonimo = app.test_client()
original = executar('SELECT DIA_SEMANA, HORA_INICIO, HORA_FIM FROM DISPONIBILIDADE WHERE PROFISSIONAL_ID = ?',
                    (PROFISSIONAL,))
sessoes = []
# Daqui a uma semana, sempre no futuro e no mesmo dia da semana
dia = date.today() + timedelta(days=7)
semana = dia_semana(dia)
assert dia_semana(date(2026, 10, 18)) == 0 and dia_semana(date(2026, 10, 24)) == 6  # domingo e sabado


def agendar(hora_inicio, hora_fim):
    r = paciente.post('/api/consultas/', json={
        'id_profissional': PROFISSIONAL,
        'timestamp_inicio': datetime.combine(dia, hora_inicio).isoformat(),
        'timestamp_fim': datetime.combine(dia, hora_fim).isoformat()})
    if r.status_code == 201:
        sessoes.append(r.get_json()['sessao']['sessao_id'])
    return r


try:
    # Validacao do PUT
    for corpo in ({'janelas': [{'dia_semana': 7, 'inicio': '08:00', 'fim': '12:00'}]},
                  {'janelas': [{'dia_semana': 1, 'inicio': '12:00', 'fim': '08:00'}]},
                  {'janelas': [{'dia_semana': 1, 'inicio': '8h', 'fim': '12:00'}]},
                  {'janelas': [{'dia_semana': 1, 'inicio': '08:00', 'fim': '12:00'},
                               {'dia_semana': 1, 'inicio': '11:00', 'fim': '13:00'}]},
                  {'janelas': [{'dia_semana': True, 'inicio': '08:00', 'fim': '12:00'}]},
                  {'janelas': [{'dia_semana': 1, 'inicio': '08:00', 'fim': '12:00', 'x': 1}]},
                  {'janelas': {}}, {'outra': []}, ['lista']):
        r = profissional.put('/api/profissionais/me/disponibilidade', json=corpo)
        assert r.status_code == 400 and r.get_json()['error'], (corpo, r.status_code, r.get_json())
    assert anonimo.put('/api/profissionais/me/disponibilidade', json={'janelas': []}).status_code == 401
    assert paciente.put('/api/profissionais/me/disponibilidade', json={'janelas': []}).status_code == 403

    # Sem janela nenhuma, qualquer horario sem conflito vale (como antes da F1)
    assert profissional.put('/api/profissionais/me/disponibilidade', json={'janelas': []}).status_code == 200
    r = agendar(time(22), time(23))
    assert r.status_code == 201, r.get_json()

    janelas = [{'dia_semana': semana, 'inicio': '14:00', 'fim': '18:00'},
               {'dia_semana': semana, 'inicio': '08:00', 'fim': '12:00'}]
    r = profissional.put('/api/profissionais/me/disponibilidade', json={'janelas': janelas})
    assert r.status_code == 200, r.get_json()
    r = anonimo.get(f'/api/profissionais/{PROFISSIONAL}/disponibilidade')
    assert r.get_json()['janelas'] == janelas[::-1], r.get_json()
    assert anonimo.get('/api/profissionais/999999/disponibilidade').status_code == 404

    # Agendamento passa a exigir horario dentro de uma janela
    assert agendar(time(12), time(13)).status_code == 409
    assert agendar(time(11, 30), time(12, 30)).status_code == 409
    r = agendar(time(9), time(10))
    assert r.status_code == 201, r.get_json()

    # Horarios livres: janelas em fatias de 60 min, menos a sessao das 9h
    r = anonimo.get(f'/api/profissionais/{PROFISSIONAL}/horarios?de={dia}&ate={dia}')
    assert r.status_code == 200, r.get_json()
    inicios = [h['inicio'][11:] for h in r.get_json()['horarios']]
    assert inicios == ['08:00', '10:00', '11:00', '14:00', '15:00', '16:00', '17:00'], inicios
    r = anonimo.get(f'/api/profissionais/{PROFISSIONAL}/horarios?de={dia}&ate={dia}&duracao=90')
    assert [h['inicio'][11:] for h in r.get_json()['horarios']] == ['14:00', '15:30'], r.get_json()
    for query in ('de=ontem', f'de={dia}&ate={dia - timedelta(days=1)}', f'de={dia}&ate={dia + timedelta(days=31)}',
                  'duracao=10', 'duracao=abc'):
        r = anonimo.get(f'/api/profissionais/{PROFISSIONAL}/horarios?{query}')
        assert r.status_code == 400, (query, r.get_json())

    # Busca por disponibilidade usa a agenda
    def na_busca(hora_inicio, hora_fim):
        r = anonimo.get('/api/profissionais/?page_size=100&disponibilidade_inicio='
                        f'{datetime.combine(dia, hora_inicio):%Y-%m-%dT%H:%M}&disponibilidade_fim='
                        f'{datetime.combine(dia, hora_fim):%Y-%m-%dT%H:%M}')
        assert r.status_code == 200, r.get_json()
        return PROFISSIONAL in [p['id_usuario'] for p in r.get_json()['profissionais']]
    assert na_busca(time(15), time(16))
    assert not na_busca(time(9), time(10))  # ocupado
    assert not na_busca(time(19), time(20))  # fora da agenda

    print('ok: agenda do profissional')
finally:
    con = get_connection()
    try:
        cur = con.cursor()
        for sessao_id in sessoes:
            cur.execute('DELETE FROM SESSAO WHERE SESSAO_ID = ?', (sessao_id,))
        cur.execute('DELETE FROM DISPONIBILIDADE WHERE PROFISSIONAL_ID = ?', (PROFISSIONAL,))
        cur.executemany('INSERT INTO DISPONIBILIDADE (PROFISSIONAL_ID, DIA_SEMANA, HORA_INICIO, HORA_FIM) VALUES (?, ?, ?, ?)',
                        [(PROFISSIONAL, *linha) for linha in original])
        con.commit()
    finally:
        con.close()
