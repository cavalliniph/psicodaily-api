from flask import Blueprint, Response, jsonify, request
from services import assinaturas_service
from util.usuarios import profissional_autenticado

assinaturas_bp = Blueprint('assinaturas', __name__, url_prefix='/api/assinaturas')


@assinaturas_bp.route('/planos', methods=['GET'])
def planos():
    return jsonify({'planos': assinaturas_service.planos()}), 200


@assinaturas_bp.route('/me', methods=['GET'])
@profissional_autenticado
def obter(dados_usuario):
    return jsonify({'assinatura': assinaturas_service.obter(dados_usuario['id_usuario'])}), 200


@assinaturas_bp.route('/me', methods=['POST'])
@profissional_autenticado
def assinar(dados_usuario):
    assinatura, cobranca = assinaturas_service.assinar(dados_usuario['id_usuario'], request.get_json(silent=True))
    return jsonify({'assinatura': assinatura, 'cobranca': cobranca}), 201 if cobranca else 200


@assinaturas_bp.route('/me/cancelar', methods=['POST'])
@profissional_autenticado
def cancelar(dados_usuario):
    return jsonify({'assinatura': assinaturas_service.cancelar(dados_usuario['id_usuario'])}), 200


@assinaturas_bp.route('/me/cobranca/<int:cobranca_id>/pdf', methods=['GET'])
@profissional_autenticado
def boleto_pdf(dados_usuario, cobranca_id):
    pdf = assinaturas_service.boleto_pdf(dados_usuario['id_usuario'], cobranca_id)
    return Response(pdf, mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename=boleto-assinatura-{cobranca_id}.pdf'})
