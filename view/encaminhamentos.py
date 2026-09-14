from flask import Blueprint, jsonify, request
from util.usuarios import profissional_autenticado
from database.db import get_connection

encam_bp = Blueprint('encaminhamentos', __name__, url_prefix='/api/encaminhamentos')

@encam_bp.route('/', methods=['POST'])
@profissional_autenticado
def criar_encaminhamento(payload):
    cursor = None
    try:
        con = get_connection()
        cursor = con.cursor()

        data = request.get_json(silent=True)

        if data is None:
            return jsonify({ 'error': 'Formato inválido' }), 400

        id_usuario = data.get('id_usuario')
        motivo = data.get('motivo')
        id_cid = data.get('id_cid')

        if id_usuario is None or motivo is None:
            return jsonify({ 'error': 'id_usuario e motivo são obrigatórios' }), 400

        cursor.execute('SELECT 1 FROM usuario WHERE id_usuario = ?', (id_usuario,))
        tem_usuario = cursor.fetchone()

        if tem_usuario is None:
            return jsonify({ 'error': 'Usuário não encontrado' }), 404

        cursor.execute("""
        INSERT INTO ENCAMINHAMENTO(PACIENTE_ID, PSICOLOGO_ID, CID, MOTIVO, STATUS)
        VALUES(?, ?, ?, ?, ?) RETURNING *
        """, (id_usuario, payload.get('id_usuario'), id_cid or None, motivo, 'ATIVO'))

        encam_criado = cursor.fetchone()
        cols = [desc[0].lower() for desc in cursor.description]

        con.commit()

        return jsonify({
            'message': 'Encaminhamento criado com sucesso',
            'encaminhamento': dict(zip(cols, encam_criado))
        }), 201
    except Exception as e:
        if con is not None:
            con.rollback()
        print(f"[{__name__}]: {str(e)}")
        return jsonify({ 'message': 'Internal Server Error' }), 500
    finally:
        if cursor is not None:
            cursor.close()

@encam_bp.route('/', methods=['GET'])
@profissional_autenticado
def encaminhamentos(payload):
    cursor = None
    try:
        con = get_connection()
        cursor = con.cursor()

        cursor.execute('SELECT * FROM ENCAMINHAMENTO')
        rows = cursor.fetchall()

        cols = [desc[0].lower() for desc in cursor.description]
        res = [dict(zip(cols, row)) for row in rows]

        return jsonify({
            'message': 'Encaminhamentos obtidos com sucesso',
            'encaminhamentos': res
        }), 200
    except Exception as e:
        print(f"[{__name__}]: {str(e)}")
        return jsonify({ 'message': 'Internal Server Error' }), 500
    finally:
        if cursor is not None:
            cursor.close()