from flask import Blueprint, jsonify
from services import dashboard_service
from util.usuarios import usuario_autenticado

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api/dashboard')


@dashboard_bp.route('/', methods=['GET'])
@usuario_autenticado
def montar(dados_usuario):
    resposta = jsonify(dashboard_service.montar(dados_usuario['id_usuario'], dados_usuario.get('usuario_role')))
    resposta.headers['Cache-Control'] = 'private, no-store'
    return resposta
