from funcao import enviar_email, gerar_token, criar_hash_senha, senha_correta, validar_senha
from flask import Blueprint, jsonify, make_response, request
from database.db import get_connection
import threading
import secrets

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/login', methods=['POST'])
def login():
	con = get_connection()
	cur = con.cursor()

	try:
		data = request.get_json(silent=True) or {}

		email = data.get('email')
		senha = data.get('senha')

		if not email or not senha:
			return jsonify({ "error": "Email e senha sao obrigatorios" }), 400

		cur.execute("SELECT id_usuario, senha, ativo, usuario_role FROM usuario WHERE email = ?", (email,))
		usuario = cur.fetchone()

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
			"usuario": {
				"id_usuario": usuario[0],
				"tipo_usuario": usuario[3]
			}
		})

		response.set_cookie("access_token", token)

		return response
	except Exception as e:
		print(str(e))
		return jsonify({ "error": "Internal server error" }), 500
	finally:
		if cur is not None:
			cur.close()

@auth_bp.route('/verificar_codigo', methods=['POST'])
def verificar_codigo():
	con = get_connection()
	cur = con.cursor()

	try:
		data = request.get_json(silent=True) or {}

		if not data:
			return jsonify({ "error": "Formato invalido" }), 400

		email = data.get('email')
		codigo = data.get('codigo')

		if not email or not codigo:
			return jsonify({ "error": "Email e codigo sao obrigatorios" }), 400

		cur.execute("SELECT id_usuario, codigo FROM usuario WHERE email = ?", (email,))
		usuario = cur.fetchone()

		if not usuario:
			return jsonify({ "error": "Usuario nao encontrado" }), 404

		if usuario[1] != codigo:
			return jsonify({ "error": "Codigo invalido" }), 401

		cur.execute("UPDATE usuario SET ativo = true, codigo = NULL WHERE id_usuario = ?", (usuario[0],))
		con.commit()

		return jsonify({ "message": "Email verificado com sucesso" }), 200
	except Exception as e:
		print(f"houve um erro ao verificar o codigo: {str(e)}")
		con.rollback()
		return jsonify({ "error": "Internal server error" }), 500
	finally:
		if cur is not None:
			cur.close()

@auth_bp.route('/esqueci_senha', methods=['POST'])
def esqueci_senha():
	con = get_connection()
	cur = con.cursor()

	try:
		data = request.get_json(silent=True) or {}
		email = data.get('email')

		if not email:
			return jsonify({ "error": "Email e obrigatorio" }), 400

		cur.execute("SELECT id_usuario FROM usuario WHERE email = ?", (email,))
		usuario = cur.fetchone()

		if not usuario:
			return jsonify({ "error": "Usuario nao encontrado" }), 404

		codigo = f"{secrets.randbelow(1000000):06d}"
		cur.execute("UPDATE usuario SET codigo = ? WHERE id_usuario = ?", (codigo, usuario[0]))
		con.commit()

		threading.Thread(
			target=enviar_email,
			args=(email, "Recuperacao de senha", f"Seu codigo para alterar a senha e: {codigo}")
		).start()

		return jsonify({ "message": "Codigo enviado para o e-mail" }), 200
	except Exception as e:
		print(f"houve um erro ao solicitar recuperacao: {str(e)}")
		con.rollback()
		return jsonify({ "error": "Internal server error" }), 500
	finally:
		if cur is not None:
			cur.close()

@auth_bp.route('/alterar_senha', methods=['POST'])
def alterar_senha():
	con = get_connection()
	cur = con.cursor()

	try:
		data = request.get_json(silent=True) or {}
		codigo = data.get('codigo')
		nova_senha = data.get('senha')

		if not codigo or not nova_senha:
			return jsonify({ "error": "Codigo e senha sao obrigatorios" }), 400

		if not validar_senha(nova_senha):
			return jsonify({ "error": "Senha nao atende aos requisitos" }), 400

		cur.execute("SELECT id_usuario FROM usuario WHERE codigo = ?", (codigo,))
		usuario = cur.fetchone()

		if not usuario:
			return jsonify({ "error": "Codigo invalido" }), 401

		cur.execute(
			"UPDATE usuario SET senha = ?, codigo = NULL WHERE id_usuario = ?",
			(criar_hash_senha(nova_senha), usuario[0])
		)
		con.commit()

		return jsonify({ "message": "Senha alterada com sucesso" }), 200
	except Exception as e:
		print(f"houve um erro ao alterar a senha: {str(e)}")
		con.rollback()
		return jsonify({ "error": "Internal server error" }), 500
	finally:
		if cur is not None:
			cur.close()
