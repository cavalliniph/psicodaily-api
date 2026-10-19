from datetime import date, timedelta

from database.db import transacao
from services.erros import ErroNegocio
from services.registros_service import COLUNAS, serializar
from services.upload_service import upload_service

ESCALA_HUMOR = {'PESSIMO': 1, 'RUIM': 2, 'NEUTRO': 3, 'BOM': 4, 'EXCELENTE': 5}


def evolucao_humor(linhas):
    """linhas: (CRIADO_EM, HUMOR, ...) -> media diaria na escala 1-5."""
    por_dia = {}
    for linha in linhas:
        if linha[1] in ESCALA_HUMOR:
            por_dia.setdefault(linha[0].isoformat(), []).append(ESCALA_HUMOR[linha[1]])
    return [{'data': dia, 'valor': sum(valores) / len(valores), 'quantidade': len(valores)}
            for dia, valores in por_dia.items()]


def prontuario(profissional_id, paciente_id, dias, antes):
    with transacao() as cur:
        # O vinculo deve existir antes de consultar qualquer dado do paciente.
        cur.execute('''SELECT FIRST 1 1 FROM SESSAO
            WHERE PACIENTE_ID = ? AND PROFISSIONAL_ID = ?
            AND STATUS <> 'CANCELADO' ''', (paciente_id, profissional_id))
        if cur.fetchone() is None:
            raise ErroNegocio('Paciente sem vinculo de atendimento com este profissional', 403)

        cur.execute('SELECT NOME FROM USUARIO WHERE ID_USUARIO = ?', (paciente_id,))
        paciente = cur.fetchone()
        if paciente is None:
            raise ErroNegocio('Paciente nao encontrado', 404)

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
        valores = [ESCALA_HUMOR[linha[1]] for linha in linhas if linha[1] in ESCALA_HUMOR]
        sono = [linha[2] for linha in linhas if linha[2] is not None]

        cur.execute(f'''SELECT FIRST 21 {', '.join(COLUNAS)} FROM REGISTRO
            WHERE USUARIO_ID = ? AND CRIADO_EM BETWEEN ? AND ? AND REGISTRO_ID < ?
            ORDER BY REGISTRO_ID DESC''', (paciente_id, inicio, hoje, antes))
        pagina = cur.fetchall()
        registros = [serializar(linha) for linha in pagina[:20]]

    return {
        'paciente': {'id_usuario': paciente_id, 'nome': paciente[0],
                     'foto_url': upload_service.url_foto_usuario(paciente_id)},
        'ultimaConsulta': {'data': ultima[0].isoformat(), 'status': ultima[1]} if ultima else None,
        'resumo': {
            'totalRegistros': len(linhas),
            'diasRegistrados': len({linha[0] for linha in linhas}),
            'humorMedio': sum(valores) / len(valores) if valores else None,
            'minutosSonoMedio': sum(sono) / len(sono) if sono else None,
            'registrosComExercicio': sum(linha[3] is True or linha[3] == 1 for linha in linhas),
        },
        'evolucaoHumor': evolucao_humor(linhas),
        'registros': registros,
        'proximo_cursor': registros[-1]['registro_id'] if len(pagina) > 20 else None,
    }
