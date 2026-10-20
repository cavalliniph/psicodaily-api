from flask import jsonify, request
from functools import wraps

from config import ORIGENS_FRONT
from services.auth_service import usuario_do_token


def origem_permitida():
    # O handshake WS nao passa pelo CORS e leva o cookie: sem isso, qualquer site aberto no navegador entra no WS (S7).
    # Sem Origin = cliente fora do navegador (app mobile), que precisa do proprio token.
    origem = request.headers.get("Origin")
    return origem is None or origem in ORIGENS_FRONT


def token_da_requisicao():
    # Web manda o cookie; o app mobile manda "Authorization: Bearer <token>".
    cabecalho = request.headers.get("Authorization", "")
    if cabecalho.startswith("Bearer "):
        return cabecalho[7:]
    return request.cookies.get("access_token")


def usuario_autenticado(funcao):
    @wraps(funcao)
    def wrapper(*args, **kwargs):
        token = token_da_requisicao()

        if not token:
            return jsonify({ "error": "Usuario nao autenticado" }), 401

        # Token vencido, invalido ou anterior a troca de senha: ErroNegocio 401
        return funcao(usuario_do_token(token), *args, **kwargs)

    return wrapper


def profissional_autenticado(funcao):
    @usuario_autenticado
    @wraps(funcao)
    def wrapper(dados, *args, **kwargs):
        if dados.get('usuario_role') not in ['PSICOLOGO', 'PSIQUIATRA']:
            return jsonify({ "error": "Acesso negado" }), 403
        return funcao(dados, *args, **kwargs)

    return wrapper


def admin_autenticado(funcao):
    @usuario_autenticado
    @wraps(funcao)
    def wrapper(dados, *args, **kwargs):
        if dados.get('usuario_role') != 'ADMIN':
            return jsonify({ "error": "Acesso negado" }), 403
        return funcao(dados, *args, **kwargs)

    return wrapper
