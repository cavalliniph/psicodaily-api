from datetime import date, datetime
from urllib.parse import urlsplit

from flask import Blueprint, jsonify, request
from database.db import get_connection
from funcao import decodificar_token
from jwt import ExpiredSignatureError, InvalidTokenError
from util.usuarios import profissional_autenticado

cons_bp = Blueprint('consultas', __name__, url_prefix='/api/consultas')


def serializar_sessao(colunas, linha):
    # TIMESTAMP do banco representa o horario local, sem conversao para GMT.
    return {coluna: valor.isoformat() if isinstance(valor, (date, datetime)) else valor
            for coluna, valor in zip(colunas, linha)}


def ler_intervalo(inicio, fim):
    try:
        if not isinstance(inicio, str) or not isinstance(fim, str) or 'T' not in inicio or 'T' not in fim:
            raise ValueError()
        # O agendamento do paciente tambem envia segundos (:00).
        inicio = datetime.fromisoformat(inicio)
        fim = datetime.fromisoformat(fim)
        if any(data.tzinfo is not None or data.second or data.microsecond for data in (inicio, fim)):
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError('Informe inicio e fim no formato AAAA-MM-DDTHH:MM, sem fuso horario')
    if inicio < datetime.now().replace(second=0, microsecond=0) or fim <= inicio:
        raise ValueError('Informe um horario futuro e um fim posterior ao inicio')
    return inicio, fim


def reservar_participantes(cur, profissional_id, paciente_id):
    # Serializa agendamentos/reagendamentos concorrentes das mesmas pessoas.
    # A ordem fixa evita que duas requisicoes adquiram os bloqueios ao contrario.
    cur.execute('''SELECT ID_USUARIO FROM USUARIO
        WHERE ID_USUARIO IN (?, ?) ORDER BY ID_USUARIO WITH LOCK''',
                (profissional_id, paciente_id))
    cur.fetchall()

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
        if papel not in ('PACIENTE', 'PSICOLOGO', 'PSIQUIATRA', 'ADMIN'):
            return jsonify({'error': 'Usuario sem permissao para consultar sessoes'}), 403

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
        resultados = [serializar_sessao(cols, row) for row in query_res]

        return jsonify({ 'message': 'Consultas obtidas com sucesso', 'consultas': resultados }), 200
    except (ExpiredSignatureError, InvalidTokenError):
        return jsonify({ 'error': 'Token invalido ou expirado' }), 401
    except Exception as e:
        print(f'[{__name__}]: {str(e)}')
        return jsonify({ 'message': 'Internal Server Error' }), 500
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()

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
        
        if not isinstance(data, dict) or not data:
            return jsonify({ "error": "Formato invalido" }), 400

        id_profissional = data.get('id_profissional')
        inicio = data.get('timestamp_inicio')
        fim = data.get('timestamp_fim')

        if not id_profissional or not inicio or not fim:
            return jsonify({ 'error': 'Profissional, inicio e fim sao obrigatorios' }), 400

        try:
            timestamp_inicio, timestamp_fim = ler_intervalo(inicio, fim)
        except ValueError as erro:
            return jsonify({'error': str(erro)}), 400

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

        reservar_participantes(cur, id_profissional, payload.get('id_usuario'))

        cur.execute('''
            SELECT FIRST 1 1
            FROM SESSAO
            WHERE (PROFISSIONAL_ID = ? OR PACIENTE_ID = ?)
              AND STATUS <> 'CANCELADO'
              AND DATA_HORA_INICIO < ?
              AND DATA_HORA_FIM > ?
        ''', (id_profissional, payload.get('id_usuario'), timestamp_fim, timestamp_inicio))
        if cur.fetchone() is not None:
            return jsonify({ 'error': 'Profissional ou paciente ja possui consulta nesse horario' }), 409

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
        sessao = serializar_sessao(cols, res_sessao)

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
        if con is not None:
            con.close()


@cons_bp.route('/<int:sessao_id>', methods=['PATCH'])
@profissional_autenticado
def atualizar_consulta(dados_usuario, sessao_id):
    if not dados_usuario.get('id_usuario'):
        return jsonify({'error': 'Token invalido'}), 401
    dados = request.get_json(silent=True)
    permitidos = {'timestamp_inicio', 'timestamp_fim', 'status', 'link_reuniao'}
    if not isinstance(dados, dict) or not dados or set(dados) - permitidos:
        return jsonify({'error': 'Informe apenas horario, status ou link da reuniao'}), 400
    if ('timestamp_inicio' in dados) != ('timestamp_fim' in dados):
        return jsonify({'error': 'Informe inicio e fim juntos'}), 400
    status = dados.get('status')
    if 'status' in dados and status not in ('REALIZADO', 'CANCELADO'):
        return jsonify({'error': 'Status deve ser REALIZADO ou CANCELADO'}), 400
    if status and len(dados) != 1:
        return jsonify({'error': 'Altere o status separadamente do horario e do link'}), 400

    intervalo = None
    if 'timestamp_inicio' in dados:
        try:
            intervalo = ler_intervalo(dados['timestamp_inicio'], dados['timestamp_fim'])
        except ValueError as erro:
            return jsonify({'error': str(erro)}), 400

    link = dados.get('link_reuniao')
    if 'link_reuniao' in dados:
        if link is not None and not isinstance(link, str):
            return jsonify({'error': 'Link da reuniao invalido'}), 400
        link = (link or '').strip() or None
        try:
            partes = urlsplit(link) if link else None
            if link and (len(link) > 255 or partes.scheme not in ('http', 'https')
                         or not partes.hostname or partes.username or partes.password
                         or any(caractere.isspace() for caractere in link)):
                raise ValueError()
        except ValueError:
            return jsonify({'error': 'Informe um link HTTP ou HTTPS valido, de ate 255 caracteres'}), 400

    con = cur = None
    try:
        con = get_connection()
        cur = con.cursor()
        profissional_id = dados_usuario['id_usuario']
        cur.execute('''SELECT STATUS, DATA_HORA_INICIO, DATA_HORA_FIM, PACIENTE_ID
            FROM SESSAO WHERE SESSAO_ID = ? AND PROFISSIONAL_ID = ? WITH LOCK''',
                    (sessao_id, profissional_id))
        sessao = cur.fetchone()
        if sessao is None:
            return jsonify({'error': 'Sessao nao encontrada'}), 404
        if sessao[0] in ('REALIZADO', 'CANCELADO'):
            return jsonify({'error': 'Esta sessao ja foi encerrada e nao pode ser alterada'}), 409
        if status == 'REALIZADO' and sessao[2] > datetime.now():
            return jsonify({'error': 'Aguarde o fim do horario da sessao para concluir'}), 409

        campos, parametros = [], []
        if intervalo:
            inicio, fim = intervalo
            reservar_participantes(cur, profissional_id, sessao[3])
            cur.execute('''SELECT FIRST 1 1 FROM SESSAO
                WHERE SESSAO_ID <> ? AND STATUS <> 'CANCELADO'
                AND (PROFISSIONAL_ID = ? OR PACIENTE_ID = ?)
                AND DATA_HORA_INICIO < ? AND DATA_HORA_FIM > ?''',
                        (sessao_id, profissional_id, sessao[3], fim, inicio))
            if cur.fetchone() is not None:
                return jsonify({'error': 'Profissional ou paciente ja possui consulta nesse horario'}), 409
            campos.extend(['DATA_HORA_INICIO = ?', 'DATA_HORA_FIM = ?'])
            parametros.extend([inicio, fim])
        if status:
            campos.append('STATUS = ?')
            parametros.append(status)
        if 'link_reuniao' in dados:
            campos.append('LINK_REUNIAO = ?')
            parametros.append(link)
        cur.execute(f'''UPDATE SESSAO SET {', '.join(campos)}
            WHERE SESSAO_ID = ? AND PROFISSIONAL_ID = ? RETURNING *''',
                    (*parametros, sessao_id, profissional_id))
        linha = cur.fetchone()
        colunas = [coluna[0].lower() for coluna in cur.description]
        resultado = serializar_sessao(colunas, linha)
        con.commit()
        return jsonify({'message': 'Sessao atualizada com sucesso', 'sessao': resultado})
    except Exception as erro:
        if con is not None:
            con.rollback()
        print(f'[{__name__}]: {erro}')
        return jsonify({'error': 'Nao foi possivel atualizar a sessao'}), 500
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()
