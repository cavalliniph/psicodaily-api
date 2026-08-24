import os
from functools import wraps

import jwt
from flask import Blueprint, current_app, jsonify, make_response, request, send_file


usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/api/usuarios")


def usuario_autenticado(funcao):
    @wraps(funcao)
    def wrapper(*args, **kwargs):
        token = request.cookies.get("access_token")

        if not token:
            return jsonify({"error": "Usuario nao autenticado"}), 401

        try:
            dados = jwt.decode(
                token,
                current_app.config["SECRET_KEY"],
                algorithms=["HS256"],
            )
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token invalido"}), 401

        return funcao(dados, *args, **kwargs)

    return wrapper


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
