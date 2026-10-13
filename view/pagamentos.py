import json
import math
import os
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, request
from jwt import ExpiredSignatureError, InvalidTokenError

from database.db import get_connection
from funcao import decodificar_token

pagamentos_bp = Blueprint('pagamentos', __name__, url_prefix='/api/pagamentos')

ARKHE_BASE_URL = os.getenv(
    'ARKHE_BASE_URL',
    'https://arkhe-backend.zbbquj.easypanel.host'
).rstrip('/')


def _token_payload():
    token = request.cookies.get('access_token')
    if not token:
        return None, (jsonify({'error': 'Token de autenticacao necessario'}), 401)

    try:
        return decodificar_token(token), None
    except (ExpiredSignatureError, InvalidTokenError):
        return None, (jsonify({'error': 'Token invalido ou expirado'}), 401)


def _arkhe_request(method, path, body=None):
    client_id = os.getenv('ARKHE_CLIENT_ID') or os.getenv('CLIENT_ID')
    client_secret = os.getenv('ARKHE_CLIENT_SECRET') or os.getenv('CLIENT_SECRET')
    if not client_id or not client_secret:
        raise RuntimeError('Credenciais da Arkhé nao configuradas')

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
        raise RuntimeError('Nao foi possivel conectar a Arkhé')
    except ValueError:
        raise RuntimeError('Arkhé retornou uma resposta invalida')

    if not isinstance(corpo, dict):
        raise RuntimeError('Arkhé retornou uma resposta invalida')
    return status, corpo


@pagamentos_bp.route('/cobranca', methods=['POST'])
def criar_cobranca():
    payload, erro = _token_payload()
    if erro:
        return erro
    if payload.get('usuario_role') != 'PACIENTE':
        return jsonify({'error': 'Somente pacientes podem pagar consultas'}), 403

    dados = request.get_json(silent=True) or {}
    sessao_id = dados.get('id_sessao')
    if not sessao_id:
        return jsonify({'error': 'id_sessao e obrigatorio'}), 400

    con = None
    cur = None
    try:
        con = get_connection()
        cur = con.cursor()
        cur.execute('''
            SELECT STATUS, VALOR_CENTAVOS
            FROM SESSAO
            WHERE SESSAO_ID = ? AND PACIENTE_ID = ?
        ''', (sessao_id, payload.get('id_usuario')))
        sessao = cur.fetchone()
        if sessao is None:
            return jsonify({'error': 'Sessao nao encontrada'}), 404
        if sessao[0] == 'CANCELADO':
            return jsonify({'error': 'Nao e possivel pagar uma sessao cancelada'}), 400

        status, resposta = _arkhe_request(
            'POST',
            '/api/v1/cobrancas/pix',
            # Arkhe recebe reais; VALOR_CENTAVOS permanece inteiro no banco.
            {'valor': float(Decimal(str(sessao[1])) / 100)},
        )
        if status >= 400:
            return jsonify({'error': 'Arkhé nao criou a cobranca', 'detalhes': resposta}), 502

        valor = resposta.get('valor')
        try:
            valor_retornado = Decimal(str(valor))
        except InvalidOperation:
            valor_retornado = Decimal("NaN")
        if not valor_retornado.is_finite() or valor_retornado * 100 != Decimal(str(sessao[1])):
            return jsonify({'error': 'Arkhé retornou um valor invalido'}), 502

        return jsonify({
            'message': 'Cobranca Pix criada com sucesso',
            'cobranca': resposta,
            'id_sessao': sessao_id,
        }), 201
    except RuntimeError as erro_runtime:
        return jsonify({'error': str(erro_runtime)}), 503
    except Exception as erro_interno:
        print(f'[{__name__}]: {erro_interno}')
        return jsonify({'error': 'Internal Server Error'}), 500
    finally:
        if cur is not None:
            cur.close()
        if con is not None:
            con.close()


@pagamentos_bp.route('/cobranca/<int:id_cobranca>', methods=['GET'])
def consultar_cobranca(id_cobranca):
    _, erro = _token_payload()
    if erro:
        return erro

    try:
        status, resposta = _arkhe_request('GET', f'/api/v1/cobrancas/pix/{id_cobranca}')
        if status >= 400:
            return jsonify({'error': 'Arkhé nao consultou a cobranca', 'detalhes': resposta}), 502
        if resposta.get('status') not in (0, 1):
            return jsonify({'error': 'Arkhé retornou status de pagamento desconhecido'}), 502
        return jsonify({'cobranca': resposta}), 200
    except RuntimeError as erro_runtime:
        return jsonify({'error': str(erro_runtime)}), 503


@pagamentos_bp.route('/financeiro', methods=['GET'])
def financeiro():
    payload, erro = _token_payload()
    if erro:
        return erro
    if payload.get('usuario_role') not in ('PSICOLOGO', 'PSIQUIATRA'):
        return jsonify({'error': 'Somente profissionais podem ver o financeiro'}), 403

    dias = request.args.get('dias', '30')
    # 365 alimenta o historico mensal da carteira
    if dias not in ('7', '30', '90', '365'):
        return jsonify({'error': 'dias deve ser 7, 30, 90 ou 365'}), 400

    hoje = date.today()
    periodo = urlencode({
        'data_inicio': (hoje - timedelta(days=int(dias) - 1)).isoformat(),
        'data_fim': hoje.isoformat(),
    })

    try:
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
                return jsonify({'error': 'Arkhé nao retornou o financeiro', 'detalhes': resposta}), 502
            respostas[chave] = resposta
    except RuntimeError as erro_runtime:
        return jsonify({'error': str(erro_runtime)}), 503

    saldo = _numero(respostas['saldo'].get('saldo'))
    resumo = {campo: _numero(respostas['resumo'].get(campo))
              for campo in ('total_receitas', 'total_despesas', 'saldo_periodo')}
    movimentacoes = respostas['movimentacoes'].get('movimentacoes')
    if saldo is None or None in resumo.values() or not isinstance(movimentacoes, list):
        return jsonify({'error': 'Arkhé retornou dados financeiros invalidos'}), 502

    return jsonify({
        'saldo': saldo,
        'conta': _conta(respostas['conta']),
        'resumo': resumo,
        # Um registro malformado nao derruba o dashboard: so fica de fora
        'movimentacoes': [m for m in map(_movimentacao, movimentacoes) if m],
    }), 200


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
