from flask import Blueprint, jsonify, request
from database.db import get_connection
from funcao import decodificar_token
from jwt import ExpiredSignatureError, InvalidTokenError
from util.datas import parsear_data

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

        return jsonify({ 'message': 'Consultas obtidas com sucesso', 'consultas': resultados }), 200
    except Exception as e:
        print(f'[{__name__}]: {str(e)}')
        return jsonify({ 'message': 'Internal Server Error' }), 500
    finally:
        if cur is not None:
            cur.close()

"""
TODO:
- em agendar_consulta, precisa criar 'conversa' caso não exista e incluir na consulta
- precisa consultar existencia de 'encaminhamento' a partir de id_usuario e id profissional
- validar colisões de data
- criar wrapper de autenticação pra evitar boilerplate
"""

@cons_bp.route('/', methods=['POST'])
def agendar_consulta():
    token = request.cookies.get('access_token')

    if not token:
        return jsonify({ 'error': 'Token de autenticação necessário' }), 401
    
    con = None
    cur = None

    try:
        payload = decodificar_token(token)

        data = request.get_json(silent=True)
        
        if not data:
            return jsonify({ "error": "Formato invalido" }), 400

        id_profissional = data.get('id_profissional')
        inicio = data.get('timestamp_inicio')
        fim = data.get('timestamp_fim')

        timestamp_inicio = parsear_data(inicio)
        timestamp_fim = parsear_data(fim)

        con = get_connection()
        cur = con.cursor()

        cur.execute('SELECT 1 FROM PROFISSIONAL WHERE USUARIO_ID = ?', (id_profissional,))
        tem_prof = cur.fetchone()

        if tem_prof is None:
            return jsonify({ 'error': 'Profissional não encontrado' }), 404

        # validacao pra quando o tipo do conselho for psiquiatria (faltam clausulas)
        # pacientes podem agendar livremente com psicologos

        # cur.execute("""
        # SELECT FIRST 1 e.*
        # FROM ENCAMINHAMENTO e
        # WHERE e.PACIENTE_ID = ?
        #     AND e.PSICOLOGO_ID = ?
        #         AND e.STATUS = 'ATIVO'
        # ORDER BY CRIADO_EM DESC;
        # """, (payload.get('id_usuario'), id_profissional))

        # encam_res = cur.fetchone()

        # if encam_res == None:
        #     return jsonify({ 'error': 'Usuário precisa de encaminhamento para agendar consulta' }), 400

        cur.execute("""
        INSERT INTO SESSAO (
            PACIENTE_ID
          , PROFISSIONAL_ID
          , ENCAMINHAMENTO_ID
          , CONVERSA_ID
          , DATA_HORA_INICIO
          , DATA_HORA_FIM
          , STATUS
          , VALOR_CENTAVOS
          , LINK_REUNIAO)
        VALUES(?, ?, ?, ?, ?, ?, 'AGENDADO', (
                SELECT preco_hora
                FROM PROFISSIONAL p
                WHERE p.USUARIO_ID = 14
            )
        , ?) RETURNING *
        """, (payload.get('id_usuario'), id_profissional, None, None, timestamp_inicio, timestamp_fim, None))

        res_sessao = cur.fetchone()
        cols = [desc[0].lower() for desc in cur.description]
        sessao = dict(zip(cols, res_sessao))

        con.commit()

        return jsonify({ 'message': 'Sessao criada com sucesso', 'sessao': sessao }), 201
    except ExpiredSignatureError:
            return jsonify({ 'error': 'Expired token' }), 401
    except InvalidTokenError:
        return jsonify({ 'error': 'Invalid token' }), 401
    except Exception as e:
        if con is not None:
            con.rollback()
        print(f'[{__name__}]: {str(e)}')
        return jsonify({ 'message': 'Internal Server Error' }), 500
    finally:
        if cur is not None:
            cur.close()