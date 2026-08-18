import random
from flask import Blueprint, jsonify, make_response, request
from database.db import con
from funcao import gerar_token, criar_hash_senha, senha_correta, validar_senha

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/login', methods=['GET'])
def login():
	try:
		data = request.json
		
		email = data.get('email')
		senha = data.get('senha')

		if not email or not senha:
			return jsonify({ "error": "Email e senha são obrigatorios" }), 400

		cursor = con.cursor()
		cursor.execute("SELECT id_usuario, senha, ativo, usuario_role FROM usuario WHERE email = ?", (email,))
		usuario = cursor.fetchone()

		if not usuario:
			return jsonify({ "error": "Usuario nao encontrado" }), 404

		if not senha_correta(usuario[1], senha):
			return jsonify({ "error": "Senha incorreta" }), 401

		if not usuario[2]:
			return jsonify({ "error": "Usuario inativo" }), 403

		payload = {
			'id_usuario': usuario[0],
			'usuario_role': usuario[3]
		}

		token = gerar_token(payload)
		
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
		pfp = request.files.get('pfp')
		email = request.form.get('email')
		nome = request.form.get('nome')
		telefone = request.form.get('telefone')
		senha = request.form.get('senha')
		cpf = request.form.get('cpf')

		if not email or not telefone or not senha or not cpf:
			return jsonify({ "error": "Todos os campos sao obrigatorios" }), 400

		cursor = con.cursor()

		cursor.execute("SELECT * FROM usuario WHERE email = ?", (email,))
		usuario = cursor.fetchone()

		if usuario:
			return jsonify({ "error": "Usuario ja cadastrado" }), 400

		if not validar_senha(senha):
			return jsonify({ "error": "Senha nao atende aos requisitos" }), 400

		senha_hash = criar_hash_senha(senha)

		codigo = codigo = random.randint(100000, 999999)
		cursor.execute("INSERT INTO usuario (nome, email, telefone, senha, cpf, codigo, usuario_role) VALUES (?, ?, ?, ?, ?, ?, ?)",
				 (nome, email, telefone, senha_hash, cpf, codigo, 'PACIENTE'))

		con.commit()

		return jsonify({ "message": "Usuario cadastrado com sucesso" }), 201
	except Exception as e:
		print(f"houve um erro ao realizar o cadastro: {str(e)}")
		con.rollback()
		return jsonify({ "error": "Internal server error" }), 500