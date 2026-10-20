from flask import Blueprint, jsonify, request
from services import admin_service
from util.usuarios import admin_autenticado

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


@admin_bp.route('/metricas', methods=['GET'])
@admin_autenticado
def metricas(dados_usuario):
    resposta = jsonify(admin_service.metricas(request.args.get('dias', '30')))
    resposta.headers['Cache-Control'] = 'private, no-store'
    return resposta


@admin_bp.route('/auditoria', methods=['GET'])
@admin_autenticado
def auditoria(dados_usuario):
    try:
        limite = int(request.args.get('limite', 50))
        antes = int(request.args.get('antes', 2147483647))
        usuario_id = int(request.args['usuario_id']) if request.args.get('usuario_id') else None
        if not 1 <= limite <= 200 or antes < 1:
            raise ValueError()
    except ValueError:
        return jsonify({'error': 'Paginacao ou usuario_id invalido'}), 400
    resposta = jsonify(admin_service.auditoria(limite, antes, usuario_id, request.args.get('acao') or None))
    resposta.headers['Cache-Control'] = 'private, no-store'
    return resposta
