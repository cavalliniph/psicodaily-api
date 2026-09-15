from datetime import date, timedelta

from flask import Blueprint, current_app, jsonify, request
from database.db import get_connection
from util.usuarios import profissional_autenticado
from view.registros import COLUNAS, serializar

prontuario_bp = Blueprint('prontuario', __name__, url_prefix='/api/prontuario')


@prontuario_bp.route('/<int:paciente_id>', methods=['GET'])
@profissional_autenticado
def prontuario(dados_usuario, paciente_id):
    profissional_id = dados_usuario.get('id_usuario')
    if not profissional_id:
        return jsonify({'error': 'Usuario nao autenticado'}), 401
    try:
        dias = int(request.args.get('dias', 30))
        antes = int(request.args.get('antes', 2147483647))
        if dias not in (7, 30, 90) or antes < 1:
            raise ValueError()
    except ValueError:
        return jsonify({'error': 'Periodo ou paginacao invalida'}), 400

    con = cur = None
    try:
        con = get_connection()
        cur = con.cursor()
        # O vinculo deve existir antes de consultar qualquer dado do paciente.
        cur.execute('''SELECT FIRST 1 1 FROM SESSAO
            WHERE PACIENTE_ID = ? AND PROFISSIONAL_ID = ?
            AND STATUS <> 'CANCELADO' ''', (paciente_id, profissional_id))
        if cur.fetchone() is None:
            return jsonify({'error': 'Paciente sem vinculo de atendimento com este profissional'}), 403

        cur.execute('SELECT NOME FROM USUARIO WHERE ID_USUARIO = ?', (paciente_id,))
        paciente = cur.fetchone()
        if paciente is None:
            return jsonify({'error': 'Paciente nao encontrado'}), 404

        cur.execute('''SELECT FIRST 1 DATA_HORA_INICIO, STATUS FROM SESSAO
            WHERE PACIENTE_ID = ? AND PROFISSIONAL_ID = ? AND STATUS = 'REALIZADO'
            ORDER BY DATA_HORA_INICIO DESC''', (paciente_id, profissional_id))
        ultima = cur.fetchone()

        hoje = date.today()
        inicio = hoje - timedelta(days=dias - 1)
        cur.execute('''SELECT CRIADO_EM, HUMOR, MINUTOS_SONO, EXERCICIO_FISICO
            FROM REGISTRO WHERE USUARIO_ID = ? AND CRIADO_EM BETWEEN ? AND ?
            ORDER BY CRIADO_EM, REGISTRO_ID''', (paciente_id, inicio, hoje))
        linhas = cur.fetchall()
        escala = {'PESSIMO': 1, 'RUIM': 2, 'NEUTRO': 3, 'BOM': 4, 'EXCELENTE': 5}
        por_dia = {}
        for data, humor, _, _ in linhas:
            if humor in escala:
                por_dia.setdefault(data.isoformat(), []).append(escala[humor])
        evolucao = [{'data': dia, 'valor': sum(valores) / len(valores), 'quantidade': len(valores)}
                    for dia, valores in por_dia.items()]
        valores = [escala[linha[1]] for linha in linhas if linha[1] in escala]
        sono = [linha[2] for linha in linhas if linha[2] is not None]

        colunas = ', '.join(COLUNAS)
        cur.execute(f'''SELECT FIRST 21 {colunas} FROM REGISTRO
            WHERE USUARIO_ID = ? AND CRIADO_EM BETWEEN ? AND ? AND REGISTRO_ID < ?
            ORDER BY REGISTRO_ID DESC''', (paciente_id, inicio, hoje, antes))
        pagina = cur.fetchall()
        registros = [serializar(linha) for linha in pagina[:20]]
        resposta = jsonify({
            'paciente': {'id_usuario': paciente_id, 'nome': paciente[0]},
            'ultimaConsulta': {'data': ultima[0].isoformat(), 'status': ultima[1]} if ultima else None,
            'resumo': {
                'totalRegistros': len(linhas),
                'diasRegistrados': len({linha[0] for linha in linhas}),
                'humorMedio': sum(valores) / len(valores) if valores else None,
                'minutosSonoMedio': sum(sono) / len(sono) if sono else None,
                'registrosComExercicio': sum(linha[3] is True or linha[3] == 1 for linha in linhas),
            },
            'evolucaoHumor': evolucao,
            'registros': registros,
            'proximo_cursor': registros[-1]['registro_id'] if len(pagina) > 20 else None,
        })
        resposta.headers['Cache-Control'] = 'private, no-store'
        return resposta
    except Exception:
        current_app.logger.exception('Erro ao acessar prontuario')
        return jsonify({'error': 'Nao foi possivel carregar o prontuario'}), 500
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()
