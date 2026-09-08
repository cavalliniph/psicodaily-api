from flask import Blueprint, jsonify
from database.db import get_connection

registros_bp = Blueprint('registros', __name__, url_prefix='/api/registros')

@registros_bp.route('/', methods=['GET'])
def registros():
    con = get_connection()
    cur = con.cursor()

    try:

        cur.execute('SELECT * FROM registro')
        resultados = cur.fetchall()
        columns = [col[0].lower() for col in cur.description]

        registros = [dict(zip(columns, row)) for row in resultados]

        return jsonify({ 'registros': registros })
    except Exception as e:
        print(f"erro ao contar registros: {str(e)}")
        return jsonify({ 'error': 'Internal Server Error' }), 500
