import os
from database.db import get_connection
from funcao import (criar_usuario_base, enviar_email_ativacao, obter_campo,
                    validar_cpf, validar_email, validar_nome, validar_telefone,
                    somente_digitos, validar_imagem_usuario, salvar_imagem_usuario)
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
        cur.execute("SELECT ID_USUARIO, NOME, EMAIL, USUARIO_ROLE, TELEFONE, CPF FROM USUARIO WHERE ID_USUARIO = ? AND ATIVO = TRUE", (dados_usuario.get("id_usuario"),))
        usuario = cur.fetchone()
        if usuario is None:
            return jsonify({"error": "Usuario indisponivel"}), 401
        resposta = jsonify({"usuario": {
            "id_usuario": usuario[0], "nome": usuario[1],
            "email": usuario[2], "tipo_usuario": usuario[3],
            "telefone": usuario[4], "cpf": usuario[5],
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


@usuarios_bp.route("/me", methods=["PUT", "PATCH"])
@usuario_autenticado
def atualizar_usuario(dados_usuario):
    con = cur = None
    try:
        con = get_connection()
        cur = con.cursor()
        usuario_id = dados_usuario.get("id_usuario")
        cur.execute("SELECT ATIVO, EMAIL, CPF FROM USUARIO WHERE ID_USUARIO = ?", (usuario_id,))
        usuario = cur.fetchone()
        if not usuario or not usuario[0]:
            return jsonify({"error": "Usuario indisponivel"}), 401
        email_atual = (usuario[1] or "").strip().lower()
        cpf_atual = somente_digitos(usuario[2] or "")

        formulario = request.form if request.form else (request.get_json(silent=True) or {})
        imagem = request.files.get("imagem")
        permitidos = {"nome", "email", "telefone", "cpf"}
        if not hasattr(formulario, "keys"):
            return jsonify({"error": "Formato de atualizacao invalido"}), 400
        if not set(formulario).issubset(permitidos):
            return jsonify({"error": "Campo de perfil invalido"}), 400
        atualizacoes = {}
        for campo in formulario:
            valor = obter_campo(formulario, campo)
            if campo == "email":
                valor = valor.lower()
                valido = validar_email(valor)
            elif campo == "nome":
                valido = validar_nome(valor)
            elif campo == "telefone":
                valido = validar_telefone(valor)
            else:
                valor = somente_digitos(valor)
                valido = validar_cpf(valor)
            if not valido:
                return jsonify({"error": f"{campo.capitalize()} invalido"}), 400
            atualizacoes[campo] = valor
        if request.method == "PUT" and set(atualizacoes) != permitidos:
            return jsonify({"error": "PUT exige nome, email, telefone e CPF"}), 400
        if not atualizacoes and not (imagem and imagem.filename):
            return jsonify({"error": "Informe um campo para atualizar"}), 400
        if not validar_imagem_usuario(imagem):
            return jsonify({"error": "Imagem deve ser um arquivo JPG ou JPEG"}), 400

        if "email" in atualizacoes and atualizacoes["email"] != email_atual:
            cur.execute("SELECT FIRST 1 1 FROM USUARIO WHERE LOWER(EMAIL) = ? AND ID_USUARIO <> ?", (atualizacoes["email"], usuario_id))
            if cur.fetchone():
                return jsonify({"error": "Email ja cadastrado"}), 409
        if "cpf" in atualizacoes and atualizacoes["cpf"] != cpf_atual:
            cur.execute("SELECT FIRST 1 1 FROM USUARIO WHERE CPF = ? AND ID_USUARIO <> ?", (atualizacoes["cpf"], usuario_id))
            if cur.fetchone():
                return jsonify({"error": "CPF ja cadastrado"}), 409

        colunas = {"nome": "NOME", "email": "EMAIL", "telefone": "TELEFONE", "cpf": "CPF"}
        if atualizacoes:
            definicoes = ", ".join(f"{colunas[campo]} = ?" for campo in atualizacoes)
            cur.execute(f"UPDATE USUARIO SET {definicoes} WHERE ID_USUARIO = ?",
                        (*atualizacoes.values(), usuario_id))
        if imagem and imagem.filename:
            salvar_imagem_usuario(imagem, usuario_id)
        con.commit()
        resposta = jsonify({"message": "Perfil atualizado"})
        resposta.headers["Cache-Control"] = "private, no-store"
        return resposta
    except Exception:
        if con is not None:
            con.rollback()
        current_app.logger.exception("Erro ao atualizar perfil")
        return jsonify({"error": "Nao foi possivel atualizar o perfil"}), 500
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
        usuario, erro = criar_usuario_base(cur, request.form, 'PACIENTE', exigir_confirmacao_senha=True)

        if erro:
            return erro

        if usuario is None:
            raise RuntimeError("Cadastro nao retornou os dados do usuario")

        con.commit()
        enviar_email_ativacao(usuario["email"], usuario["codigo"], usuario["nome"])

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
