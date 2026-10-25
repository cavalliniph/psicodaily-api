from datetime import date, datetime, timedelta

from database.db import transacao
from services.assinaturas_service import PLANOS
from services.auditoria_service import ACOES
from services.erros import ErroNegocio

PERIODOS_DIAS = ('7', '30', '90', '365')
PAPEIS = ('PACIENTE', 'PSICOLOGO', 'PSIQUIATRA', 'ADMIN')
STATUS_SESSAO = ('AGENDADO', 'CONFIRMADO', 'REALIZADO', 'CANCELADO')


def _contagem(chaves, linhas):
    return {**dict.fromkeys(chaves, 0), **{chave: total for chave, total in linhas}}


def metricas(dias):
    if dias not in PERIODOS_DIAS:
        raise ErroNegocio('dias deve ser 7, 30, 90 ou 365')
    inicio = date.today() - timedelta(days=int(dias) - 1)
    de, ate = datetime.combine(inicio, datetime.min.time()), datetime.combine(date.today() + timedelta(days=1), datetime.min.time())

    with transacao() as cur:
        # Sessoes pela data em que acontecem; sessoes futuras ficam fora do periodo
        cur.execute('''SELECT STATUS, COUNT(*) FROM SESSAO
            WHERE DATA_HORA_INICIO >= ? AND DATA_HORA_INICIO < ? GROUP BY STATUS''', (de, ate))
        sessoes = cur.fetchall()
        cur.execute('''SELECT SUM(p.VALOR_CENTAVOS) FROM PAGAMENTO p WHERE p.STATUS = 'PAGO' AND p.PAGO_EM >= ? AND p.PAGO_EM < ?
            AND NOT EXISTS (SELECT 1 FROM REEMBOLSO r WHERE r.PAGAMENTO_ID = p.PAGAMENTO_ID)''', (de, ate))
        faturamento = cur.fetchone()[0]
        cur.execute('SELECT USUARIO_ROLE, COUNT(*) FROM USUARIO WHERE ATIVO = TRUE GROUP BY USUARIO_ROLE')
        ativos = cur.fetchall()
        cur.execute('SELECT USUARIO_ROLE, COUNT(*) FROM USUARIO WHERE CRIADO_EM >= ? GROUP BY USUARIO_ROLE', (de,))
        novos = cur.fetchall()
        cur.execute('SELECT AVG(CAST(NOTA AS NUMERIC(5,2))), COUNT(*) FROM AVALIACAO WHERE CRIADO_EM >= ?', (de,))
        media, avaliacoes = cur.fetchone()
        cur.execute('SELECT PLANO, COUNT(*) FROM ASSINATURA WHERE VALIDA_ATE >= CURRENT_DATE GROUP BY PLANO')
        planos = cur.fetchall()
        cur.execute('''SELECT SUM(VALOR_CENTAVOS) FROM COBRANCA_ASSINATURA
            WHERE STATUS = 'PAGO' AND PAGO_EM >= ? AND PAGO_EM < ?''', (de, ate))
        receita_assinaturas = cur.fetchone()[0]

    return {
        'dias': int(dias),
        'data_inicio': inicio.isoformat(),
        'faturamento_centavos': faturamento or 0,
        'consultas_por_status': _contagem(STATUS_SESSAO, sessoes),
        'usuarios_ativos': _contagem(PAPEIS, ativos),
        'novos_cadastros': _contagem(PAPEIS, novos),
        'avaliacao': {'media': round(float(media), 1) if media is not None else None, 'total': avaliacoes},
        # 9: a receita das assinaturas e da plataforma; faturamento_centavos segue sendo so o das consultas
        'assinaturas': {'ativas_por_plano': _contagem(PLANOS, planos), 'receita_centavos': receita_assinaturas or 0},
    }


def auditoria(limite, antes, usuario_id=None, acao=None):
    if acao is not None and acao not in ACOES:
        raise ErroNegocio(f'acao deve ser uma de: {", ".join(sorted(ACOES))}')
    filtros, parametros = ['AUDITORIA_ID < ?'], [antes]
    if usuario_id is not None:
        filtros.append('USUARIO_ID = ?')
        parametros.append(usuario_id)
    if acao is not None:
        filtros.append('ACAO = ?')
        parametros.append(acao)

    with transacao() as cur:
        cur.execute(f'''SELECT FIRST ? AUDITORIA_ID, USUARIO_ID, ACAO, ENTIDADE, ENTIDADE_ID, IP, CRIADO_EM
            FROM AUDITORIA WHERE {' AND '.join(filtros)} ORDER BY AUDITORIA_ID DESC''', (limite + 1, *parametros))
        linhas = cur.fetchall()
    itens = [{'auditoria_id': a, 'usuario_id': u, 'acao': ac, 'entidade': e, 'entidade_id': ei, 'ip': ip,
              'criado_em': criado.isoformat()} for a, u, ac, e, ei, ip, criado in linhas[:limite]]
    return {'auditoria': itens, 'proximo_cursor': itens[-1]['auditoria_id'] if len(linhas) > limite else None}
