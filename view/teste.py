from flask import Blueprint, jsonify

from database import db

teste_bp = Blueprint('teste', __name__, url_prefix='/api/auth')

@teste_bp.route('/')
def teste_index():
    db.conn()
    return jsonify({ 'message': 'ok' }), 200
