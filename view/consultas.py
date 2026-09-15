from datetime import datetime

from flask import Blueprint, jsonify, request
from database.db import get_connection
from funcao import decodificar_token
from jwt import ExpiredSignatureError, InvalidTokenError

cons_bp = Blueprint('consultas', __name__, url_prefix='/api/consultas')

@cons_bp.route('/', methods=['GET'])
def consultas():
    token = request.cookies.get('access_token')

    if not token:
        return jsonify({ 'error': 'Token de autenticação necessário' }), 401

    con = None
    cur = None

    try:
        payload = decodificar_token(token)
        usuario_id = payload.get('id_usuario')
        papel = payload.get('usuario_role')

        if not usuario_id:
            return jsonify({ 'error': 'Token invalido' }), 401

        con = get_connection()
        cur = con.cursor()

        filtros = []
        parametros = []
        if papel == 'PACIENTE':
            filtros.append('s.PACIENTE_ID = ?')
            parametros.append(usuario_id)
        elif papel in ('PSICOLOGO', 'PSIQUIATRA'):
            filtros.append('s.PROFISSIONAL_ID = ?')
            parametros.append(usuario_id)

        where = f"WHERE {' AND '.join(filtros)}" if filtros else ''
        cur.execute(f'''
                 SELECT s.*, u.NOME AS PROFISSIONAL_NOME,
                     paciente.NOME AS PACIENTE_NOME,
                   r.HUMOR AS ULTIMO_HUMOR,
                   r.QUALIDADE_SONO AS ULTIMA_QUALIDADE_SONO,
                   r.CRIADO_EM AS ULTIMO_REGISTRO_EM
            FROM SESSAO s
            INNER JOIN PROFISSIONAL p ON p.USUARIO_ID = s.PROFISSIONAL_ID
            INNER JOIN USUARIO u ON u.ID_USUARIO = p.USUARIO_ID
            INNER JOIN USUARIO paciente ON paciente.ID_USUARIO = s.PACIENTE_ID
            LEFT JOIN REGISTRO r ON r.REGISTRO_ID = (
                SELECT FIRST 1 r2.REGISTRO_ID
                FROM REGISTRO r2
                WHERE r2.USUARIO_ID = s.PACIENTE_ID
                ORDER BY r2.CRIADO_EM DESC, r2.REGISTRO_ID DESC
            )
            {where}
            ORDER BY s.DATA_HORA_INICIO DESC
        ''', tuple(parametros))
        query_res = cur.fetchall()

        cols = [col[0].lower() for col in cur.description]
        resultados = [dict(zip(cols, row)) for row in query_res]

        return jsonify({ 'message': 'Consultas obtidas com sucesso', 'consultas': resultados }), 200
    except (ExpiredSignatureError, InvalidTokenError):
        return jsonify({ 'error': 'Token invalido ou expirado' }), 401
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
        payload = decodificar_token(token)

        data = request.get_json(silent=True)
        
        if not data:
            return jsonify({ "error": "Formato invalido" }), 400

        id_profissional = data.get('id_profissional')
        inicio = data.get('timestamp_inicio')
        fim = data.get('timestamp_fim')

        if not id_profissional or not inicio or not fim:
            return jsonify({ 'error': 'Profissional, inicio e fim sao obrigatorios' }), 400

        try:
            timestamp_inicio = datetime.fromisoformat(inicio).replace(second=0, microsecond=0)
            timestamp_fim = datetime.fromisoformat(fim).replace(second=0, microsecond=0)
        except (TypeError, ValueError):
            return jsonify({ 'error': 'Datas devem estar no formato ISO 8601' }), 400

        agora = datetime.now().replace(second=0, microsecond=0)
        if timestamp_inicio < agora or timestamp_fim <= timestamp_inicio:
            return jsonify({ 'error': 'O horario da consulta e invalido' }), 400

        con = get_connection()
        cur = con.cursor()

        cur.execute('''
            SELECT p.PRECO_HORA
            FROM PROFISSIONAL p
            INNER JOIN USUARIO u ON u.ID_USUARIO = p.USUARIO_ID
            WHERE p.USUARIO_ID = ? AND u.ATIVO = TRUE
        ''', (id_profissional,))
        tem_prof = cur.fetchone()

        if tem_prof is None:
            return jsonify({ 'error': 'Profissional não encontrado' }), 404

        if payload.get('usuario_role') != 'PACIENTE':
            return jsonify({ 'error': 'Somente pacientes podem agendar consultas' }), 403

        cur.execute('''
            SELECT FIRST 1 1
            FROM SESSAO
            WHERE PROFISSIONAL_ID = ?
              AND STATUS <> 'CANCELADO'
              AND DATA_HORA_INICIO < ?
              AND DATA_HORA_FIM > ?
        ''', (id_profissional, timestamp_fim, timestamp_inicio))
        if cur.fetchone() is not None:
            return jsonify({ 'error': 'O profissional ja possui uma consulta nesse horario' }), 409

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
            VALUES(?, ?, ?, ?, ?, ?, 'AGENDADO', ?, ?) RETURNING *
        """, (payload.get('id_usuario'), id_profissional, None, None, timestamp_inicio, timestamp_fim, tem_prof[0], None))

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