from datetime import date, datetime, time, timedelta

from database.db import transacao
from services.erros import ErroNegocio

# 0 = domingo ... 6 = sabado, como EXTRACT(WEEKDAY) do Firebird e getDay() do JavaScript
NOMES_DIAS = {'DOMINGO': 0, 'SEGUNDA': 1, 'TERCA': 2, 'QUARTA': 3, 'QUINTA': 4, 'SEXTA': 5, 'SABADO': 6}
# Janela padrao para os dias marcados no cadastro, ate o profissional ajustar a agenda
PADRAO_CADASTRO = (time(8), time(18))
MAXIMO_JANELAS = 50
MAXIMO_DIAS_CONSULTA = 31
DURACAO_PADRAO = 60


def dia_semana(momento):
    return (momento.weekday() + 1) % 7


def _hora(texto):
    try:
        if not isinstance(texto, str) or len(texto) != 5:
            raise ValueError()
        return time.fromisoformat(texto)
    except ValueError:
        raise ErroNegocio('Horarios no formato HH:MM')


def _serializar(linha):
    return {'dia_semana': linha[0], 'inicio': linha[1].strftime('%H:%M'), 'fim': linha[2].strftime('%H:%M')}


def _janelas(cur, profissional_id):
    cur.execute('''SELECT DIA_SEMANA, HORA_INICIO, HORA_FIM FROM DISPONIBILIDADE
        WHERE PROFISSIONAL_ID = ? ORDER BY DIA_SEMANA, HORA_INICIO''', (profissional_id,))
    return cur.fetchall()


def _profissional_ativo(cur, profissional_id):
    cur.execute('''SELECT 1 FROM PROFISSIONAL p JOIN USUARIO u ON u.ID_USUARIO = p.USUARIO_ID
        WHERE p.USUARIO_ID = ? AND u.ATIVO = TRUE''', (profissional_id,))
    if cur.fetchone() is None:
        raise ErroNegocio('Profissional não encontrado', 404)


def filtro_sql(coluna_profissional, inicio, fim):
    """Condicao SQL: o intervalo cabe numa janela do profissional. Quem ainda nao cadastrou
    nenhuma janela aceita qualquer horario (comportamento de antes da F1)."""
    # ponytail: uma sessao nao atravessa a meia-noite; dia diferente nunca casa com janela
    mesmo_dia = inicio.date() == fim.date()
    sql = f'''(NOT EXISTS (SELECT 1 FROM DISPONIBILIDADE d WHERE d.PROFISSIONAL_ID = {coluna_profissional})
        OR EXISTS (SELECT 1 FROM DISPONIBILIDADE d WHERE d.PROFISSIONAL_ID = {coluna_profissional}
            AND d.DIA_SEMANA = ? AND d.HORA_INICIO <= ? AND d.HORA_FIM >= ?))'''
    return sql, [dia_semana(inicio) if mesmo_dia else -1, inicio.time(), fim.time() if mesmo_dia else inicio.time()]


def listar(profissional_id):
    with transacao() as cur:
        _profissional_ativo(cur, profissional_id)
        return [_serializar(linha) for linha in _janelas(cur, profissional_id)]


def validar(janelas):
    if not isinstance(janelas, list) or len(janelas) > MAXIMO_JANELAS:
        raise ErroNegocio(f'Envie janelas como lista de ate {MAXIMO_JANELAS} itens')
    limpas = []
    for janela in janelas:
        if not isinstance(janela, dict) or set(janela) != {'dia_semana', 'inicio', 'fim'}:
            raise ErroNegocio('Cada janela tem exatamente dia_semana, inicio e fim')
        dia = janela['dia_semana']
        if type(dia) is not int or not 0 <= dia <= 6:
            raise ErroNegocio('dia_semana deve ser inteiro de 0 (domingo) a 6 (sabado)')
        inicio, fim = _hora(janela['inicio']), _hora(janela['fim'])
        if fim <= inicio:
            raise ErroNegocio('fim deve ser posterior ao inicio')
        limpas.append((dia, inicio, fim))
    limpas.sort()
    for anterior, atual in zip(limpas, limpas[1:]):
        if anterior[0] == atual[0] and atual[1] < anterior[2]:
            raise ErroNegocio('Janelas do mesmo dia nao podem se sobrepor')
    return limpas


def gravar(cur, profissional_id, janelas):
    cur.execute('DELETE FROM DISPONIBILIDADE WHERE PROFISSIONAL_ID = ?', (profissional_id,))
    cur.executemany('''INSERT INTO DISPONIBILIDADE (PROFISSIONAL_ID, DIA_SEMANA, HORA_INICIO, HORA_FIM)
        VALUES (?, ?, ?, ?)''', [(profissional_id, *janela) for janela in janelas])


def substituir(profissional_id, dados):
    if not isinstance(dados, dict) or set(dados) != {'janelas'}:
        raise ErroNegocio('Envie {"janelas": [...]}')
    janelas = validar(dados['janelas'])
    with transacao() as cur:
        gravar(cur, profissional_id, janelas)
    return [_serializar(janela) for janela in janelas]


def janelas_do_cadastro(dias):
    """Dias marcados no cadastro ('Segunda', 'Terca'...) viram janelas no horario padrao."""
    return [(NOMES_DIAS[dia.upper()], *PADRAO_CADASTRO) for dia in dias]


def _ler_dia(texto, padrao):
    if texto is None:
        return padrao
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        raise ErroNegocio('Datas no formato AAAA-MM-DD')


def horarios_livres(profissional_id, de=None, ate=None, duracao=None):
    """Horarios de `duracao` minutos dentro das janelas, sem sessao marcada e no futuro."""
    de = _ler_dia(de, date.today())
    ate = _ler_dia(ate, de + timedelta(days=13))
    if ate < de or (ate - de).days >= MAXIMO_DIAS_CONSULTA:
        raise ErroNegocio(f'Periodo de 1 a {MAXIMO_DIAS_CONSULTA} dias, com ate depois de de')
    try:
        duracao = DURACAO_PADRAO if duracao is None else int(duracao)
    except ValueError:
        duracao = 0
    if not 30 <= duracao <= 120:
        raise ErroNegocio('duracao deve ser de 30 a 120 minutos')

    with transacao() as cur:
        _profissional_ativo(cur, profissional_id)
        janelas = _janelas(cur, profissional_id)
        cur.execute('''SELECT DATA_HORA_INICIO, DATA_HORA_FIM FROM SESSAO
            WHERE PROFISSIONAL_ID = ? AND STATUS <> 'CANCELADO'
              AND DATA_HORA_INICIO < ? AND DATA_HORA_FIM > ?''',
                    (profissional_id, datetime.combine(ate + timedelta(days=1), time()), datetime.combine(de, time())))
        ocupados = cur.fetchall()

    agora = datetime.now()
    passo = timedelta(minutes=duracao)
    livres = []
    dia = de
    while dia <= ate:
        for semana, hora_inicio, hora_fim in janelas:
            if semana != dia_semana(dia):
                continue
            inicio, limite = datetime.combine(dia, hora_inicio), datetime.combine(dia, hora_fim)
            while inicio + passo <= limite:
                fim = inicio + passo
                if inicio >= agora and not any(o_ini < fim and o_fim > inicio for o_ini, o_fim in ocupados):
                    livres.append({'inicio': inicio.isoformat(timespec='minutes'), 'fim': fim.isoformat(timespec='minutes')})
                inicio = fim
        dia += timedelta(days=1)
    return {'duracao': duracao, 'de': de.isoformat(), 'ate': ate.isoformat(), 'horarios': livres}
