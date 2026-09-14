from flask import Blueprint, jsonify, request
from database.db import get_connection
from funcao import decodificar_token
from jwt import ExpiredSignatureError, InvalidTokenError

cons_bp = Blueprint('consultas', __name__, url_prefix='/api/consultas')

@cons_bp.route('/', methods=['GET'])
def consultas():
    con = None
    cur = None

    try:
        con = get_connection()
        cur = con.cursor()

        cur.execute('SELECT * FROM sessao')
        query_res = cur.fetchall()

        cols = [col[0].lower() for col in cur.description]
        resultados = [dict(zip(cols, row)) for row in query_res]

        return jsonify({ 'message': resultados }), 200
    except Exception as e:
        print(f'[{__name__}]: {str(e)}')
        return jsonify({ 'message': 'Internal Server Error' }), 500
    finally:
        if cur is not None:
            cur.close()

@cons_bp.route('/', methods=['POST'])
def agendar_consulta():
    token = request.cookies.get('access_token')

    if not token:
        return jsonify({ 'error': 'Token de autenticação necessário' }), 401
    
    con = None
    cur = None

    try:
        decodificar_token(token)

        con = get_connection()
        cur = con.cursor()

        cur.execute('SELECT * FROM USUARIO')
        query_res = cur.fetchall()

        cols = [col[0].lower() for col in cur.description]
        resultados = [dict(zip(cols, row)) for row in query_res]

        return jsonify({ 'message': resultados }), 200
    except ExpiredSignatureError:
            return jsonify({ 'error': 'Expired token' }), 401
    except InvalidTokenError:
        return jsonify({ 'error': 'Invalid token' }), 401
    except Exception as e:
        print(f'[{__name__}]: {str(e)}')
        return jsonify({ 'message': 'Internal Server Error' }), 500
    finally:
        if cur is not None:
            cur.close()