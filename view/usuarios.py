from flask import Blueprint, jsonify, make_response, request
from services import usuarios_service
from util.usuarios import usuario_autenticado

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/api/usuarios")


def _sem_cache(resposta):
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@usuarios_bp.route("/me", methods=["GET"])
@usuario_autenticado
def usuario_atual(dados_usuario):
    return _sem_cache(jsonify({"usuario": usuarios_service.perfil(dados_usuario.get("id_usuario"))}))


@usuarios_bp.route("/me", methods=["PUT", "PATCH"])
@usuario_autenticado
def atualizar_usuario(dados_usuario):
    formulario = request.form if request.form else (request.get_json(silent=True) or {})
    usuarios_service.atualizar_perfil(dados_usuario.get("id_usuario"), formulario,
                                      request.files.get("imagem"), request.method == "PUT")
    return _sem_cache(jsonify({"message": "Perfil atualizado"}))


@usuarios_bp.route("/", methods=["GET"])
@usuario_autenticado
def listar_usuarios(dados_usuario):
    if dados_usuario.get("usuario_role") != "ADMIN":
        return jsonify({"error": "Acesso negado"}), 403
    return _sem_cache(jsonify({"usuarios": usuarios_service.listar()}))


@usuarios_bp.route("/logout", methods=["POST"])
def logout():
    resposta = make_response(jsonify({"message": "Logout realizado com sucesso"}))
    resposta.delete_cookie("access_token")
    return resposta


@usuarios_bp.route('/', methods=['POST'])
def cadastro():
    usuario = usuarios_service.cadastrar_paciente(request.form, request.files.get('imagem'))
    return jsonify({
        "message": "Usuario cadastrado com sucesso",
        "usuario": {
            "id_usuario": usuario["id_usuario"],
            "tipo_usuario": "PACIENTE"
        }
    }), 201
