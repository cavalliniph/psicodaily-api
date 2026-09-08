from flask import Blueprint, jsonify
from database.db import get_connection

prof_bp = Blueprint('profissionais', __name__, url_prefix='/api/profissionais')

@prof_bp.route('/', methods=['GET'])
def profissionais():
	con = get_connection()
	cur = con.cursor()

	try:
		cur.execute("SELECT * FROM PROFISSIONAL p")
		resultados = cur.fetchall()
		columns = [desc[0].lower() for desc in cur.description]

		payload = [dict(zip(columns, row)) for row in resultados]

		return jsonify({ 'message': 'Profissionais obtidos com sucesso', 'profissionais': payload }), 200
	except Exception as e:
		print(f"[{__name__}]: {str(e)}")
		return jsonify({ 'error': 'Internal Server Error' }), 500
	finally:
		if cur is not None:
			cur.close()

@prof_bp.route('/<int:id>', metods=['GET'])
def profissional(id):
	con = get_connection()
	cur = con.cursor()

	try:
		cur.execute("SELECT * FROM PROFISSIONAL p WHERE usuario_id = ?", (id,))
		resultado = cur.fetchone()

		if resultado is None:
			return jsonify({ 'error': 'Profissional não encontrado' }), 404

		columns = [desc[0].lower() for desc in cur.description]
		payload = dict(zip(columns, resultado))

		return jsonify({ 'message': 'Profissionais obtidos com sucesso', 'profissionais': payload }), 200
	except Exception as e:
		print(f"[{__name__}]: {str(e)}")
		return jsonify({ 'error': 'Internal Server Error' }), 500
	finally:
		if cur is not None:
			cur.close()
