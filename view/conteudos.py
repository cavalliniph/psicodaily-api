from flask import Blueprint, jsonify, request
from services import conteudos_service
from util.usuarios import profissional_autenticado

conteudos_bp = Blueprint('conteudos', __name__, url_prefix='/api/conteudos')


@conteudos_bp.route('/', methods=['POST'])
@profissional_autenticado
def criar(dados_usuario):
    conteudo = conteudos_service.criar(dados_usuario['id_usuario'], request.get_json(silent=True))
    return jsonify({'conteudo': conteudo}), 201


@conteudos_bp.route('/<int:conteudo_id>', methods=['PATCH'])
@profissional_autenticado
def atualizar(dados_usuario, conteudo_id):
    conteudo = conteudos_service.atualizar(dados_usuario['id_usuario'], conteudo_id, request.get_json(silent=True))
    return jsonify({'conteudo': conteudo}), 200


@conteudos_bp.route('/<int:conteudo_id>', methods=['DELETE'])
@profissional_autenticado
def apagar(dados_usuario, conteudo_id):
    conteudos_service.apagar(dados_usuario['id_usuario'], conteudo_id)
    return jsonify({'message': 'Conteúdo removido'}), 200
