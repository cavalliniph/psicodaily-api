from flask import current_app, jsonify, request
from functools import wraps
import jwt

def usuario_autenticado(funcao):
    @wraps(funcao)
    def wrapper(*args, **kwargs):
        token = request.cookies.get("access_token")

        if not token:
            return jsonify({ "error": "Usuario nao autenticado" }), 401

        try:
            dados = jwt.decode(
                token,
                current_app.config["SECRET_KEY"],
                algorithms=["HS256"],
            )
        except jwt.ExpiredSignatureError:
            return jsonify({ "error": "Expired token" }), 401
        except jwt.InvalidTokenError:
            return jsonify({ "error": "Token invalido" }), 401

        return funcao(dados, *args, **kwargs)

    return wrapper

def profissional_autenticado(funcao):
    @wraps(funcao)
    def wrapper(*args, **kwargs):
        token = request.cookies.get("access_token")

        if not token:
            return jsonify({ "error": "Usuario nao autenticado" }), 401

        try:
            dados = jwt.decode(
                token,
                current_app.config["SECRET_KEY"],
                algorithms=["HS256"],
            )

            if dados.get('usuario_role') not in ['PSICOLOGO', 'PSIQUIATRA']:
                return jsonify({ "error": "Acesso negado" }), 403
        except jwt.ExpiredSignatureError:
            return jsonify({ "error": "Expired token" }), 401
        except jwt.InvalidTokenError:
            return jsonify({ "error": "Token invalido" }), 401

        return funcao(dados, *args, **kwargs)

    return wrapper