# Precisa do Firebird no ar: python tests/test_perfil_profissional.py
# Perfil completo: formacao, experiencia, idiomas, areas de atuacao e video.
# Usa o profissional 22 do banco local; desfaz tudo o que cria.
import os
import random
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
from database.db import get_connection
from funcao import AREAS_ATUACAO, normalizar_ano_inicio, normalizar_lista, normalizar_video_url, validar_cpf
from services import profissionais_service
from services.auth_service import gerar_token

PROFISSIONAL = 22
COLUNAS = 'ABORDAGEM, MODALIDADE, FORMACAO, ANO_INICIO_ATUACAO, IDIOMAS, AREAS_ATUACAO, VIDEO_URL'


def executar(sql, params=()):
    con = get_connection()
    cur = con.cursor()
    cur.execute(sql, params)
    linha = cur.fetchone() if cur.description else None
    con.commit()
    con.close()
    return linha


def cpf_valido():
    while True:
        cpf = ''.join(random.choice('0123456789') for _ in range(9))
        for i in (9, 10):
            soma = sum(int(cpf[j]) * (i + 1 - j) for j in range(i))
            cpf += str(soma * 10 % 11 % 10)
        if validar_cpf(cpf):
            return cpf


# 1. Validadores puros
YT = 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'
for entrada, esperado in [
    ('https://www.youtube.com/watch?v=dQw4w9WgXcQ', YT),
    ('https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s', YT),
    ('https://m.youtube.com/watch?v=dQw4w9WgXcQ', YT),
    ('https://youtu.be/dQw4w9WgXcQ?si=abc', YT),
    ('https://www.youtube.com/shorts/dQw4w9WgXcQ', YT),
    ('https://www.youtube.com/embed/dQw4w9WgXcQ', YT),
    ('  https://youtu.be/dQw4w9WgXcQ  ', YT),
    ('https://vimeo.com/76979871', 'https://player.vimeo.com/video/76979871'),
    ('https://vimeo.com/76979871/af3c2b1d9e', 'https://player.vimeo.com/video/76979871?h=af3c2b1d9e'),
    ('https://player.vimeo.com/video/76979871?h=af3c2b1d9e&badge=0', 'https://player.vimeo.com/video/76979871?h=af3c2b1d9e'),
    ('https://www.youtube.com/watch?v=curto', None),
    ('https://www.youtube.com/watch?v=dQw4w9WgXcQ"><script>', None),
    ('https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ', None),
    ('https://evil.com/youtu.be/dQw4w9WgXcQ', None),
    ('javascript:alert(1)//youtu.be/dQw4w9WgXcQ', None),
    ('https://www.instagram.com/reel/abc', None),
    ('https://vimeo.com/channels/staffpicks/76979871', None),
    ('https://vimeo.com/76979871/<b>', None),
    ('youtu.be/dQw4w9WgXcQ', None),
    (12345, None),
]:
    assert normalizar_video_url(entrada) == esperado, (entrada, normalizar_video_url(entrada))

IDIOMAS = ['Português', 'Inglês', 'Espanhol', 'Francês', 'Italiano', 'Alemão', 'Libras']
assert normalizar_lista(['ingles', ' LIBRAS ', 'Inglês'], IDIOMAS, 7) == 'Inglês,Libras'
assert normalizar_lista('portugues, espanhol', IDIOMAS, 7) == 'Português,Espanhol'
assert normalizar_lista('["Alemao"]', IDIOMAS, 7) == 'Alemão'
assert normalizar_lista(['Klingon'], IDIOMAS, 7) is None
assert normalizar_lista([1], IDIOMAS, 7) is None
assert normalizar_lista({'a': 1}, IDIOMAS, 7) is None
assert normalizar_lista('[quebrado', IDIOMAS, 7) is None
assert normalizar_lista(AREAS_ATUACAO[:9], AREAS_ATUACAO, 8) is None
assert normalizar_ano_inicio('2015') == 2015 and normalizar_ano_inicio(1950) == 1950
for invalido in (1949, date.today().year + 1, '20x5', True, 2015.5, None):
    assert normalizar_ano_inicio(invalido) is None, invalido

# 2. Rotas
with app.app_context():
    token = gerar_token({'id_usuario': PROFISSIONAL, 'usuario_role': 'PSICOLOGO'})
profissional = app.test_client()
profissional.set_cookie('access_token', token)
anonimo = app.test_client()
original = executar(f'SELECT {COLUNAS} FROM PROFISSIONAL WHERE USUARIO_ID = ?', (PROFISSIONAL,))
envios = []
profissionais_service.enviar_ativacao = envios.append
novo_usuario = None

try:
    r = profissional.patch('/api/profissionais/me', json={
        'formacao': '  Psicologia - USP (2012); especialização em TCC  ',
        'ano_inicio_atuacao': 2014,
        'idiomas': ['portugues', 'Inglês', 'libras'],
        'areas_atuacao': 'ansiedade, depressao, TDAH',
        'video_url': 'https://youtu.be/dQw4w9WgXcQ',
    })
    assert r.status_code == 200, r.get_json()
    detalhe = anonimo.get(f'/api/profissionais/{PROFISSIONAL}').get_json()['profissionais']
    assert detalhe['formacao'] == 'Psicologia - USP (2012); especialização em TCC', detalhe
    assert detalhe['ano_inicio_atuacao'] == 2014, detalhe
    assert detalhe['anos_experiencia'] == date.today().year - 2014, detalhe
    assert detalhe['idiomas'] == ['Português', 'Inglês', 'Libras'], detalhe
    assert detalhe['areas_atuacao'] == ['Ansiedade', 'Depressão', 'TDAH'], detalhe
    assert detalhe['video_url'] == YT, detalhe

    busca = anonimo.get('/api/profissionais/?page_size=100').get_json()['profissionais']
    na_busca = next(p for p in busca if p['id_usuario'] == PROFISSIONAL)
    assert {k: na_busca[k] for k in detalhe} == detalhe, (na_busca, detalhe)
    # Quem nao preencheu recebe listas vazias e null, nao chaves faltando
    outro = next((p for p in busca if p['id_usuario'] != PROFISSIONAL and not p['idiomas']), None)
    if outro:
        assert outro['areas_atuacao'] == [] and outro['anos_experiencia'] is None, outro

    for corpo in (
        {'idiomas': ['Klingon']},
        {'idiomas': 5},
        {'areas_atuacao': AREAS_ATUACAO[:9]},
        {'ano_inicio_atuacao': 1900},
        {'ano_inicio_atuacao': date.today().year + 1},
        {'ano_inicio_atuacao': 'dois mil'},
        {'video_url': 'https://www.instagram.com/reel/abc'},
        {'video_url': ['https://youtu.be/dQw4w9WgXcQ']},
        {'formacao': 'ab'},
        {'formacao': 'x' * 1001},
        {'campo_inventado': 1},
    ):
        r = profissional.patch('/api/profissionais/me', json=corpo)
        assert r.status_code == 400 and r.get_json()['error'], (corpo, r.status_code, r.get_json())
    # Erro nao altera nada
    assert anonimo.get(f'/api/profissionais/{PROFISSIONAL}').get_json()['profissionais'] == detalhe

    # null, lista vazia ou texto vazio limpam
    r = profissional.patch('/api/profissionais/me', json={'formacao': None, 'ano_inicio_atuacao': None,
                                                         'idiomas': [], 'areas_atuacao': '', 'video_url': ' '})
    assert r.status_code == 200, r.get_json()
    limpo = anonimo.get(f'/api/profissionais/{PROFISSIONAL}').get_json()['profissionais']
    assert (limpo['formacao'], limpo['ano_inicio_atuacao'], limpo['anos_experiencia'], limpo['idiomas'],
            limpo['areas_atuacao'], limpo['video_url']) == (None, None, None, [], [], None), limpo

    # 3. Cadastro multipart: chave repetida para lista, CSV e campos opcionais ausentes
    email = f'teste.perfil.{random.randint(0, 10 ** 9)}@exemplo.com'
    formulario = {
        'nome': 'Teste Perfil', 'email': email, 'telefone': '(11) 98888-7777', 'cpf': cpf_valido(),
        'senha': 'Senha@123', 'confirmar_senha': 'Senha@123', 'especialidade': 'Psicologia',
        'crp': '06/123456', 'descricao': 'Atendimento de adultos e adolescentes.', 'valor': '150',
        'dias': 'Segunda', 'idiomas': ['Português', 'Inglês'], 'areas_atuacao': 'Luto, Trauma',
        'ano_inicio_atuacao': '2010', 'video_url': 'https://vimeo.com/76979871',
    }
    invalido = anonimo.post('/api/profissionais/', data={**formulario, 'video_url': 'https://tiktok.com/x'})
    assert invalido.status_code == 400, invalido.get_json()
    assert executar('SELECT 1 FROM USUARIO WHERE EMAIL = ?', (email,)) is None, 'cadastro invalido gravou usuario'

    r = anonimo.post('/api/profissionais/', data=formulario)
    assert r.status_code == 201, r.get_json()
    criado = r.get_json()
    novo_usuario = criado['usuario']['id_usuario']
    assert len(envios) == 1 and envios[0]['email'] == email, envios
    perfil = criado['profissional']
    assert perfil['idiomas'] == ['Português', 'Inglês'] and perfil['areas_atuacao'] == ['Luto', 'Trauma'], perfil
    assert perfil['anos_experiencia'] == date.today().year - 2010 and perfil['formacao'] is None, perfil
    assert perfil['video_url'] == 'https://player.vimeo.com/video/76979871', perfil
    gravado = executar(f'SELECT {COLUNAS} FROM PROFISSIONAL WHERE USUARIO_ID = ?', (novo_usuario,))
    assert gravado == (None, None, None, 2010, 'Português,Inglês', 'Luto,Trauma',
                       'https://player.vimeo.com/video/76979871'), gravado

    print('ok: perfil completo do profissional')
finally:
    executar(f'''UPDATE PROFISSIONAL SET {", ".join(c + " = ?" for c in COLUNAS.split(", "))}
        WHERE USUARIO_ID = ?''', (*original, PROFISSIONAL))
    if novo_usuario:
        executar('DELETE FROM USUARIO WHERE ID_USUARIO = ?', (novo_usuario,))
