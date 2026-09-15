from flask import Blueprint, current_app, jsonify, request
from database.db import get_connection
from util.usuarios import usuario_autenticado

registros_bp = Blueprint('registros', __name__, url_prefix='/api/registros')

DOMINIOS = {
    'humor': {'PESSIMO', 'RUIM', 'NEUTRO', 'BOM', 'EXCELENTE'},
    'qualidade_sono': {'RUIM', 'REGULAR', 'BOA', 'EXCELENTE'},
    'alimentacao': {'POUCA', 'DESREGULADA', 'ADEQUADA', 'EXCESSIVA'},
}
COLUNAS = ('registro_id', 'usuario_id', 'humor', 'qualidade_sono',
           'minutos_sono', 'alimentacao', 'exercicio_fisico', 'interacao',
           'anotacao', 'criado_em')


def serializar(linha):
    registro = dict(zip(COLUNAS, linha))
    if hasattr(registro['anotacao'], 'read'):
        registro['anotacao'] = registro['anotacao'].read()
    if registro['criado_em'] is not None:
        registro['criado_em'] = registro['criado_em'].isoformat()
    return registro


def validar(dados):
    if not isinstance(dados, dict):
        return 'Envie um objeto JSON'
    permitidos = set(COLUNAS) - {'registro_id', 'usuario_id', 'criado_em'}
    if set(dados) - permitidos:
        return 'Campos desconhecidos; usuario e data sao definidos pelo servidor'
    for campo, valores in DOMINIOS.items():
        valor = dados.get(campo)
        if campo == 'alimentacao' and valor is None:
            continue
        if not isinstance(valor, str) or valor not in valores:
            return f'Valor invalido para {campo}'
    for campo, limite in [('minutos_sono', 1440), ('interacao', 32767)]:
        valor = dados.get(campo)
        if valor is not None and (type(valor) is not int or not 0 <= valor <= limite):
            return f'{campo} deve ser inteiro entre 0 e {limite}'
    if type(dados.get('exercicio_fisico', False)) is not bool:
        return 'exercicio_fisico deve ser booleano'
    if not isinstance(dados.get('anotacao', ''), str) or len(dados.get('anotacao', '')) > 10000:
        return 'anotacao deve ter no maximo 10000 caracteres'
    return None


@registros_bp.route('/', methods=['GET', 'POST'])
@usuario_autenticado
def registros(dados_usuario):
    if dados_usuario.get('usuario_role') != 'PACIENTE' or not dados_usuario.get('id_usuario'):
        return jsonify({'error': 'Acesso exclusivo do paciente aos proprios registros'}), 403
    dados = request.get_json(silent=True) if request.method == 'POST' else None
    if request.method == 'POST':
        erro = validar(dados)
        if erro:
            return jsonify({'error': erro}), 400
    else:
        try:
            limite = int(request.args.get('limite', 20))
            antes = int(request.args.get('antes', 2147483647))
            if not 1 <= limite <= 100 or antes < 1:
                raise ValueError()
        except ValueError:
            return jsonify({'error': 'Paginacao invalida'}), 400
    con = None
    cur = None
    try:
        con = get_connection()
        cur = con.cursor()
        usuario_id = dados_usuario['id_usuario']
        colunas = ', '.join(COLUNAS)
        if request.method == 'GET':
            cur.execute(f"""SELECT FIRST ? {colunas} FROM REGISTRO
                WHERE USUARIO_ID = ? AND REGISTRO_ID < ?
                ORDER BY REGISTRO_ID DESC""", (limite + 1, usuario_id, antes))
            linhas = cur.fetchall()
            itens = [serializar(linha) for linha in linhas[:limite]]
            resposta = jsonify({'registros': itens, 'proximo_cursor': itens[-1]['registro_id'] if len(linhas) > limite else None})
            resposta.headers['Cache-Control'] = 'private, no-store'
            return resposta
        cur.execute(f"""INSERT INTO REGISTRO
            (USUARIO_ID, HUMOR, QUALIDADE_SONO, MINUTOS_SONO, ALIMENTACAO,
             EXERCICIO_FISICO, INTERACAO, ANOTACAO)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING {colunas}""",
            (usuario_id, dados['humor'], dados['qualidade_sono'], dados.get('minutos_sono'),
             dados.get('alimentacao'), dados.get('exercicio_fisico', False),
             dados.get('interacao'), dados.get('anotacao', '')))
        registro = serializar(cur.fetchone())
        con.commit()
        resposta = jsonify({'registro': registro})
        resposta.headers['Cache-Control'] = 'private, no-store'
        return resposta, 201
    except Exception:
        if con is not None:
            con.rollback()
        current_app.logger.exception('Erro ao acessar registros')
        return jsonify({'error': 'Nao foi possivel acessar os registros'}), 500
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()
