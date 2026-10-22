from flask import Blueprint, Response, jsonify, request
from services import financeiro_service, pagamentos_service
from util.usuarios import usuario_autenticado

pagamentos_bp = Blueprint('pagamentos', __name__, url_prefix='/api/pagamentos')


@pagamentos_bp.route('/cobranca', methods=['POST'])
@usuario_autenticado
def criar_cobranca(payload):
    dados = request.get_json(silent=True)
    cobranca = pagamentos_service.criar_cobranca(payload.get('id_usuario'), payload.get('usuario_role'), dados)
    return jsonify({
        'message': 'Pagamento aprovado' if cobranca['metodo'] == 'CARTAO' else 'Cobranca criada com sucesso',
        'cobranca': cobranca,
        'id_sessao': dados['id_sessao'],
    }), 201


@pagamentos_bp.route('/cobranca/<int:id_cobranca>', methods=['GET'])
@usuario_autenticado
def consultar_cobranca(payload, id_cobranca):
    return jsonify({'cobranca': pagamentos_service.consultar_cobranca(payload.get('id_usuario'), id_cobranca)}), 200


@pagamentos_bp.route('/cobranca/<int:id_cobranca>/pdf', methods=['GET'])
@usuario_autenticado
def boleto_pdf(payload, id_cobranca):
    pdf = pagamentos_service.boleto_pdf(payload.get('id_usuario'), id_cobranca)
    return Response(pdf, mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename=boleto-{id_cobranca}.pdf'})


@pagamentos_bp.route('/ganhos', methods=['GET'])
@usuario_autenticado
def ganhos(payload):
    return jsonify(financeiro_service.ganhos(payload.get('id_usuario'), payload.get('usuario_role'),
                                             request.args.get('dias', '30'))), 200


@pagamentos_bp.route('/financeiro', methods=['GET'])
@usuario_autenticado
def financeiro(payload):
    return jsonify(pagamentos_service.financeiro(payload.get('usuario_role'), request.args.get('dias', '30'))), 200
