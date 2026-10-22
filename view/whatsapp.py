from flask import Blueprint, jsonify, request
from services import assistente_service, whatsapp_service

whatsapp_bp = Blueprint('whatsapp', __name__, url_prefix='/api/whatsapp')


@whatsapp_bp.route('/webhook', methods=['POST'])
def webhook():
    # Sem login: quem chama e o WAHA, provado pela assinatura HMAC do corpo
    if not whatsapp_service.assinatura_valida(request.get_data(), request.headers.get('X-Webhook-Hmac')):
        return jsonify({'error': 'Assinatura invalida'}), 401
    respondendo = assistente_service.receber_whatsapp(request.get_json(silent=True) or {})
    return jsonify({'ok': True, 'respondendo': respondendo})
