from flask import Blueprint, jsonify, request
from services import notificacoes_service
from util.usuarios import usuario_autenticado

notificacoes_bp = Blueprint('notificacoes', __name__, url_prefix='/api/notificacoes')


@notificacoes_bp.route('/', methods=['GET'])
@usuario_autenticado
def listar(dados_usuario):
    try:
        limite = int(request.args.get('limite', 20))
        antes = int(request.args.get('antes', 2147483647))
        if not 1 <= limite <= 100 or antes < 1:
            raise ValueError()
    except ValueError:
        return jsonify({'error': 'Paginacao invalida'}), 400
    resposta = jsonify(notificacoes_service.listar(dados_usuario['id_usuario'], limite, antes))
    resposta.headers['Cache-Control'] = 'private, no-store'
    return resposta


@notificacoes_bp.route('/lidas', methods=['POST'])
@usuario_autenticado
def marcar_lidas(dados_usuario):
    total = notificacoes_service.marcar_lidas(dados_usuario['id_usuario'], request.get_json(silent=True) or {})
    return jsonify({'message': 'Notificacoes marcadas como lidas', 'atualizadas': total})
