from flask import Blueprint, jsonify, request
from services import pagamentos_service
from util.usuarios import usuario_autenticado

pagamentos_bp = Blueprint('pagamentos', __name__, url_prefix='/api/pagamentos')


@pagamentos_bp.route('/cobranca', methods=['POST'])
@usuario_autenticado
def criar_cobranca(payload):
    sessao_id = (request.get_json(silent=True) or {}).get('id_sessao')
    cobranca = pagamentos_service.criar_cobranca(payload.get('id_usuario'), payload.get('usuario_role'), sessao_id)
    return jsonify({
        'message': 'Cobranca Pix criada com sucesso',
        'cobranca': cobranca,
        'id_sessao': sessao_id,
    }), 201


@pagamentos_bp.route('/cobranca/<int:id_cobranca>', methods=['GET'])
@usuario_autenticado
def consultar_cobranca(payload, id_cobranca):
    return jsonify({'cobranca': pagamentos_service.consultar_cobranca(payload.get('id_usuario'), id_cobranca)}), 200


@pagamentos_bp.route('/financeiro', methods=['GET'])
@usuario_autenticado
def financeiro(payload):
    return jsonify(pagamentos_service.financeiro(payload.get('usuario_role'), request.args.get('dias', '30'))), 200
