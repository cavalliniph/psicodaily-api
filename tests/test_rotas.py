# Precisa do Firebird no ar: python tests/test_rotas.py
# Caracterizacao das rotas (status + chaves) para a refatoracao view -> services.
# Usa o profissional 22 e os pacientes 23 e 25 do banco local; desfaz tudo o que cria.
import os
import sys
from datetime import datetime, timedelta

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


def checar(resposta, status, *chaves):
    corpo = resposta.get_json(silent=True) or {}
    assert resposta.status_code == status, (resposta.request.path, resposta.status_code, corpo)
    for chave in chaves:
        assert chave in corpo, (resposta.request.path, chave, corpo)
    return corpo


anonimo = app.test_client()
profissional = cliente(PROFISSIONAL, 'PSICOLOGO')
paciente = cliente(PACIENTE, 'PACIENTE')
outro = cliente(OUTRO_PACIENTE, 'PACIENTE')
amanha = (datetime.now() + timedelta(days=400)).replace(hour=10, minute=0, second=0, microsecond=0)
criados = {'SESSAO': [], 'REGISTRO': [], 'ENCAMINHAMENTO': []}

try:
    # auth
    checar(anonimo.post('/api/auth/login', json={}), 400, 'error')
    checar(anonimo.post('/api/auth/login', json={'email': 'naoexiste@x.com', 'senha': 'a'}), 404, 'error')
    checar(anonimo.post('/api/auth/verificar_codigo', json={}), 400, 'error')
    checar(anonimo.post('/api/auth/alterar_senha', json={}), 400, 'error')
    checar(anonimo.post('/api/auth/esqueci_senha', json={}), 400, 'error')
    checar(paciente.post('/api/auth/alterar_senha_logado', json={}), 400, 'error')
    checar(anonimo.post('/api/auth/alterar_senha_logado', json={}), 401, 'error')
    checar(anonimo.post('/api/auth/logout'), 200, 'message')

    # usuarios
    checar(anonimo.get('/api/usuarios/me'), 401, 'error')
    me = checar(paciente.get('/api/usuarios/me'), 200, 'usuario')['usuario']
    for chave in ('id_usuario', 'nome', 'email', 'tipo_usuario', 'telefone', 'cpf', 'foto_url'):
        assert chave in me, chave
    checar(paciente.patch('/api/usuarios/me', json={'role': 'ADMIN'}), 400, 'error')
    checar(paciente.patch('/api/usuarios/me', json={'nome': '1'}), 400, 'error')
    checar(paciente.patch('/api/usuarios/me', json={'nome': me['nome']}), 200, 'message')
    checar(paciente.get('/api/usuarios/'), 403, 'error')
    checar(anonimo.post('/api/usuarios/', data={}), 400, 'error')
    checar(anonimo.post('/api/usuarios/logout'), 200, 'message')

    # profissionais
    lista = checar(anonimo.get('/api/profissionais/'), 200, 'page', 'page_size', 'total', 'total_pages', 'profissionais')
    assert lista['profissionais'], lista
    checar(anonimo.get('/api/profissionais/?page=0'), 400, 'error')
    checar(anonimo.get('/api/profissionais/?especialidade=x'), 400, 'error')
    checar(anonimo.get(f'/api/profissionais/{PROFISSIONAL}'), 200, 'profissionais')
    checar(anonimo.get('/api/profissionais/999999'), 404, 'error')
    checar(anonimo.post('/api/profissionais/', data={}), 400, 'error')
    checar(paciente.patch('/api/profissionais/me', json={'descricao': 'x' * 20}), 403, 'error')
    checar(profissional.patch('/api/profissionais/me', json={'foo': 1}), 400, 'error')

    # registros
    checar(profissional.get('/api/registros/'), 403, 'error')
    checar(paciente.get('/api/registros/?limite=0'), 400, 'error')
    checar(paciente.get('/api/registros/'), 200, 'registros', 'proximo_cursor')
    checar(paciente.post('/api/registros/', json={'humor': 'X'}), 400, 'error')
    checar(profissional.get('/api/registros/evolucao'), 403, 'error')
    checar(paciente.get('/api/registros/evolucao?dias=5'), 400, 'error')
    checar(paciente.get('/api/registros/evolucao?dias=x'), 400, 'error')
    hoje = datetime.now().date().isoformat()

    def humor_de_hoje():
        corpo = checar(paciente.get('/api/registros/evolucao?dias=7'), 200, 'dias', 'resumo', 'evolucaoHumor')
        dia = next((d for d in corpo['evolucaoHumor'] if d['data'] == hoje), {'valor': 0, 'quantidade': 0})
        return corpo['resumo']['totalRegistros'], dia['valor'] * dia['quantidade'], dia['quantidade']

    total_antes, soma_antes, qtd_antes = humor_de_hoje()
    registro = checar(paciente.post('/api/registros/', json={'humor': 'BOM', 'qualidade_sono': 'BOA'}), 201, 'registro')['registro']
    criados['REGISTRO'].append(registro['registro_id'])
    assert registro['usuario_id'] == PACIENTE and registro['humor'] == 'BOM', registro
    ruim = checar(paciente.post('/api/registros/', json={'humor': 'RUIM', 'qualidade_sono': 'RUIM'}), 201, 'registro')['registro']
    criados['REGISTRO'].append(ruim['registro_id'])
    # BOM vale 4 e RUIM vale 2: a media do dia passa a incluir os dois
    total, soma, qtd = humor_de_hoje()
    assert (total, qtd) == (total_antes + 2, qtd_antes + 2), (total, qtd, total_antes, qtd_antes)
    assert abs(soma - (soma_antes + 6)) < 1e-9, (soma, soma_antes)

    # consultas
    checar(anonimo.get('/api/consultas/'), 401, 'error')
    checar(paciente.get('/api/consultas/'), 200, 'consultas')
    checar(paciente.post('/api/consultas/', json={}), 400, 'error')
    checar(paciente.post('/api/consultas/', json={'id_profissional': PROFISSIONAL,
                                                 'timestamp_inicio': 'x', 'timestamp_fim': 'y'}), 400, 'error')
    corpo = {'id_profissional': PROFISSIONAL, 'timestamp_inicio': amanha.isoformat(),
             'timestamp_fim': (amanha + timedelta(hours=1)).isoformat()}
    checar(profissional.post('/api/consultas/', json=corpo), 403, 'error')
    checar(paciente.post('/api/consultas/', json={**corpo, 'id_profissional': 999999}), 404, 'error')
    sessao = checar(paciente.post('/api/consultas/', json=corpo), 201, 'sessao')['sessao']
    criados['SESSAO'].append(sessao['sessao_id'])
    for chave in ('sessao_id', 'paciente_id', 'profissional_id', 'status', 'paciente_foto_url', 'profissional_foto_url'):
        assert chave in sessao, chave
    checar(outro.post('/api/consultas/', json=corpo), 409, 'error')
    sid = sessao['sessao_id']
    checar(paciente.patch(f'/api/consultas/{sid}', json={'status': 'CANCELADO'}), 403, 'error')
    checar(profissional.patch(f'/api/consultas/{sid}', json={'foo': 1}), 400, 'error')
    checar(profissional.patch(f'/api/consultas/{sid}', json={'status': 'REALIZADO'}), 409, 'error')
    atualizada = checar(profissional.patch(f'/api/consultas/{sid}', json={'link_reuniao': 'https://meet.x/a'}), 200, 'sessao')
    assert atualizada['sessao']['link_reuniao'] == 'https://meet.x/a', atualizada
    checar(profissional.patch('/api/consultas/999999', json={'link_reuniao': None}), 404, 'error')
    checar(profissional.post(f'/api/consultas/{sid}/avaliacao', json={'nota': 5}), 403, 'error')
    checar(paciente.post(f'/api/consultas/{sid}/avaliacao', json={'nota': 9}), 400, 'error')
    checar(paciente.post(f'/api/consultas/{sid}/avaliacao', json={'nota': 5}), 409, 'error')
    checar(outro.post(f'/api/consultas/{sid}/avaliacao', json={'nota': 5}), 404, 'error')

    # prontuario (vinculo vem da sessao criada acima)
    checar(paciente.get(f'/api/prontuario/{PACIENTE}'), 403, 'error')
    checar(profissional.get(f'/api/prontuario/{PACIENTE}?dias=5'), 400, 'error')
    checar(profissional.get(f'/api/prontuario/{OUTRO_PACIENTE}'), 403, 'error')
    pront = checar(profissional.get(f'/api/prontuario/{PACIENTE}'), 200, 'paciente', 'ultimaConsulta',
                   'resumo', 'evolucaoHumor', 'registros', 'proximo_cursor')
    assert any(r['registro_id'] == registro['registro_id'] for r in pront['registros']), pront
    # Paciente e profissional enxergam o mesmo calculo
    proprio = paciente.get('/api/registros/evolucao?dias=30').get_json()
    assert (proprio['resumo'], proprio['evolucaoHumor']) == (pront['resumo'], pront['evolucaoHumor']), (proprio, pront)

    # encaminhamentos
    checar(paciente.get('/api/encaminhamentos/'), 403, 'error')
    checar(profissional.get('/api/encaminhamentos/'), 200, 'encaminhamentos')
    checar(profissional.post('/api/encaminhamentos/', json={}), 400, 'error')
    checar(profissional.post('/api/encaminhamentos/', json={'id_usuario': 999999, 'motivo': 'x'}), 404, 'error')
    encam = checar(profissional.post('/api/encaminhamentos/', json={'id_usuario': PACIENTE, 'motivo': 'teste'}),
                   201, 'encaminhamento')['encaminhamento']
    criados['ENCAMINHAMENTO'].append(encam['encaminhamento_id'])

    # pagamentos (so os caminhos que nao chamam a Arkhe)
    checar(anonimo.post('/api/pagamentos/cobranca', json={}), 401, 'error')
    checar(profissional.post('/api/pagamentos/cobranca', json={}), 403, 'error')
    checar(paciente.post('/api/pagamentos/cobranca', json={}), 400, 'error')
    checar(paciente.post('/api/pagamentos/cobranca', json={'id_sessao': 999999}), 404, 'error')
    checar(paciente.get('/api/pagamentos/financeiro'), 403, 'error')
    checar(profissional.get('/api/pagamentos/financeiro?dias=2'), 400, 'error')
    checar(anonimo.get('/api/pagamentos/cobranca/1'), 401, 'error')

    print('ok: rotas caracterizadas')
finally:
    for tabela, ids in criados.items():
        coluna = {'SESSAO': 'SESSAO_ID', 'REGISTRO': 'REGISTRO_ID', 'ENCAMINHAMENTO': 'ENCAMINHAMENTO_ID'}[tabela]
        for id_ in ids:
            executar(f'DELETE FROM {tabela} WHERE {coluna} = ?', (id_,))
