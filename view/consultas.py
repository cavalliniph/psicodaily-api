from flask import Blueprint, jsonify
from database.db import get_connection

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
