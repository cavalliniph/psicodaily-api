from flask import Blueprint, jsonify, request
from services import prontuario_service
from util.usuarios import profissional_autenticado

prontuario_bp = Blueprint('prontuario', __name__, url_prefix='/api/prontuario')


@prontuario_bp.route('/<int:paciente_id>', methods=['GET'])
@profissional_autenticado
def prontuario(dados_usuario, paciente_id):
    profissional_id = dados_usuario.get('id_usuario')
    if not profissional_id:
        return jsonify({'error': 'Usuario nao autenticado'}), 401
    try:
        dias = int(request.args.get('dias', 30))
        antes = int(request.args.get('antes', 2147483647))
        if dias not in (7, 30, 90) or antes < 1:
            raise ValueError()
    except ValueError:
        return jsonify({'error': 'Periodo ou paginacao invalida'}), 400

    resposta = jsonify(prontuario_service.prontuario(profissional_id, paciente_id, dias, antes))
    resposta.headers['Cache-Control'] = 'private, no-store'
    return resposta
