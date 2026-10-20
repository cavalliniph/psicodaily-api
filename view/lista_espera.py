from flask import Blueprint, jsonify, request
from services import lista_espera_service
from util.usuarios import usuario_autenticado

lista_espera_bp = Blueprint('lista_espera', __name__, url_prefix='/api/lista-espera')


@lista_espera_bp.route('/', methods=['GET'])
@usuario_autenticado
def listar(dados_usuario):
    resposta = jsonify({'lista_espera': lista_espera_service.listar(dados_usuario['id_usuario'], dados_usuario.get('usuario_role'))})
    resposta.headers['Cache-Control'] = 'private, no-store'
    return resposta


@lista_espera_bp.route('/', methods=['POST'])
@usuario_autenticado
def entrar(dados_usuario):
    entrada = lista_espera_service.entrar(dados_usuario['id_usuario'], dados_usuario.get('usuario_role'),
                                         request.get_json(silent=True))
    return jsonify({'message': 'Voce entrou na lista de espera', 'lista_espera': entrada}), 201


@lista_espera_bp.route('/<int:lista_espera_id>', methods=['DELETE'])
@usuario_autenticado
def sair(dados_usuario, lista_espera_id):
    lista_espera_service.sair(dados_usuario['id_usuario'], dados_usuario.get('usuario_role'), lista_espera_id)
    return jsonify({'message': 'Voce saiu da lista de espera'})
