import random
from flask import Blueprint, jsonify, make_response, request
from database.db import con
from funcao import gerar_token, criar_hash_senha

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/login', methods=['GET'])
def login():
	try:
		data = request.json() # parseando
		
		email = str(data.get('email'))
		senha = str(data.get('senha'))

		if not email or not senha:
			return jsonify({ "error": "Email e senha são obrigatorios" }), 400

		cursor = con.cursor()
		cursor.execute("SELECT * FROM usuario WHERE email = ?", (email,))
		usuario = cursor.fetchone()

		print(usuario)

		if not usuario:
			return jsonify({ "error": "Usuario nao encontrado" }), 404

		token = gerar_token(usuario)
		
		if not token:
			raise RuntimeError("Erro ao gerar token")
		
		response = make_response({
			"message": "Usuario logado com sucesso",
		})

		response.set_cookie("access_token", token)

		return response
	except Exception as e:
		print(str(e))
		return jsonify({ "error": "Internal server error" }), 500

# cadastro de cliente comum
@auth_bp.route('/cadastro', methods=['POST'])
def cadastro():
	try:
		email = request.form.get('email')
		nome = request.form.get('nome')
		telefone = request.form.get('telefone')
		senha = request.form.get('senha')
		cpf = request.form.get('cpf')

		if not email or not telefone or not senha or not cpf:
			return jsonify({ "error": "Todos os campos sao obrigatorios" }), 400

		senha_hash = criar_hash_senha(senha)

		cursor = con.cursor()
		codigo = codigo = random.randint(100000, 999999)
		cursor.execute("INSERT INTO usuario (nome, email, telefone, senha, cpf, codigo, usuario_role) VALUES (?, ?, ?, ?, ?, ?, ?)",
				 (nome, email, telefone, senha_hash, cpf, codigo, 'PACIENTE'))

		return jsonify({ "message": "Usuario cadastrado com sucesso" }), 201
	except Exception as e:
		print(f"houve um erro ao realizar o cadastro: {str(e)}")
		return jsonify({ "error": "Internal server error" }), 500