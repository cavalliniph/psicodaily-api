from flask import Blueprint, jsonify, request
from services import encaminhamentos_service
from util.usuarios import profissional_autenticado

encam_bp = Blueprint('encaminhamentos', __name__, url_prefix='/api/encaminhamentos')


@encam_bp.route('/', methods=['POST'])
@profissional_autenticado
def criar_encaminhamento(payload):
    encaminhamento = encaminhamentos_service.criar(payload.get('id_usuario'), request.get_json(silent=True))
    return jsonify({
        'message': 'Encaminhamento criado com sucesso',
        'encaminhamento': encaminhamento
    }), 201


@encam_bp.route('/', methods=['GET'])
@profissional_autenticado
def encaminhamentos(payload):
    return jsonify({
        'message': 'Encaminhamentos obtidos com sucesso',
        'encaminhamentos': encaminhamentos_service.listar(payload['id_usuario'])
    }), 200
