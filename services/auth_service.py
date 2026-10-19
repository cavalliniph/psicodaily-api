import secrets

import jwt
from flask_bcrypt import check_password_hash, generate_password_hash

import config
from database.db import transacao
from funcao import validar_senha
from services import email_service
from services.erros import ErroNegocio
from services.upload_service import upload_service


def gerar_token(payload):
    return jwt.encode(payload, config.SECRET_KEY, algorithm='HS256')


def decodificar_token(token):
    return jwt.decode(token, config.SECRET_KEY, algorithms=['HS256'])


def senha_correta(senha_hash, senha):
    return check_password_hash(senha_hash, senha)


def criar_hash_senha(senha):
    return generate_password_hash(senha)


def gerar_codigo():
    return f"{secrets.randbelow(1000000):06d}"


def autenticar(email, senha):
    """Confere email/senha e devolve (usuario, token)."""
    if not email or not senha:
        raise ErroNegocio("Email e senha sao obrigatorios")

    with transacao() as cur:
        cur.execute("SELECT id_usuario, senha, ativo, usuario_role, nome, email FROM usuario WHERE LOWER(email) = LOWER(?)",
                    (email.strip(),))
        usuario = cur.fetchone()

    if not usuario:
        raise ErroNegocio("Usuario nao encontrado", 404)
    if not senha_correta(usuario[1], senha):
        raise ErroNegocio("Senha incorreta", 401)
    if not usuario[2]:
        raise ErroNegocio("Usuario inativo", 403)

    token = gerar_token({'id_usuario': usuario[0], 'usuario_role': usuario[3]})
    return {
        "id_usuario": usuario[0],
        "tipo_usuario": usuario[3],
        "nome": usuario[4],
        "email": usuario[5],
        "foto_url": upload_service.url_foto_usuario(usuario[0]),
    }, token


def verificar_codigo(email, codigo):
    if not email or not codigo:
        raise ErroNegocio("Email e codigo sao obrigatorios")
    email = str(email).strip().lower()
    codigo = str(codigo).strip()

    with transacao() as cur:
        cur.execute("SELECT id_usuario, codigo FROM usuario WHERE LOWER(email) = ?", (email,))
        usuario = cur.fetchone()
        if not usuario:
            raise ErroNegocio("Usuario nao encontrado", 404)
        if usuario[1] is None:
            raise ErroNegocio("Nenhum codigo de verificacao encontrado", 401)
        if str(usuario[1]).strip() != codigo:
            raise ErroNegocio("Codigo invalido", 401)
        cur.execute("UPDATE usuario SET ativo = true, codigo = NULL WHERE id_usuario = ?", (usuario[0],))


def esqueci_senha(email):
    if not email:
        raise ErroNegocio("Email e obrigatorio")

    with transacao() as cur:
        cur.execute("SELECT id_usuario, email, nome FROM usuario WHERE LOWER(email) = ?", (email.strip().lower(),))
        usuario = cur.fetchone()
        if not usuario:
            raise ErroNegocio("Usuario nao encontrado", 404)
        codigo = gerar_codigo()
        cur.execute("UPDATE usuario SET codigo = ? WHERE id_usuario = ?", (codigo, usuario[0]))

    email_service.enviar_email_codigo_async(usuario[1], usuario[2], codigo, "recuperacao")


def alterar_senha(email, codigo, nova_senha):
    email = (email or '').strip().lower()
    if not codigo or not nova_senha or not email:
        raise ErroNegocio("Email, codigo e senha sao obrigatorios")
    if not validar_senha(nova_senha):
        raise ErroNegocio("Senha nao atende aos requisitos")

    with transacao() as cur:
        cur.execute("SELECT id_usuario FROM usuario WHERE LOWER(email) = ? AND codigo = ?", (email, codigo))
        usuario = cur.fetchone()
        if not usuario:
            raise ErroNegocio("Codigo invalido", 401)
        cur.execute("UPDATE usuario SET senha = ?, codigo = NULL WHERE id_usuario = ?",
                    (criar_hash_senha(nova_senha), usuario[0]))


def alterar_senha_logado(id_usuario, senha_atual, nova_senha):
    if not senha_atual or not nova_senha:
        raise ErroNegocio("Informe a senha atual e a nova senha")
    if not validar_senha(nova_senha):
        raise ErroNegocio("A nova senha deve ter 8 a 12 caracteres e incluir maiuscula, minuscula, numero e simbolo")

    with transacao() as cur:
        cur.execute("SELECT SENHA FROM USUARIO WHERE ID_USUARIO = ? AND ATIVO = TRUE", (id_usuario,))
        usuario = cur.fetchone()
        if not usuario:
            raise ErroNegocio("Usuario indisponivel", 401)
        if not senha_correta(usuario[0], senha_atual):
            raise ErroNegocio("Senha atual incorreta", 401)
        cur.execute("UPDATE USUARIO SET SENHA = ? WHERE ID_USUARIO = ?", (criar_hash_senha(nova_senha), id_usuario))
