import jwt
from flask import Blueprint, jsonify, request

from extensions.websocket import sock
from services import chat_service
from services.auth_service import decodificar_token
from services.erros import ErroNegocio
from util.usuarios import origem_permitida, token_da_requisicao, usuario_autenticado

chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')


def _sem_cache(resposta):
    resposta.headers['Cache-Control'] = 'private, no-store'
    return resposta


@chat_bp.route('/', methods=['GET'])
@usuario_autenticado
def conversas(dados_usuario):
    return _sem_cache(jsonify({'conversas': chat_service.conversas(dados_usuario['id_usuario'], dados_usuario.get('usuario_role'))}))


@chat_bp.route('/<int:outro_id>', methods=['GET'])
@usuario_autenticado
def mensagens(dados_usuario, outro_id):
    try:
        limite = int(request.args.get('limite', 50))
        antes = int(request.args['antes']) if 'antes' in request.args else None
        depois = int(request.args['depois']) if 'depois' in request.args else None
        if not 1 <= limite <= 100 or (antes is not None and depois is not None):
            raise ValueError()
    except ValueError:
        return jsonify({'error': 'Use limite de 1 a 100 e no maximo um entre antes e depois'}), 400
    itens = chat_service.mensagens(dados_usuario['id_usuario'], dados_usuario.get('usuario_role'), outro_id,
                                   limite, antes, depois)
    return _sem_cache(jsonify({'mensagens': itens}))


@chat_bp.route('/<int:outro_id>', methods=['POST'])
@usuario_autenticado
def enviar(dados_usuario, outro_id):
    mensagem = chat_service.enviar(dados_usuario['id_usuario'], dados_usuario.get('usuario_role'), outro_id,
                                   request.get_json(silent=True))
    return jsonify({'mensagem': mensagem}), 201


@sock.route('/ws/chat')
def tempo_real(ws):
    """Recebe {"type": "mensagem", "paciente_id", "profissional_id", "mensagem"} de toda conversa do usuario."""
    token = token_da_requisicao()
    try:
        if not origem_permitida() or not token:
            raise ErroNegocio('Conexao recusada', 401)
        dados = decodificar_token(token)
        chat_service.manter_conexao(dados['id_usuario'], dados.get('usuario_role'), ws)
    except (ErroNegocio, jwt.InvalidTokenError):
        ws.close()
