from database.db import transacao
from services.erros import ErroNegocio
from services.upload_service import upload_service

MAXIMO_TEXTO = 2000


def _colunas(papel):
    """(coluna do usuario, coluna do outro) em SESSAO e MENSAGEM."""
    if papel == 'PACIENTE':
        return 'PACIENTE_ID', 'PROFISSIONAL_ID'
    if papel in ('PSICOLOGO', 'PSIQUIATRA'):
        return 'PROFISSIONAL_ID', 'PACIENTE_ID'
    raise ErroNegocio('Chat exclusivo de pacientes e profissionais', 403)


def _par(cur, usuario_id, papel, outro_id):
    """(paciente_id, profissional_id) se existe vinculo (sessao nao cancelada); senao 404."""
    eu, outro = _colunas(papel)
    cur.execute(f'''SELECT FIRST 1 PACIENTE_ID, PROFISSIONAL_ID FROM SESSAO
        WHERE {eu} = ? AND {outro} = ? AND STATUS <> 'CANCELADO' ''', (usuario_id, outro_id))
    par = cur.fetchone()
    if par is None:
        raise ErroNegocio('Conversa nao encontrada', 404)
    return par


def _mensagem(mensagem_id, remetente_id, texto, lida, criado_em):
    return {'mensagem_id': mensagem_id, 'remetente_id': remetente_id, 'texto': texto, 'lida': lida,
            'criado_em': criado_em.isoformat()}


def conversas(usuario_id, papel):
    """Todos com quem ha vinculo, com a ultima mensagem e quantas recebidas nao foram lidas."""
    eu, outro = _colunas(papel)
    with transacao() as cur:
        cur.execute(f'''SELECT v.OUTRO, u.NOME, COALESCE(r.NAO_LIDAS, 0),
                m.MENSAGEM_ID, m.REMETENTE_ID, m.TEXTO, m.LIDA, m.CRIADO_EM
            FROM (SELECT DISTINCT {outro} AS OUTRO FROM SESSAO WHERE {eu} = ? AND STATUS <> 'CANCELADO') v
            JOIN USUARIO u ON u.ID_USUARIO = v.OUTRO
            LEFT JOIN (SELECT {outro} AS OUTRO, MAX(MENSAGEM_ID) AS ULTIMA,
                    SUM(IIF(LIDA = FALSE AND REMETENTE_ID <> ?, 1, 0)) AS NAO_LIDAS
                FROM MENSAGEM WHERE {eu} = ? GROUP BY {outro}) r ON r.OUTRO = v.OUTRO
            LEFT JOIN MENSAGEM m ON m.MENSAGEM_ID = r.ULTIMA
            ORDER BY m.MENSAGEM_ID DESC NULLS LAST, u.NOME''', (usuario_id, usuario_id, usuario_id))
        linhas = cur.fetchall()
    return [{'id_usuario': outro_id, 'nome': nome, 'foto_url': upload_service.url_foto_usuario(outro_id),
             'nao_lidas': nao_lidas, 'ultima_mensagem': _mensagem(*ultima) if ultima[0] else None}
            for outro_id, nome, nao_lidas, *ultima in linhas]


def mensagens(usuario_id, papel, outro_id, limite, antes=None, depois=None):
    """Sem cursor: as ultimas `limite`. `antes`: historico mais antigo. `depois`: as novas (polling).
    Sempre em ordem cronologica; marca como lidas as recebidas."""
    with transacao() as cur:
        paciente_id, profissional_id = _par(cur, usuario_id, papel, outro_id)
        filtro, parametros, ordem = '', (), 'DESC'
        if depois is not None:
            filtro, parametros, ordem = ' AND MENSAGEM_ID > ?', (depois,), 'ASC'
        elif antes is not None:
            filtro, parametros = ' AND MENSAGEM_ID < ?', (antes,)
        cur.execute(f'''SELECT FIRST ? MENSAGEM_ID, REMETENTE_ID, TEXTO, LIDA, CRIADO_EM FROM MENSAGEM
            WHERE PACIENTE_ID = ? AND PROFISSIONAL_ID = ?{filtro} ORDER BY MENSAGEM_ID {ordem}''',
                    (limite, paciente_id, profissional_id, *parametros))
        linhas = cur.fetchall()
        cur.execute('''UPDATE MENSAGEM SET LIDA = TRUE
            WHERE PACIENTE_ID = ? AND PROFISSIONAL_ID = ? AND REMETENTE_ID <> ? AND LIDA = FALSE''',
                    (paciente_id, profissional_id, usuario_id))
    itens = [_mensagem(*linha) for linha in linhas]
    return itens if ordem == 'ASC' else itens[::-1]


def enviar(usuario_id, papel, outro_id, dados):
    if not isinstance(dados, dict) or set(dados) != {'texto'} or not isinstance(dados['texto'], str):
        raise ErroNegocio('Envie apenas texto')
    texto = dados['texto'].strip()
    if not 1 <= len(texto) <= MAXIMO_TEXTO:
        raise ErroNegocio(f'A mensagem deve ter de 1 a {MAXIMO_TEXTO} caracteres')
    with transacao() as cur:
        paciente_id, profissional_id = _par(cur, usuario_id, papel, outro_id)
        cur.execute('''INSERT INTO MENSAGEM (PACIENTE_ID, PROFISSIONAL_ID, REMETENTE_ID, TEXTO) VALUES (?, ?, ?, ?)
            RETURNING MENSAGEM_ID, REMETENTE_ID, TEXTO, LIDA, CRIADO_EM''', (paciente_id, profissional_id, usuario_id, texto))
        return _mensagem(*cur.fetchone())
