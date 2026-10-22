import hashlib
import hmac
import json
import logging
import os
import re
import threading
from urllib.request import Request, urlopen

from database.db import transacao

logger = logging.getLogger(__name__)

# WAHA (github.com/devlikeapro/waha): WhatsApp nao oficial por HTTP, servico proprio no Northflank.
# Sem WAHA_URL (dev, CI) nada e enviado.
SESSAO = 'default'


def _waha(metodo, caminho, corpo=None):
    req = Request(f"{os.getenv('WAHA_URL', '').rstrip('/')}{caminho}", method=metodo,
                  data=json.dumps(corpo).encode() if corpo is not None else None,
                  headers={'X-Api-Key': os.getenv('WAHA_API_KEY', ''), 'Content-Type': 'application/json',
                           'Accept': 'application/json'})
    with urlopen(req, timeout=15) as resposta:
        return json.load(resposta)


def chat_id(telefone):
    """Telefone do cadastro ('(11) 99999-9999') -> chatId do WhatsApp ('5511999999999@c.us'); None se nao der."""
    digitos = re.sub(r'\D', '', telefone or '')
    if len(digitos) in (10, 11):
        digitos = '55' + digitos
    return f'{digitos}@c.us' if len(digitos) in (12, 13) else None


def _enviar(telefone, texto):
    # Aceita o chatId de quem mandou mensagem (inclusive @lid) ou o telefone do cadastro
    destino = telefone if '@' in (telefone or '') else chat_id(telefone)
    if not destino or not os.getenv('WAHA_URL'):
        return
    try:
        _waha('POST', '/api/sendText', {'session': SESSAO, 'chatId': destino, 'text': texto})
    except Exception:
        # Melhor esforco, como o e-mail: o aviso ja esta gravado em NOTIFICACAO
        logger.exception('WhatsApp nao enviado para %s', destino)


def enviar_async(telefone, texto):
    threading.Thread(target=_enviar, args=(telefone, texto), daemon=True).start()


def assinatura_valida(corpo, assinatura):
    """HMAC sha512 do corpo bruto com WAHA_HMAC_KEY (header X-Webhook-Hmac do WAHA)."""
    chave = os.getenv('WAHA_HMAC_KEY')
    if not chave or not assinatura:
        return False
    esperado = hmac.new(chave.encode(), corpo, hashlib.sha512).hexdigest()
    return hmac.compare_digest(esperado, assinatura)


def telefone_do_remetente(remetente):
    """'5511999999999@c.us' -> '5511999999999'. O WhatsApp tambem manda ids ocultos (@lid): o WAHA traduz."""
    if remetente.endswith('@c.us'):
        return remetente.split('@')[0]
    if remetente.endswith('@lid'):
        try:
            return (_waha('GET', f'/api/{SESSAO}/lids/{remetente.split("@")[0]}').get('pn') or '').split('@')[0] or None
        except Exception:
            logger.exception('Nao traduziu o @lid %s', remetente)
    return None


def usuario_por_telefone(telefone):
    """(id, papel, nome) de quem tem esse numero no cadastro, comparando DDD + 8 ultimos digitos.

    Os 8 ultimos cobrem o celular com ou sem o 9 da frente, que o WhatsApp omite em numeros antigos.
    ponytail: varre os usuarios ativos em Python; coluna normalizada e indice se o cadastro crescer
    """
    digitos = re.sub(r'\D', '', telefone or '')
    if digitos.startswith('55') and len(digitos) in (12, 13):
        digitos = digitos[2:]
    if len(digitos) not in (10, 11):
        return None
    chave = (digitos[:2], digitos[-8:])
    with transacao() as cur:
        cur.execute('SELECT ID_USUARIO, USUARIO_ROLE, NOME, TELEFONE FROM USUARIO WHERE ATIVO = TRUE')
        for usuario_id, papel, nome, cadastrado in cur.fetchall():
            numero = re.sub(r'\D', '', cadastrado or '')
            if len(numero) in (10, 11) and (numero[:2], numero[-8:]) == chave:
                return usuario_id, papel, nome
    return None
