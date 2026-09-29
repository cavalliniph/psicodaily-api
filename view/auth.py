from funcao import enviar_email_codigo_async, gerar_token, criar_hash_senha, senha_correta, validar_senha
from flask import Blueprint, jsonify, make_response, request
from database.db import get_connection
from util.usuarios import usuario_autenticado
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

		cur.execute("SELECT id_usuario, senha, ativo, usuario_role, nome, email FROM usuario WHERE LOWER(email) = LOWER(?)", (email.strip(),))
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
				"tipo_usuario": usuario[3],
				"nome": usuario[4],
				"email": usuario[5]
			}
		})

		response.set_cookie(
			'access_token',
			token,
			path='/',
			httponly=True,
			secure=True,
			samesite="None",
		)

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
            return jsonify({
                "error": "Formato invalido"
            }), 400

        email = data.get('email')
        codigo = data.get('codigo')

        if not email or not codigo:
            return jsonify({
                "error": "Email e codigo sao obrigatorios"
            }), 400

        email = str(email).strip().lower()
        codigo = str(codigo).strip()

        print("EMAIL RECEBIDO:", email)
        print("CODIGO RECEBIDO:", codigo)

        cur.execute(
            """
            SELECT id_usuario, codigo
            FROM usuario
            WHERE LOWER(email) = ?
            """,
            (email,)
        )

        usuario = cur.fetchone()

        print("USUARIO ENCONTRADO:", usuario)

        if not usuario:
            return jsonify({
                "error": "Usuario nao encontrado"
            }), 404

        codigo_banco = usuario[1]

        print("CODIGO NO BANCO:", codigo_banco)

        if codigo_banco is None:
            return jsonify({
                "error": "Nenhum codigo de verificacao encontrado"
            }), 401

        codigo_banco = str(codigo_banco).strip()

        if codigo_banco != codigo:
            return jsonify({
                "error": "Codigo invalido"
            }), 401

        cur.execute(
		"""
		UPDATE usuario
		SET ativo = true,
			codigo = NULL
		WHERE id_usuario = ?
		""",
		(usuario[0],))

        con.commit()

        return jsonify({
            "message": "Email verificado com sucesso"
        }), 200
    except Exception as e:
        print(f"houve um erro ao verificar o codigo: {str(e)}")
        con.rollback()

        return jsonify({
            "error": "Internal server error"
        }), 500
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

		email = email.strip().lower()
		cur.execute("SELECT id_usuario, email, nome FROM usuario WHERE LOWER(email) = ?", (email,))
		usuario = cur.fetchone()

		if not usuario:
			return jsonify({ "error": "Usuario nao encontrado" }), 404

		codigo = f"{secrets.randbelow(1000000):06d}"
		cur.execute("UPDATE usuario SET codigo = ? WHERE id_usuario = ?", (codigo, usuario[0]))
		con.commit()

		enviar_email_codigo_async(usuario[1], usuario[2], codigo, "recuperacao")

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
		email = (data.get('email') or '').strip().lower()

		if not codigo or not nova_senha or not email:
			return jsonify({ "error": "Email, codigo e senha sao obrigatorios" }), 400

		if not validar_senha(nova_senha):
			return jsonify({ "error": "Senha nao atende aos requisitos" }), 400

		cur.execute("SELECT id_usuario FROM usuario WHERE LOWER(email) = ? AND codigo = ?", (email, codigo))
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
		if con is not None:
			con.close()

@auth_bp.route('/alterar_senha_logado', methods=['POST'])
@usuario_autenticado
def alterar_senha_logado(dados_usuario):
	con = None
	cur = None
	try:
		data = request.get_json(silent=True) or {}
		senha_atual = data.get('senha_atual')
		nova_senha = data.get('nova_senha')
		if not senha_atual or not nova_senha:
			return jsonify({"error": "Informe a senha atual e a nova senha"}), 400
		if not validar_senha(nova_senha):
			return jsonify({"error": "A nova senha deve ter 8 a 12 caracteres e incluir maiuscula, minuscula, numero e simbolo"}), 400
		con = get_connection()
		cur = con.cursor()
		cur.execute("SELECT SENHA FROM USUARIO WHERE ID_USUARIO = ? AND ATIVO = TRUE", (dados_usuario.get('id_usuario'),))
		usuario = cur.fetchone()
		if not usuario:
			return jsonify({"error": "Usuario indisponivel"}), 401
		if not senha_correta(usuario[0], senha_atual):
			return jsonify({"error": "Senha atual incorreta"}), 401
		cur.execute("UPDATE USUARIO SET SENHA = ? WHERE ID_USUARIO = ?", (criar_hash_senha(nova_senha), dados_usuario.get('id_usuario')))
		con.commit()
		return jsonify({"message": "Senha alterada com sucesso"})
	except Exception:
		if con is not None:
			con.rollback()
		return jsonify({"error": "Nao foi possivel alterar a senha"}), 500
	finally:
		if cur is not None:
			cur.close()
		if con is not None:
			con.close()

@auth_bp.route('/logout', methods=['POST'])
def logout():
	response = make_response(jsonify({ 'message': 'Logout realizado com sucesso' }), 200)
	response.delete_cookie('access_token')
	return response
