import json
import math
import os
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from database.db import transacao
from services import notificacoes_service
from services.erros import ErroNegocio

ARKHE_BASE_URL = os.getenv(
    'ARKHE_BASE_URL',
    'https://arkhe-backend.zbbquj.easypanel.host'
).rstrip('/')


def _arkhe_request(method, path, body=None):
    client_id = os.getenv('ARKHE_CLIENT_ID') or os.getenv('CLIENT_ID')
    client_secret = os.getenv('ARKHE_CLIENT_SECRET') or os.getenv('CLIENT_SECRET')
    if not client_id or not client_secret:
        raise ErroNegocio('Credenciais da Arkhé nao configuradas', 503)

    headers = {
        'X-Client-ID': client_id,
        'X-Client-Secret': client_secret,
        'Accept': 'application/json',
    }
    if method == 'POST':
        headers['Content-Type'] = 'application/json'

    dados = json.dumps(body).encode('utf-8') if body is not None else None
    req = Request(f'{ARKHE_BASE_URL}{path}', data=dados, method=method, headers=headers)
    try:
        with urlopen(req, timeout=15) as resposta:
            status, corpo = resposta.status, json.loads(resposta.read().decode('utf-8'))
    except HTTPError as erro:
        corpo = erro.read().decode('utf-8', errors='replace')
        try:
            detalhe = json.loads(corpo)
        except json.JSONDecodeError:
            detalhe = None
        if not isinstance(detalhe, dict):
            # Erros fora da API (404 do Flask, proxy) chegam em HTML
            detalhe = {'error': f'Arkhé respondeu HTTP {erro.code}'}
        return erro.code, detalhe
    except (URLError, OSError):
        # OSError cobre o timeout de leitura, que nao vira URLError
        raise ErroNegocio('Nao foi possivel conectar a Arkhé', 503)
    except ValueError:
        raise ErroNegocio('Arkhé retornou uma resposta invalida', 503)

    if not isinstance(corpo, dict):
        raise ErroNegocio('Arkhé retornou uma resposta invalida', 503)
    return status, corpo


def criar_cobranca(paciente_id, papel, sessao_id):
    if papel != 'PACIENTE':
        raise ErroNegocio('Somente pacientes podem pagar consultas', 403)
    if not sessao_id:
        raise ErroNegocio('id_sessao e obrigatorio')

    with transacao() as cur:
        cur.execute('''
            SELECT STATUS, VALOR_CENTAVOS
            FROM SESSAO
            WHERE SESSAO_ID = ? AND PACIENTE_ID = ?
        ''', (sessao_id, paciente_id))
        sessao = cur.fetchone()
        cur.execute('SELECT ID_COBRANCA_ARKHE, STATUS FROM PAGAMENTO WHERE SESSAO_ID = ? ORDER BY PAGAMENTO_ID DESC',
                    (sessao_id,))
        pagamentos = cur.fetchall()
    if sessao is None:
        raise ErroNegocio('Sessao nao encontrada', 404)
    if sessao[0] == 'CANCELADO':
        raise ErroNegocio('Nao e possivel pagar uma sessao cancelada')
    if any(status == 'PAGO' for _, status in pagamentos):
        raise ErroNegocio('Esta sessao ja foi paga', 409)
    if pagamentos:
        # Reaproveita o Pix pendente: duas cobrancas abertas deixariam o paciente pagar duas vezes
        return consultar_cobranca(paciente_id, pagamentos[0][0])

    status, resposta = _arkhe_request(
        'POST',
        '/api/v1/cobrancas/pix',
        # Arkhe recebe reais; VALOR_CENTAVOS permanece inteiro no banco.
        {'valor': float(Decimal(str(sessao[1])) / 100)},
    )
    if status >= 400:
        raise ErroNegocio('Arkhé nao criou a cobranca', 502, detalhes=resposta)

    try:
        valor_retornado = Decimal(str(resposta.get('valor')))
    except InvalidOperation:
        valor_retornado = Decimal("NaN")
    if not valor_retornado.is_finite() or valor_retornado * 100 != Decimal(str(sessao[1])):
        raise ErroNegocio('Arkhé retornou um valor invalido', 502)
    if not isinstance(resposta.get('id_cobranca'), int):
        raise ErroNegocio('Arkhé retornou uma cobranca sem id', 502)

    with transacao() as cur:
        cur.execute('INSERT INTO PAGAMENTO (SESSAO_ID, ID_COBRANCA_ARKHE, VALOR_CENTAVOS) VALUES (?, ?, ?)',
                    (sessao_id, resposta['id_cobranca'], sessao[1]))
    return resposta


def consultar_cobranca(usuario_id, id_cobranca):
    with transacao() as cur:
        cur.execute('''SELECT p.STATUS, s.SESSAO_ID, s.PROFISSIONAL_ID, s.DATA_HORA_INICIO
            FROM PAGAMENTO p JOIN SESSAO s ON s.SESSAO_ID = p.SESSAO_ID
            WHERE p.ID_COBRANCA_ARKHE = ? AND ? IN (s.PACIENTE_ID, s.PROFISSIONAL_ID)''', (id_cobranca, usuario_id))
        pagamento = cur.fetchone()
    if pagamento is None:
        raise ErroNegocio('Cobranca nao encontrada', 404)

    status, resposta = _arkhe_request('GET', f'/api/v1/cobrancas/pix/{id_cobranca}')
    if status >= 400:
        raise ErroNegocio('Arkhé nao consultou a cobranca', 502, detalhes=resposta)
    if resposta.get('status') not in (0, 1):
        raise ErroNegocio('Arkhé retornou status de pagamento desconhecido', 502)
    if resposta['status'] == 1 and pagamento[0] == 'PENDENTE':
        _confirmar(id_cobranca, *pagamento[1:])
    return resposta


def _confirmar(id_cobranca, sessao_id, profissional_id, inicio):
    # shortcut: o status so muda quando alguem consulta a cobranca; webhook ou job (F7) se a Arkhé tiver
    with transacao() as cur:
        cur.execute('''UPDATE PAGAMENTO SET STATUS = 'PAGO', PAGO_EM = CURRENT_TIMESTAMP
            WHERE ID_COBRANCA_ARKHE = ? AND STATUS = 'PENDENTE' RETURNING PAGAMENTO_ID''', (id_cobranca,))
        if cur.fetchone()[0] is None:
            return  # outra requisicao confirmou antes
        cur.execute("UPDATE SESSAO SET STATUS = 'CONFIRMADO' WHERE SESSAO_ID = ? AND STATUS = 'AGENDADO'", (sessao_id,))
        emails = [notificacoes_service.notificar(
            cur, profissional_id, 'PAGAMENTO_CONFIRMADO', 'Pagamento confirmado',
            f'O paciente pagou a sessão de {inicio.strftime("%d/%m/%Y às %H:%M")}.', {'sessao_id': sessao_id})]
    notificacoes_service.enviar_emails(emails)


def financeiro(papel, dias):
    if papel not in ('PSICOLOGO', 'PSIQUIATRA'):
        raise ErroNegocio('Somente profissionais podem ver o financeiro', 403)
    # 365 alimenta o historico mensal da carteira
    if dias not in ('7', '30', '90', '365'):
        raise ErroNegocio('dias deve ser 7, 30, 90 ou 365')

    hoje = date.today()
    periodo = urlencode({
        'data_inicio': (hoje - timedelta(days=int(dias) - 1)).isoformat(),
        'data_fim': hoje.isoformat(),
    })

    # ponytail: credencial global do .env, todos os profissionais veem a mesma conta PJ
    respostas = {}
    for chave, caminho in (
        ('saldo', '/api/v1/saldo'),
        ('conta', '/api/v1/conta'),
        ('resumo', '/api/v1/resumo-financeiro'),
        ('movimentacoes', f'/api/v1/movimentacoes?{periodo}'),
    ):
        status, resposta = _arkhe_request('GET', caminho)
        if status >= 400:
            raise ErroNegocio('Arkhé nao retornou o financeiro', 502, detalhes=resposta)
        respostas[chave] = resposta

    saldo = _numero(respostas['saldo'].get('saldo'))
    resumo = {campo: _numero(respostas['resumo'].get(campo))
              for campo in ('total_receitas', 'total_despesas', 'saldo_periodo')}
    movimentacoes = respostas['movimentacoes'].get('movimentacoes')
    if saldo is None or None in resumo.values() or not isinstance(movimentacoes, list):
        raise ErroNegocio('Arkhé retornou dados financeiros invalidos', 502)

    return {
        'saldo': saldo,
        'conta': _conta(respostas['conta']),
        'resumo': resumo,
        # Um registro malformado nao derruba o dashboard: so fica de fora
        'movimentacoes': [m for m in map(_movimentacao, movimentacoes) if m],
    }


def _conta(conta):
    # So o necessario para exibir; a Arkhé manda numero_conta como inteiro
    nome, agencia, numero = (str(conta.get(campo) or '') for campo in ('nome', 'agencia', 'numero_conta'))
    if not numero:
        return None
    return {'nome': nome, 'agencia': agencia, 'final': numero[-4:]}


def _numero(valor):
    if isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _movimentacao(item):
    if not isinstance(item, dict):
        return None
    valor = _numero(item.get('valor'))
    data = item.get('data_movimentacao')
    try:
        # A Arkhé manda microssegundos; nem todo navegador interpreta esse formato
        data = datetime.fromisoformat(str(data)).strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None
    if valor is None or item.get('tipo') not in ('entrada', 'saida'):
        return None
    return {
        'id_movimentacao': item.get('id_movimentacao'),
        'nome_contraparte': str(item.get('nome_contraparte') or 'Sem identificação'),
        'valor': valor,
        'data_movimentacao': data,
        'tipo': item['tipo'],
        'origem': str(item.get('origem') or ''),
    }
