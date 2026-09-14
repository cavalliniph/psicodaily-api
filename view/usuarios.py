import os
from functools import wraps

import jwt
from database.db import get_connection
from funcao import criar_usuario_base, enviar_email_ativacao
from flask import Blueprint, current_app, jsonify, make_response, request, send_file
from util.usuarios import usuario_autenticado

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/api/usuarios")

@usuarios_bp.route("/me/avatar", methods=["GET"])
@usuario_autenticado
def avatar(dados_usuario):
    id_usuario = dados_usuario.get("id_usuario")
    caminho_imagem = os.path.join(
        current_app.config["UPLOAD_FOLDER"],
        "usuarios",
        f"{id_usuario}.jpg",
    )

    if not os.path.isfile(caminho_imagem):
        return jsonify({"error": "Imagem do usuario nao encontrada"}), 404

    return send_file(caminho_imagem, mimetype="image/jpeg")


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
