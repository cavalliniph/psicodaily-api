from flask import Blueprint, jsonify
from database.db import con

agendamento_bp = Blueprint('agendamento', __name__, url_prefix='/api/agendamento')

# TODO
# - obter todos os agendamentos 

@agendamento_bp.route('/', methods=['GET'])
def agendamentos():
    cur = con.cursor()

    try:
        cur.execute('SELECT * FROM usuario')
        resultados = cur.fetchall()
        columns = [col[0].lower() for col in cur.description]

        usuarios = [dict(zip(columns, row)) for row in resultados]
        # esse endpoint (por enquanto) é pra puro teste
        # TODO tabela de agendamento/sessao precisa ser criada
        return jsonify({ 'usuarios': usuarios }), 200
    except Exception as e:
        print(f"erro ao obter agendamentos {str(e)}")
        return jsonify({ 'error': 'Houve um erro ao obter agendamentos' })
    finally:
        if cur:
            cur.close()


