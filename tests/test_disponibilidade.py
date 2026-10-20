# F1: agenda do profissional 22, agendamento do paciente 23.
from datetime import date, datetime, time, timedelta

import pytest

from apoio import PROFISSIONAL
from services.disponibilidade_service import dia_semana

# Daqui a uma semana, sempre no futuro e no mesmo dia da semana
DIA = date.today() + timedelta(days=7)


def test_dia_semana_comeca_no_domingo():
    assert dia_semana(date(2026, 10, 18)) == 0 and dia_semana(date(2026, 10, 24)) == 6


@pytest.mark.parametrize('corpo', [
    {'janelas': [{'dia_semana': 7, 'inicio': '08:00', 'fim': '12:00'}]},
    {'janelas': [{'dia_semana': 1, 'inicio': '12:00', 'fim': '08:00'}]},
    {'janelas': [{'dia_semana': 1, 'inicio': '8h', 'fim': '12:00'}]},
    {'janelas': [{'dia_semana': 1, 'inicio': '08:00', 'fim': '12:00'},
                 {'dia_semana': 1, 'inicio': '11:00', 'fim': '13:00'}]},
    {'janelas': [{'dia_semana': True, 'inicio': '08:00', 'fim': '12:00'}]},
    {'janelas': [{'dia_semana': 1, 'inicio': '08:00', 'fim': '12:00', 'x': 1}]},
    {'janelas': {}},
    {'outra': []},
    ['lista'],
])
def test_put_invalido(profissional, corpo):
    r = profissional.put('/api/profissionais/me/disponibilidade', json=corpo)
    assert r.status_code == 400 and r.get_json()['error'], (r.status_code, r.get_json())


def test_put_so_profissional(anonimo, paciente):
    assert anonimo.put('/api/profissionais/me/disponibilidade', json={'janelas': []}).status_code == 401
    assert paciente.put('/api/profissionais/me/disponibilidade', json={'janelas': []}).status_code == 403


@pytest.mark.parametrize('query', ['de=ontem', f'de={DIA}&ate={DIA - timedelta(days=1)}',
                                   f'de={DIA}&ate={DIA + timedelta(days=31)}', 'duracao=10', 'duracao=abc'])
def test_horarios_parametro_invalido(anonimo, query):
    r = anonimo.get(f'/api/profissionais/{PROFISSIONAL}/horarios?{query}')
    assert r.status_code == 400, r.get_json()


def test_agenda_rege_agendamento_horarios_e_busca(anonimo, paciente, profissional, agenda_vazia, sessoes):
    def agendar(hora_inicio, hora_fim):
        r = paciente.post('/api/consultas/', json={
            'id_profissional': PROFISSIONAL,
            'timestamp_inicio': datetime.combine(DIA, hora_inicio).isoformat(),
            'timestamp_fim': datetime.combine(DIA, hora_fim).isoformat()})
        if r.status_code == 201:
            sessoes.append(r.get_json()['sessao']['sessao_id'])
        return r

    def na_busca(hora_inicio, hora_fim):
        r = anonimo.get('/api/profissionais/?page_size=100&disponibilidade_inicio='
                        f'{datetime.combine(DIA, hora_inicio):%Y-%m-%dT%H:%M}&disponibilidade_fim='
                        f'{datetime.combine(DIA, hora_fim):%Y-%m-%dT%H:%M}')
        assert r.status_code == 200, r.get_json()
        return PROFISSIONAL in [p['id_usuario'] for p in r.get_json()['profissionais']]

    # Sem janela nenhuma, qualquer horario sem conflito vale (como antes da F1)
    r = agendar(time(22), time(23))
    assert r.status_code == 201, r.get_json()

    janelas = [{'dia_semana': dia_semana(DIA), 'inicio': '14:00', 'fim': '18:00'},
               {'dia_semana': dia_semana(DIA), 'inicio': '08:00', 'fim': '12:00'}]
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
    r = anonimo.get(f'/api/profissionais/{PROFISSIONAL}/horarios?de={DIA}&ate={DIA}')
    assert r.status_code == 200, r.get_json()
    inicios = [h['inicio'][11:] for h in r.get_json()['horarios']]
    assert inicios == ['08:00', '10:00', '11:00', '14:00', '15:00', '16:00', '17:00'], inicios
    r = anonimo.get(f'/api/profissionais/{PROFISSIONAL}/horarios?de={DIA}&ate={DIA}&duracao=90')
    assert [h['inicio'][11:] for h in r.get_json()['horarios']] == ['14:00', '15:30'], r.get_json()

    # Busca por disponibilidade usa a agenda
    assert na_busca(time(15), time(16))
    assert not na_busca(time(9), time(10))  # ocupado
    assert not na_busca(time(19), time(20))  # fora da agenda
