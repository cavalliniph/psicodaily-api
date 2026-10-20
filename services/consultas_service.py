import os
import threading
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit

import fdb

from database.db import transacao
from services import disponibilidade_service, email_service, lista_espera_service, notificacoes_service
from services.auditoria_service import auditar
from services.erros import ErroNegocio
from services.upload_service import upload_service

MENSAGEM_CONFLITO = 'Profissional ou paciente ja possui consulta nesse horario'


def serializar_sessao(colunas, linha):
    # TIMESTAMP do banco representa o horario local, sem conversao para GMT.
    sessao = {coluna: valor.isoformat() if isinstance(valor, (date, datetime)) else valor
              for coluna, valor in zip(colunas, linha)}
    sessao['paciente_foto_url'] = upload_service.url_foto_usuario(sessao['paciente_id'])
    sessao['profissional_foto_url'] = upload_service.url_foto_usuario(sessao['profissional_id'])
    return sessao


def _sessao_retornada(cur):
    linha = cur.fetchone()
    return serializar_sessao([desc[0].lower() for desc in cur.description], linha)


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
        raise ErroNegocio('Informe inicio e fim no formato AAAA-MM-DDTHH:MM, sem fuso horario')
    if inicio < datetime.now().replace(second=0, microsecond=0) or fim <= inicio:
        raise ErroNegocio('Informe um horario futuro e um fim posterior ao inicio')
    return inicio, fim


def reservar_participantes(cur, profissional_id, paciente_id):
    # Serializa agendamentos/reagendamentos concorrentes das mesmas pessoas.
    # A ordem fixa evita que duas requisicoes adquiram os bloqueios ao contrario.
    cur.execute('''SELECT ID_USUARIO FROM USUARIO
        WHERE ID_USUARIO IN (?, ?) ORDER BY ID_USUARIO WITH LOCK''',
                (profissional_id, paciente_id))
    cur.fetchall()


def listar(usuario_id, papel):
    if not usuario_id:
        raise ErroNegocio('Token invalido', 401)
    if papel not in ('PACIENTE', 'PSICOLOGO', 'PSIQUIATRA', 'ADMIN'):
        raise ErroNegocio('Usuario sem permissao para consultar sessoes', 403)

    where, parametros = '', ()
    if papel == 'PACIENTE':
        where, parametros = 'WHERE s.PACIENTE_ID = ?', (usuario_id,)
    elif papel in ('PSICOLOGO', 'PSIQUIATRA'):
        where, parametros = 'WHERE s.PROFISSIONAL_ID = ?', (usuario_id,)

    with transacao() as cur:
        cur.execute(f'''
                 SELECT s.*, u.NOME AS PROFISSIONAL_NOME,
                     paciente.NOME AS PACIENTE_NOME,
                   r.HUMOR AS ULTIMO_HUMOR,
                   r.QUALIDADE_SONO AS ULTIMA_QUALIDADE_SONO,
                   r.CRIADO_EM AS ULTIMO_REGISTRO_EM,
                   av.NOTA AS NOTA_AVALIACAO
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
            LEFT JOIN AVALIACAO av ON av.SESSAO_ID = s.SESSAO_ID
            {where}
            ORDER BY s.DATA_HORA_INICIO DESC
        ''', parametros)
        colunas = [col[0].lower() for col in cur.description]
        return [serializar_sessao(colunas, linha) for linha in cur.fetchall()]


def agendar(paciente_id, papel, data):
    if not isinstance(data, dict) or not data:
        raise ErroNegocio('Formato invalido')
    id_profissional = data.get('id_profissional')
    inicio = data.get('timestamp_inicio')
    fim = data.get('timestamp_fim')
    if not id_profissional or not inicio or not fim:
        raise ErroNegocio('Profissional, inicio e fim sao obrigatorios')
    inicio, fim = ler_intervalo(inicio, fim)

    with transacao() as cur:
        cur.execute('''
            SELECT p.PRECO_HORA
            FROM PROFISSIONAL p
            INNER JOIN USUARIO u ON u.ID_USUARIO = p.USUARIO_ID
            WHERE p.USUARIO_ID = ? AND u.ATIVO = TRUE
        ''', (id_profissional,))
        profissional = cur.fetchone()
        if profissional is None:
            raise ErroNegocio('Profissional não encontrado', 404)
        if papel != 'PACIENTE':
            raise ErroNegocio('Somente pacientes podem agendar consultas', 403)
        na_agenda, parametros = disponibilidade_service.filtro_sql('p.USUARIO_ID', inicio, fim)
        cur.execute(f'SELECT 1 FROM PROFISSIONAL p WHERE p.USUARIO_ID = ? AND {na_agenda}',
                    (id_profissional, *parametros))
        if cur.fetchone() is None:
            raise ErroNegocio('Horario fora da agenda do profissional', 409)

        reservar_participantes(cur, id_profissional, paciente_id)
        cur.execute('''
            SELECT FIRST 1 1
            FROM SESSAO
            WHERE (PROFISSIONAL_ID = ? OR PACIENTE_ID = ?)
              AND STATUS <> 'CANCELADO'
              AND DATA_HORA_INICIO < ?
              AND DATA_HORA_FIM > ?
        ''', (id_profissional, paciente_id, fim, inicio))
        if cur.fetchone() is not None:
            raise ErroNegocio(MENSAGEM_CONFLITO, 409)

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
        """, (paciente_id, id_profissional, None, None, inicio, fim, profissional[0], None))
        sessao = _sessao_retornada(cur)
        auditar(cur, paciente_id, 'SESSAO_AGENDADA', 'SESSAO', sessao['sessao_id'])
        return sessao


def _ler_link(link):
    if link is not None and not isinstance(link, str):
        raise ErroNegocio('Link da reuniao invalido')
    link = (link or '').strip() or None
    try:
        partes = urlsplit(link) if link else None
        if link and (len(link) > 255 or partes.scheme not in ('http', 'https')
                     or not partes.hostname or partes.username or partes.password
                     or any(caractere.isspace() for caractere in link)):
            raise ValueError()
    except ValueError:
        raise ErroNegocio('Informe um link HTTP ou HTTPS valido, de ate 255 caracteres')
    return link


def atualizar(profissional_id, sessao_id, dados):
    if not profissional_id:
        raise ErroNegocio('Token invalido', 401)
    permitidos = {'timestamp_inicio', 'timestamp_fim', 'status', 'link_reuniao'}
    if not isinstance(dados, dict) or not dados or set(dados) - permitidos:
        raise ErroNegocio('Informe apenas horario, status ou link da reuniao')
    if ('timestamp_inicio' in dados) != ('timestamp_fim' in dados):
        raise ErroNegocio('Informe inicio e fim juntos')
    status = dados.get('status')
    if 'status' in dados and status not in ('REALIZADO', 'CANCELADO'):
        raise ErroNegocio('Status deve ser REALIZADO ou CANCELADO')
    if status and len(dados) != 1:
        raise ErroNegocio('Altere o status separadamente do horario e do link')

    intervalo = ler_intervalo(dados['timestamp_inicio'], dados['timestamp_fim']) if 'timestamp_inicio' in dados else None
    link = _ler_link(dados.get('link_reuniao')) if 'link_reuniao' in dados else None

    with transacao() as cur:
        cur.execute('''SELECT STATUS, DATA_HORA_INICIO, DATA_HORA_FIM, PACIENTE_ID
            FROM SESSAO WHERE SESSAO_ID = ? AND PROFISSIONAL_ID = ? WITH LOCK''',
                    (sessao_id, profissional_id))
        sessao = cur.fetchone()
        if sessao is None:
            raise ErroNegocio('Sessao nao encontrada', 404)
        if sessao[0] in ('REALIZADO', 'CANCELADO'):
            raise ErroNegocio('Esta sessao ja foi encerrada e nao pode ser alterada', 409)
        if status == 'REALIZADO' and sessao[2] > datetime.now():
            raise ErroNegocio('Aguarde o fim do horario da sessao para concluir', 409)

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
                raise ErroNegocio(MENSAGEM_CONFLITO, 409)
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
        atualizada = _sessao_retornada(cur)
        auditar(cur, profissional_id, 'SESSAO_ALTERADA', 'SESSAO', sessao_id)
        emails = []
        if status == 'CANCELADO':
            emails = lista_espera_service.avisar_vaga(cur, profissional_id, sessao[1], sessao[2], sessao[3])
    notificacoes_service.enviar_emails(emails)
    return atualizada


def avaliar(paciente_id, papel, sessao_id, dados):
    if papel != 'PACIENTE' or not paciente_id:
        raise ErroNegocio('Somente o paciente pode avaliar a sessao', 403)
    if not isinstance(dados, dict) or set(dados) - {'nota', 'comentario'}:
        raise ErroNegocio('Envie apenas nota e comentario')
    nota = dados.get('nota')
    if type(nota) is not int or not 1 <= nota <= 5:
        raise ErroNegocio('nota deve ser inteiro entre 1 e 5')
    comentario = dados.get('comentario')
    if comentario is not None:
        if not isinstance(comentario, str) or len(comentario.strip()) > 500:
            raise ErroNegocio('comentario deve ter no maximo 500 caracteres')
        comentario = comentario.strip() or None

    try:
        with transacao() as cur:
            cur.execute('SELECT PROFISSIONAL_ID, STATUS FROM SESSAO WHERE SESSAO_ID = ? AND PACIENTE_ID = ?',
                        (sessao_id, paciente_id))
            sessao = cur.fetchone()
            if sessao is None:
                raise ErroNegocio('Sessao nao encontrada', 404)
            if sessao[1] != 'REALIZADO':
                raise ErroNegocio('Só é possível avaliar sessões realizadas', 409)
            cur.execute('''INSERT INTO AVALIACAO (SESSAO_ID, PACIENTE_ID, PROFISSIONAL_ID, NOTA, COMENTARIO)
                VALUES (?, ?, ?, ?, ?)''', (sessao_id, paciente_id, sessao[0], nota, comentario))
    except fdb.DatabaseError as erro:
        if 'UQ_AVALIACAO_SESSAO' in str(erro):
            raise ErroNegocio('Sessão já avaliada', 409)
        raise
    return {'sessao_id': sessao_id, 'nota': nota}


def sala_da_sessao(id_usuario, sessao_id):
    """Dados da sala se o usuario pode entrar agora, senao None.

    A sala abre 15 min antes do inicio e fecha no fim, so para os participantes.
    """
    with transacao() as cur:
        cur.execute('''SELECT s.STATUS, s.DATA_HORA_INICIO, s.DATA_HORA_FIM,
                   pac.ID_USUARIO, pac.NOME, pac.EMAIL, prof.ID_USUARIO, prof.NOME, prof.EMAIL
            FROM SESSAO s
            INNER JOIN USUARIO pac ON pac.ID_USUARIO = s.PACIENTE_ID
            INNER JOIN USUARIO prof ON prof.ID_USUARIO = s.PROFISSIONAL_ID
            WHERE s.SESSAO_ID = ?''', (sessao_id,))
        sessao = cur.fetchone()
    if not sessao:
        return None
    status, inicio, fim = sessao[:3]
    participantes = {linha[0]: {'id_usuario': linha[0], 'nome': linha[1], 'email': linha[2]}
                     for linha in (sessao[3:6], sessao[6:9])}
    agora = datetime.now()
    if (id_usuario not in participantes or status == 'CANCELADO'
            or inicio > agora.replace(second=0, microsecond=0) + timedelta(minutes=15) or fim < agora):
        return None
    return {'sessao_id': sessao_id, 'inicio': inicio, 'participantes': participantes}


# ponytail: dedupe em memoria (processo unico); reinicio do servidor pode repetir um aviso
_avisos_enviados = set()
_avisos_lock = threading.Lock()


def avisar_entrada_na_sala(sala, id_usuario, presentes):
    """Avisa por e-mail quem ainda nao entrou; uma vez por sessao e por quem entrou."""
    url_sala = f"{os.getenv('FRONT_URL', 'https://psicodaily-front.vercel.app').rstrip('/')}/videochamada/{sala['sessao_id']}"
    quem_entrou = sala['participantes'][id_usuario]
    for destino in sala['participantes'].values():
        if destino['id_usuario'] == id_usuario or destino['id_usuario'] in presentes:
            continue
        chave = (sala['sessao_id'], id_usuario, destino['id_usuario'])
        with _avisos_lock:
            if chave in _avisos_enviados:
                continue
            _avisos_enviados.add(chave)
        email_service.enviar_email_async(
            destino['email'],
            f"{quem_entrou['nome']} entrou na sala da sua consulta",
            f"Olá, {destino['nome']}.\n\n"
            f"{quem_entrou['nome']} já está na sala da consulta de "
            f"{sala['inicio'].strftime('%d/%m/%Y às %H:%M')} e aguarda você.\n\n"
            f"Entre pelo link: {url_sala}",
        )
