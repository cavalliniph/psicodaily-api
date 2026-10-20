# Features 5 e 2: questionario do paciente e profissionais recomendados a partir dele.
import pytest

from apoio import PACIENTE, PROFISSIONAL, executar

COLUNAS = 'ABORDAGEM, MODALIDADE, IDIOMAS, AREAS_ATUACAO, PRECO_HORA'


@pytest.fixture
def sem_preferencias():
    original = executar('SELECT RESPOSTAS FROM PREFERENCIA_PACIENTE WHERE PACIENTE_ID = ?', (PACIENTE,))
    executar('DELETE FROM PREFERENCIA_PACIENTE WHERE PACIENTE_ID = ?', (PACIENTE,))
    yield
    executar('DELETE FROM PREFERENCIA_PACIENTE WHERE PACIENTE_ID = ?', (PACIENTE,))
    if original:
        executar('INSERT INTO PREFERENCIA_PACIENTE (PACIENTE_ID, RESPOSTAS) VALUES (?, ?)', (PACIENTE, original[0][0]))


@pytest.fixture
def perfil_original():
    original = executar(f'SELECT {COLUNAS} FROM PROFISSIONAL WHERE USUARIO_ID = ?', (PROFISSIONAL,))[0]
    yield
    executar(f'''UPDATE PROFISSIONAL SET {", ".join(c + " = ?" for c in COLUNAS.split(", "))}
        WHERE USUARIO_ID = ?''', (*original, PROFISSIONAL))


def test_questionario(anonimo, profissional, paciente, sem_preferencias):
    assert anonimo.get('/api/usuarios/me/preferencias').status_code == 401
    assert profissional.get('/api/usuarios/me/preferencias').status_code == 403
    vazio = paciente.get('/api/usuarios/me/preferencias').get_json()
    assert vazio['preferencias'] is None and 'Ansiedade' in vazio['opcoes']['motivos'], vazio

    for invalido in ({}, {'motivos': ['Astrologia']}, {'motivos': ['Ansiedade', 'Luto', 'TDAH', 'Trauma']},
                     {'preco_max': '100'}, {'idioma': 'Klingon'}, {'genero': 'F'}):
        assert paciente.put('/api/usuarios/me/preferencias', json=invalido).status_code == 400, invalido

    r = paciente.put('/api/usuarios/me/preferencias', json={'motivos': 'ansiedade,luto', 'abordagem': 'tcc',
                                                            'modalidade': 'online', 'idioma': 'ingles', 'preco_max': 20000})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['preferencias'] == {'motivos': ['Ansiedade', 'Luto'], 'abordagem': 'TCC', 'modalidade': 'ONLINE',
                                            'idioma': 'Inglês', 'preco_max': 20000}
    # PUT substitui: o que nao veio deixa de ser preferencia
    r = paciente.put('/api/usuarios/me/preferencias', json={'abordagem': 'Gestalt'})
    assert r.get_json()['preferencias'] == {'abordagem': 'Gestalt'}


def test_recomendados(anonimo, paciente, sem_preferencias, perfil_original):
    assert anonimo.get('/api/profissionais/recomendados').status_code == 401
    r = paciente.get('/api/profissionais/recomendados').get_json()
    assert r['questionario_respondido'] is False and r['profissionais'], r

    executar('''UPDATE PROFISSIONAL SET ABORDAGEM = 'Psicanálise', MODALIDADE = 'ONLINE', IDIOMAS = 'Libras',
        AREAS_ATUACAO = 'Luto,Trauma', PRECO_HORA = 100 WHERE USUARIO_ID = ?''', (PROFISSIONAL,))
    paciente.put('/api/usuarios/me/preferencias', json={'motivos': ['Luto', 'Trauma'], 'abordagem': 'Psicanálise',
                                                        'modalidade': 'ONLINE', 'idioma': 'Libras', 'preco_max': 100})
    r = paciente.get('/api/profissionais/recomendados').get_json()
    primeiro = r['profissionais'][0]
    assert r['questionario_respondido'] is True and primeiro['id_usuario'] == PROFISSIONAL, r
    assert primeiro['pontuacao'] >= 3 * 2 + 3 + 2 + 2 + 1, primeiro
