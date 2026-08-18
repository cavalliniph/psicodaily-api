from flask import Blueprint, jsonify, make_response
from database.db import con
from funcao import gerar_token

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/login', methods=['GET'])
def login():
	try:
		response = make_response({
			"foo": "bar"
		})

		token = gerar_token({ "foo": "sure" })

		if not token:
			return jsonify({ "foo": "bar" })

		response.set_cookie("access_token", token)

		return response
	except Exception as e:
		return jsonify({ "error": "Internal server error" }), 500


def cadastro():
	return jsonify({}) 