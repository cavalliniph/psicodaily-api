# Precisa do Firebird no ar: python tests/test_conteudos.py
# Feature 8: conteudos do profissional 22; o paciente 23 tenta mexer. Desfaz tudo o que cria.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
from database.db import get_connection
from services.auth_service import gerar_token

PROFISSIONAL, PACIENTE, OUTRO_PROFISSIONAL = 22, 23, 24


def cliente(id_usuario, papel):
    c = app.test_client()
    with app.app_context():
        c.set_cookie('access_token', gerar_token({'id_usuario': id_usuario, 'usuario_role': papel}))
    return c


profissional = cliente(PROFISSIONAL, 'PSICOLOGO')
outro = cliente(OUTRO_PROFISSIONAL, 'PSIQUIATRA')
paciente = cliente(PACIENTE, 'PACIENTE')
anonimo = app.test_client()
criados = []

try:
    r = profissional.post('/api/conteudos/', json={'titulo': '  Ansiedade – 5 dicas  ',
                                                   'corpo': '# Respire\n\n“Calma” é **treino** 😊 e 3 < 5'})
    assert r.status_code == 201, r.get_json()
    conteudo = r.get_json()['conteudo']
    criados.append(conteudo['conteudo_id'])
    assert conteudo['titulo'] == 'Ansiedade – 5 dicas' and conteudo['profissional_id'] == PROFISSIONAL, conteudo
    assert conteudo['publicado_em'] and conteudo['atualizado_em'] is None, conteudo
    segundo = profissional.post('/api/conteudos/', json={'titulo': 'Sono', 'corpo': 'Durma bem.'}).get_json()['conteudo']
    criados.append(segundo['conteudo_id'])

    # Listagem publica, mais recente primeiro
    r = anonimo.get(f'/api/profissionais/{PROFISSIONAL}/conteudos')
    assert r.status_code == 200, r.get_json()
    lista = [c for c in r.get_json()['conteudos'] if c['conteudo_id'] in criados]
    assert [c['conteudo_id'] for c in lista] == criados[::-1], lista
    assert lista[1]['corpo'] == '# Respire\n\n“Calma” é **treino** 😊 e 3 < 5', lista[1]
    assert anonimo.get('/api/profissionais/999999/conteudos').status_code == 404

    # Validacao
    for corpo in ({'titulo': 'ab', 'corpo': 'x'}, {'titulo': 'Titulo', 'corpo': ' '},
                  {'titulo': 'Titulo', 'corpo': 'x' * 20001}, {'titulo': 'Titulo', 'corpo': 5},
                  {'titulo': 'Titulo', 'corpo': 'oi <script>alert(1)</script>'},
                  {'titulo': '<b>Titulo</b>', 'corpo': 'x'}, {'titulo': 'Titulo', 'corpo': 'x', 'extra': 1},
                  ['lista']):
        r = profissional.post('/api/conteudos/', json=corpo)
        assert r.status_code == 400 and r.get_json()['error'], (corpo, r.status_code, r.get_json())
    assert profissional.patch(f"/api/conteudos/{segundo['conteudo_id']}", json={}).status_code == 400

    # Permissoes: anonimo 401, paciente 403, outro profissional 404 (nao ve o que nao e dele)
    assert anonimo.post('/api/conteudos/', json={'titulo': 'Titulo', 'corpo': 'x'}).status_code == 401
    assert paciente.post('/api/conteudos/', json={'titulo': 'Titulo', 'corpo': 'x'}).status_code == 403
    assert outro.patch(f"/api/conteudos/{segundo['conteudo_id']}", json={'titulo': 'Invadido'}).status_code == 404
    assert outro.delete(f"/api/conteudos/{segundo['conteudo_id']}").status_code == 404

    # Edicao parcial e remocao pelo dono
    r = profissional.patch(f"/api/conteudos/{segundo['conteudo_id']}", json={'titulo': 'Sono e humor'})
    assert r.status_code == 200, r.get_json()
    editado = r.get_json()['conteudo']
    assert editado['titulo'] == 'Sono e humor' and editado['corpo'] == 'Durma bem.' and editado['atualizado_em'], editado
    assert profissional.delete(f"/api/conteudos/{segundo['conteudo_id']}").status_code == 200
    assert profissional.delete(f"/api/conteudos/{segundo['conteudo_id']}").status_code == 404
    ids = [c['conteudo_id'] for c in anonimo.get(f'/api/profissionais/{PROFISSIONAL}/conteudos').get_json()['conteudos']]
    assert segundo['conteudo_id'] not in ids and conteudo['conteudo_id'] in ids, ids

    print('ok: conteudos do profissional')
finally:
    con = get_connection()
    try:
        for conteudo_id in criados:
            con.cursor().execute('DELETE FROM CONTEUDO WHERE CONTEUDO_ID = ?', (conteudo_id,))
        con.commit()
    finally:
        con.close()
