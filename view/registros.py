from flask import Blueprint, jsonify

registros_bp = Blueprint('registros', __name__, url_prefix='/api/registros')

@registros_bp.route('/', methods=['GET'])
def registros():
    return jsonify({ 'messsage': 'Hello registros' })

