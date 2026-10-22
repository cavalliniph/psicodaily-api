from contextvars import ContextVar

from database.db import transacao

# Preenchido pelo app.py a cada requisicao, para os services nao importarem flask
IP_ATUAL = ContextVar('ip_atual', default=None)

ACOES = {'LOGIN', 'LOGIN_FALHA', 'PRONTUARIO_ACESSO', 'SESSAO_AGENDADA', 'SESSAO_ALTERADA',
         'ENCAMINHAMENTO_CRIADO', 'SENHA_ALTERADA', 'EMAIL_ALTERADO', 'SESSAO_CANCELADA', 'REEMBOLSO_PAGO'}


def auditar(cur, usuario_id, acao, entidade=None, entidade_id=None):
    """Grava na mesma transacao da acao: se ela for desfeita, o registro tambem e."""
    assert acao in ACOES, acao
    cur.execute('''INSERT INTO AUDITORIA (USUARIO_ID, ACAO, ENTIDADE, ENTIDADE_ID, IP)
        VALUES (?, ?, ?, ?, ?)''', (usuario_id, acao, entidade, entidade_id, (IP_ATUAL.get() or '')[:45] or None))


def auditar_avulso(usuario_id, acao, entidade=None, entidade_id=None):
    """Transacao propria, para o que precisa ficar mesmo quando a requisicao falha (ex.: login errado)."""
    with transacao() as cur:
        auditar(cur, usuario_id, acao, entidade, entidade_id)
