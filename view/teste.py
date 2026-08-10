from flask import Blueprint, jsonify, request

teste_bp = Blueprint('teste', __name__, url_prefix='/api')

@teste_bp.route('/')
def teste_index():
    return jsonify({ 'message': 'ok' }), 200