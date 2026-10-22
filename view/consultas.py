from flask import Blueprint, jsonify, request
from services import consultas_service
from util.usuarios import profissional_autenticado, usuario_autenticado

cons_bp = Blueprint('consultas', __name__, url_prefix='/api/consultas')


@cons_bp.route('/', methods=['GET'])
@usuario_autenticado
def consultas(dados_usuario):
    resultados = consultas_service.listar(dados_usuario.get('id_usuario'), dados_usuario.get('usuario_role'))
    return jsonify({'message': 'Consultas obtidas com sucesso', 'consultas': resultados}), 200


@cons_bp.route('/', methods=['POST'])
@usuario_autenticado
def agendar_consulta(dados_usuario):
    sessao = consultas_service.agendar(dados_usuario.get('id_usuario'), dados_usuario.get('usuario_role'),
                                       request.get_json(silent=True))
    return jsonify({'message': 'Sessao criada com sucesso', 'sessao': sessao}), 201


@cons_bp.route('/<int:sessao_id>', methods=['PATCH'])
@profissional_autenticado
def atualizar_consulta(dados_usuario, sessao_id):
    sessao = consultas_service.atualizar(dados_usuario.get('id_usuario'), sessao_id, request.get_json(silent=True))
    return jsonify({'message': 'Sessao atualizada com sucesso', 'sessao': sessao})


@cons_bp.route('/<int:sessao_id>/cancelar', methods=['POST'])
@usuario_autenticado
def cancelar_consulta(dados_usuario, sessao_id):
    resultado = consultas_service.cancelar(dados_usuario.get('id_usuario'), dados_usuario.get('usuario_role'), sessao_id)
    return jsonify({'message': 'Consulta cancelada', **resultado})


@cons_bp.route('/<int:sessao_id>/avaliacao', methods=['POST'])
@usuario_autenticado
def avaliar_consulta(dados_usuario, sessao_id):
    avaliacao = consultas_service.avaliar(dados_usuario.get('id_usuario'), dados_usuario.get('usuario_role'),
                                          sessao_id, request.get_json(silent=True))
    return jsonify({'message': 'Sessao avaliada com sucesso', 'avaliacao': avaliacao}), 201
