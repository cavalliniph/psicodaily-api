# Precisa do Firebird no ar: python tests/test_favoritos.py
# Feature 7: o paciente 23 favorita o profissional 22. Desfaz tudo o que cria.
import os
import sys
from datetime import date, timedelta

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


paciente = cliente(PACIENTE, 'PACIENTE')
profissional = cliente(PROFISSIONAL, 'PSICOLOGO')
anonimo = app.test_client()
agenda = executar('SELECT DIA_SEMANA, HORA_INICIO, HORA_FIM FROM DISPONIBILIDADE WHERE PROFISSIONAL_ID = ?', (PROFISSIONAL,))
favoritos_antes = executar('SELECT PROFISSIONAL_ID FROM FAVORITO WHERE PACIENTE_ID = ?', (PACIENTE,))

try:
    executar('DELETE FROM FAVORITO WHERE PACIENTE_ID = ?', (PACIENTE,))
    executar('DELETE FROM DISPONIBILIDADE WHERE PROFISSIONAL_ID = ?', (PROFISSIONAL,))

    assert anonimo.get('/api/favoritos/').status_code == 401
    assert profissional.get('/api/favoritos/').status_code == 403
    assert profissional.post(f'/api/favoritos/{PROFISSIONAL}').status_code == 403
    assert paciente.post('/api/favoritos/999999').status_code == 404
    assert paciente.delete(f'/api/favoritos/{PROFISSIONAL}').status_code == 404

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

    print('ok: favoritos do paciente')
finally:
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute('DELETE FROM FAVORITO WHERE PACIENTE_ID = ?', (PACIENTE,))
        cur.executemany('INSERT INTO FAVORITO (PACIENTE_ID, PROFISSIONAL_ID) VALUES (?, ?)',
                        [(PACIENTE, linha[0]) for linha in favoritos_antes or []])
        cur.execute('DELETE FROM DISPONIBILIDADE WHERE PROFISSIONAL_ID = ?', (PROFISSIONAL,))
        cur.executemany('INSERT INTO DISPONIBILIDADE (PROFISSIONAL_ID, DIA_SEMANA, HORA_INICIO, HORA_FIM) VALUES (?, ?, ?, ?)',
                        [(PROFISSIONAL, *linha) for linha in agenda])
        con.commit()
    finally:
        con.close()
