# Feature 7: o paciente 23 favorita o profissional 22.
from datetime import date, timedelta

import pytest

from apoio import PACIENTE, PROFISSIONAL, executar
from services.disponibilidade_service import dia_semana


@pytest.fixture
def sem_favoritos():
    antes = executar('SELECT PROFISSIONAL_ID FROM FAVORITO WHERE PACIENTE_ID = ?', (PACIENTE,))
    executar('DELETE FROM FAVORITO WHERE PACIENTE_ID = ?', (PACIENTE,))
    yield
    executar('DELETE FROM FAVORITO WHERE PACIENTE_ID = ?', (PACIENTE,))
    for (profissional_id,) in antes:
        executar('INSERT INTO FAVORITO (PACIENTE_ID, PROFISSIONAL_ID) VALUES (?, ?)', (PACIENTE, profissional_id))


def test_permissoes(anonimo, paciente, profissional, sem_favoritos):
    assert anonimo.get('/api/favoritos/').status_code == 401
    assert profissional.get('/api/favoritos/').status_code == 403
    assert profissional.post(f'/api/favoritos/{PROFISSIONAL}').status_code == 403
    assert paciente.post('/api/favoritos/999999').status_code == 404
    assert paciente.delete(f'/api/favoritos/{PROFISSIONAL}').status_code == 404


def test_favoritar_listar_com_proximo_horario_e_remover(paciente, profissional, sem_favoritos, agenda_vazia):
    assert paciente.post(f'/api/favoritos/{PROFISSIONAL}').status_code == 201
    assert paciente.post(f'/api/favoritos/{PROFISSIONAL}').status_code == 200  # repetido nao duplica

    r = paciente.get('/api/favoritos/')
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'private, no-store', r.get_json()
    favoritos = r.get_json()['favoritos']
    assert [f['id_profissional'] for f in favoritos] == [PROFISSIONAL], favoritos
    assert favoritos[0]['proximo_horario'] is None, favoritos  # sem agenda cadastrada
    for chave in ('nome', 'especialidade', 'preco_hora', 'foto_url', 'favoritado_em'):
        assert chave in favoritos[0], chave

    # Agenda so amanha das 10h as 11h: e esse o proximo horario livre
    amanha = date.today() + timedelta(days=1)
    r = profissional.put('/api/profissionais/me/disponibilidade',
                         json={'janelas': [{'dia_semana': dia_semana(amanha), 'inicio': '10:00', 'fim': '11:00'}]})
    assert r.status_code == 200, r.get_json()
    proximo = paciente.get('/api/favoritos/').get_json()['favoritos'][0]['proximo_horario']
    assert proximo == {'inicio': f'{amanha}T10:00', 'fim': f'{amanha}T11:00'}, proximo

    assert paciente.delete(f'/api/favoritos/{PROFISSIONAL}').status_code == 200
    assert paciente.get('/api/favoritos/').get_json()['favoritos'] == []
