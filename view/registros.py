from flask import Blueprint, jsonify, request
from services import registros_service
from util.usuarios import usuario_autenticado

registros_bp = Blueprint('registros', __name__, url_prefix='/api/registros')


@registros_bp.route('/', methods=['GET', 'POST'])
@usuario_autenticado
def registros(dados_usuario):
    if dados_usuario.get('usuario_role') != 'PACIENTE' or not dados_usuario.get('id_usuario'):
        return jsonify({'error': 'Acesso exclusivo do paciente aos proprios registros'}), 403
    usuario_id = dados_usuario['id_usuario']
    if request.method == 'POST':
        registro = registros_service.criar(usuario_id, request.get_json(silent=True))
        resposta, status = jsonify({'registro': registro}), 201
    else:
        try:
            limite = int(request.args.get('limite', 20))
            antes = int(request.args.get('antes', 2147483647))
            if not 1 <= limite <= 100 or antes < 1:
                raise ValueError()
        except ValueError:
            return jsonify({'error': 'Paginacao invalida'}), 400
        resposta, status = jsonify(registros_service.listar(usuario_id, limite, antes)), 200
    resposta.headers['Cache-Control'] = 'private, no-store'
    return resposta, status
