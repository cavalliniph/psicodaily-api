from flask import Blueprint, jsonify, request
from services import assistente_service
from util.usuarios import usuario_autenticado

assistente_bp = Blueprint('assistente', __name__, url_prefix='/api/assistente')


@assistente_bp.route('/', methods=['POST'])
@usuario_autenticado
def conversar(dados_usuario):
    resultado = assistente_service.conversar(dados_usuario.get('id_usuario'), dados_usuario.get('usuario_role'),
                                             request.get_json(silent=True))
    return jsonify(resultado)
