from flask import Blueprint, jsonify
from database.db import con
from funcao import gerar_token

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/login', methods=['GET'])
def login():
	try:
		return jsonify({ "message": gerar_token({ "hello": "world" }) })
	except Exception as e:
		return jsonify({ "error": "Internal server error" }), 500


def cadastro():
	return jsonify({}) 