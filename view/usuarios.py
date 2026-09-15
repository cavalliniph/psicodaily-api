import os
from database.db import get_connection
from funcao import criar_usuario_base, enviar_email_ativacao
from flask import Blueprint, current_app, jsonify, make_response, request, send_file
from util.usuarios import usuario_autenticado

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/api/usuarios")


@usuarios_bp.route("/me", methods=["GET"])
@usuario_autenticado
def usuario_atual(dados_usuario):
    con = None
    cur = None
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute("SELECT ID_USUARIO, NOME, EMAIL, USUARIO_ROLE FROM USUARIO WHERE ID_USUARIO = ? AND ATIVO = TRUE", (dados_usuario.get("id_usuario"),))
        usuario = cur.fetchone()
        if usuario is None:
            return jsonify({"error": "Usuario indisponivel"}), 401
        resposta = jsonify({"usuario": {
            "id_usuario": usuario[0], "nome": usuario[1],
            "email": usuario[2], "tipo_usuario": usuario[3],
        }})
        resposta.headers["Cache-Control"] = "private, no-store"
        return resposta
    except Exception:
        current_app.logger.exception("Erro ao carregar usuario autenticado")
        return jsonify({"error": "Nao foi possivel carregar o perfil"}), 500
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()

@usuarios_bp.route("/me/avatar", methods=["GET"])
@usuario_autenticado
def avatar(dados_usuario):
    try:
        id_usuario = int(dados_usuario.get("id_usuario"))
    except (TypeError, ValueError):
        return jsonify({"error": "Usuario nao autenticado"}), 401
    if id_usuario < 1:
        return jsonify({"error": "Usuario nao autenticado"}), 401
    return servir_avatar(id_usuario)


def servir_avatar(id_usuario):
    caminho_imagem = os.path.join(
        current_app.config["UPLOAD_FOLDER"],
        "usuarios",
        f"{id_usuario}.jpg",
    )

    if not os.path.isfile(caminho_imagem):
        return jsonify({"error": "Imagem do usuario nao encontrada"}), 404

    resposta = send_file(caminho_imagem, mimetype="image/jpeg", conditional=False)
    resposta.headers["Cache-Control"] = "private, no-store"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta


@usuarios_bp.route("/<int:id_usuario>/avatar", methods=["GET"])
@usuario_autenticado
def avatar_usuario(dados_usuario, id_usuario):
    if id_usuario < 1:
        return jsonify({"error": "Imagem do usuario nao encontrada"}), 404
    if str(dados_usuario.get("id_usuario")) == str(id_usuario):
        return servir_avatar(id_usuario)

    con = None
    cur = None
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute("SELECT USUARIO_ROLE, ATIVO FROM USUARIO WHERE ID_USUARIO = ?", (id_usuario,))
        usuario = cur.fetchone()
        if usuario is None:
            return jsonify({"error": "Imagem do usuario nao encontrada"}), 404

        papel = dados_usuario.get("usuario_role")
        permitido = papel == "ADMIN" or (usuario[1] and usuario[0] in ("PSICOLOGO", "PSIQUIATRA"))
        if not permitido and papel in ("PSICOLOGO", "PSIQUIATRA") and usuario[0] == "PACIENTE":
            # O profissional pode ver as fotos dos pacientes presentes em suas consultas.
            cur.execute("""
                SELECT FIRST 1 1 FROM SESSAO
                WHERE PROFISSIONAL_ID = ? AND PACIENTE_ID = ?
            """, (dados_usuario.get("id_usuario"), id_usuario))
            permitido = cur.fetchone() is not None
        if not permitido:
            return jsonify({"error": "Imagem do usuario nao encontrada"}), 404
        return servir_avatar(id_usuario)
    except Exception:
        current_app.logger.exception("Erro ao carregar avatar do usuario")
        return jsonify({"error": "Nao foi possivel carregar a imagem"}), 500
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()


@usuarios_bp.route("/", methods=["GET"])
@usuario_autenticado
def listar_usuarios(dados_usuario):
    if dados_usuario.get("usuario_role") != "ADMIN":
        return jsonify({"error": "Acesso negado"}), 403
    con = None
    cur = None
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute("SELECT ID_USUARIO, NOME, EMAIL, USUARIO_ROLE FROM USUARIO ORDER BY NOME")
        usuarios = [
            {"id_usuario": linha[0], "nome": linha[1], "email": linha[2], "tipo": linha[3]}
            for linha in cur.fetchall()
        ]
        resposta = jsonify({"usuarios": usuarios})
        resposta.headers["Cache-Control"] = "private, no-store"
        return resposta
    except Exception:
        current_app.logger.exception("Erro ao listar usuarios")
        return jsonify({"error": "Nao foi possivel carregar os usuarios"}), 500
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()


@usuarios_bp.route("/logout", methods=["POST"])
def logout():
    resposta = make_response(jsonify({"message": "Logout realizado com sucesso"}))
    resposta.delete_cookie("access_token")
    return resposta


@usuarios_bp.route('/', methods=['POST'])
def cadastro():
    con = get_connection()
    cur = con.cursor()

    try:
        usuario, erro = criar_usuario_base(cur, request.form, 'PACIENTE')

        if erro:
            return erro

        if usuario is None:
            raise RuntimeError("Cadastro nao retornou os dados do usuario")

        con.commit()
        enviar_email_ativacao(usuario["email"], usuario["codigo"])

        return jsonify({
            "message": "Usuario cadastrado com sucesso",
            "usuario": {
                "id_usuario": usuario["id_usuario"],
                "tipo_usuario": "PACIENTE"
            }
        }), 201


    except Exception as e:
        print(f"houve um erro ao realizar o cadastro: {str(e)}")
        con.rollback()
        return jsonify({ "error": "Internal server error" }), 500
    finally:
        if cur is not None:
            cur.close()
