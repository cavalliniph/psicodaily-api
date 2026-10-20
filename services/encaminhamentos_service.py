from database.db import transacao
from services.auditoria_service import auditar
from services.erros import ErroNegocio


def criar(profissional_id, dados):
    if dados is None:
        raise ErroNegocio('Formato inválido')
    id_usuario = dados.get('id_usuario')
    motivo = dados.get('motivo')
    if id_usuario is None or motivo is None:
        raise ErroNegocio('id_usuario e motivo são obrigatórios')

    with transacao() as cur:
        cur.execute('SELECT 1 FROM usuario WHERE id_usuario = ?', (id_usuario,))
        if cur.fetchone() is None:
            raise ErroNegocio('Usuário não encontrado', 404)
        cur.execute("""
        INSERT INTO ENCAMINHAMENTO(PACIENTE_ID, PSICOLOGO_ID, CID, MOTIVO, STATUS)
        VALUES(?, ?, ?, ?, ?) RETURNING *
        """, (id_usuario, profissional_id, dados.get('id_cid') or None, motivo, 'ATIVO'))
        linha = cur.fetchone()
        encaminhamento = dict(zip([desc[0].lower() for desc in cur.description], linha))
        auditar(cur, profissional_id, 'ENCAMINHAMENTO_CRIADO', 'ENCAMINHAMENTO', encaminhamento['encaminhamento_id'])
        return encaminhamento


def listar():
    with transacao() as cur:
        cur.execute('SELECT * FROM ENCAMINHAMENTO')
        colunas = [desc[0].lower() for desc in cur.description]
        return [dict(zip(colunas, linha)) for linha in cur.fetchall()]
