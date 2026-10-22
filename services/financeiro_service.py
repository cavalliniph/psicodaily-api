from database.db import transacao
from services import notificacoes_service, pagamentos_service
from services.auditoria_service import auditar
from services.erros import ErroNegocio

STATUS_SAIDA = ('PENDENTE', 'PAGO')

# Saidas de dinheiro que o admin paga: o nome da tabela vem daqui, nunca da requisicao.
# `destino` devolve (quem recebe, CPF dele, valor, status).
SAIDAS = {
    'REEMBOLSO': {
        'destino': '''SELECT s.PACIENTE_ID, u.CPF, r.VALOR_CENTAVOS, r.STATUS FROM REEMBOLSO r
            JOIN PAGAMENTO p ON p.PAGAMENTO_ID = r.PAGAMENTO_ID
            JOIN SESSAO s ON s.SESSAO_ID = p.SESSAO_ID
            JOIN USUARIO u ON u.ID_USUARIO = s.PACIENTE_ID
            WHERE r.REEMBOLSO_ID = ?''',
        'titulo': 'Reembolso enviado',
        'mensagem': 'Devolvemos {valor} da consulta cancelada.',
    },
}


def _reais(centavos):
    return f'R$ {centavos / 100:.2f}'.replace('.', ',')


def _ler_status(status):
    if status is not None and status not in STATUS_SAIDA:
        raise ErroNegocio('status deve ser PENDENTE ou PAGO')
    return status


def _ler_manual(dados):
    dados = {} if dados is None else dados
    if not isinstance(dados, dict) or set(dados) - {'manual'} or not isinstance(dados.get('manual', False), bool):
        raise ErroNegocio('Envie {} para pagar pela Arkhé ou {"manual": true} se ja pagou por fora')
    return dados.get('manual', False)


def _pagar_saida(admin_id, tabela, registro_id, dados):
    """Paga um reembolso ou repasse: Pix pela Arkhé para a chave CPF de quem recebe ou, com manual, so marca."""
    manual = _ler_manual(dados)
    saida = SAIDAS[tabela]
    with transacao() as cur:
        cur.execute(saida['destino'], (registro_id,))
        linha = cur.fetchone()
    if linha is None:
        raise ErroNegocio(f'{tabela.capitalize()} nao encontrado', 404)
    destinatario, cpf, valor, status = linha
    if status == 'PAGO':
        raise ErroNegocio(f'{tabela.capitalize()} ja foi pago', 409)

    movimentacao = None if manual else pagamentos_service.pix_saida(cpf, valor, f'psicodaily-{tabela.lower()}-{registro_id}')
    with transacao() as cur:
        cur.execute(f'''UPDATE {tabela} SET STATUS = 'PAGO', PAGO_EM = CURRENT_TIMESTAMP, ID_MOVIMENTACAO_ARKHE = ?
            WHERE {tabela}_ID = ? AND STATUS = 'PENDENTE' RETURNING {tabela}_ID''', (movimentacao, registro_id))
        if cur.fetchone()[0] is None:
            raise ErroNegocio(f'{tabela.capitalize()} ja foi pago', 409)
        auditar(cur, admin_id, f'{tabela}_PAGO', tabela, registro_id)
        email = notificacoes_service.notificar(
            cur, destinatario, f'{tabela}_PAGO', saida['titulo'], saida['mensagem'].format(valor=_reais(valor)),
            {f'{tabela.lower()}_id': registro_id})
    notificacoes_service.enviar_emails([email])
    return {f'{tabela.lower()}_id': registro_id, 'status': 'PAGO', 'valor_centavos': valor,
            'manual': manual, 'id_movimentacao_arkhe': movimentacao}


def listar_reembolsos(status=None):
    status = _ler_status(status)
    with transacao() as cur:
        cur.execute(f'''SELECT FIRST 200 r.REEMBOLSO_ID, r.STATUS, r.VALOR_CENTAVOS, r.CRIADO_EM, r.PAGO_EM,
                r.ID_MOVIMENTACAO_ARKHE, p.METODO, s.SESSAO_ID, s.DATA_HORA_INICIO, u.ID_USUARIO, u.NOME, u.CPF
            FROM REEMBOLSO r
            JOIN PAGAMENTO p ON p.PAGAMENTO_ID = r.PAGAMENTO_ID
            JOIN SESSAO s ON s.SESSAO_ID = p.SESSAO_ID
            JOIN USUARIO u ON u.ID_USUARIO = s.PACIENTE_ID
            {'WHERE r.STATUS = ?' if status else ''} ORDER BY r.REEMBOLSO_ID DESC''', (status,) if status else ())
        linhas = cur.fetchall()
    # O CPF vai para o admin pagar por fora quando o Pix da Arkhé falha
    return [{'reembolso_id': reembolso_id, 'status': situacao, 'valor_centavos': valor, 'criado_em': criado.isoformat(),
             'pago_em': pago.isoformat() if pago else None, 'id_movimentacao_arkhe': movimentacao, 'metodo': metodo,
             'sessao_id': sessao_id, 'data_sessao': inicio.isoformat(),
             'paciente': {'id_usuario': paciente_id, 'nome': nome, 'cpf': cpf}}
            for reembolso_id, situacao, valor, criado, pago, movimentacao, metodo, sessao_id, inicio, paciente_id, nome, cpf
            in linhas]


def pagar_reembolso(admin_id, reembolso_id, dados):
    return _pagar_saida(admin_id, 'REEMBOLSO', reembolso_id, dados)
