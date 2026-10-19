from flask import Blueprint, jsonify, request
from services import profissionais_service
from util.usuarios import profissional_autenticado

prof_bp = Blueprint('profissionais', __name__, url_prefix='/api/profissionais')


@prof_bp.route('/', methods=['GET'])
def profissionais():
	return jsonify({'message': 'Profissionais obtidos com sucesso', **profissionais_service.buscar(request.args)}), 200


@prof_bp.route('/<int:id>', methods=['GET'])
def profissional(id):
	return jsonify({'message': 'Profissionais obtidos com sucesso', 'profissionais': profissionais_service.detalhe(id)}), 200


@prof_bp.route('/', methods=['POST'])
def cadastro_profissional():
	cadastro = profissionais_service.cadastrar(request.form, request.files.get('imagem'))
	return jsonify({"message": "Profissional cadastrado com sucesso", **cadastro}), 201


@prof_bp.route('/me', methods=['PATCH'])
@profissional_autenticado
def atualizar_profissional(dados_usuario):
	profissionais_service.atualizar(dados_usuario.get('id_usuario'), request.get_json(silent=True) or {})
	return jsonify({'message': 'Perfil profissional atualizado'}), 200
