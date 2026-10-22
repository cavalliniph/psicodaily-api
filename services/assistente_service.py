import json
import os
from datetime import date
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from services import consultas_service, disponibilidade_service, profissionais_service
from services.erros import ErroNegocio

# Gemini no plano gratuito, pelo endpoint no formato da OpenAI (trocado do Groq em 22/10/2026, que era lento).
# Outro provedor compativel = trocar URL, modelo e a variavel da chave.
URL_LLM = 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
# 3.5 Flash: ~1,3 s por rodada com ferramentas em 22/10/2026; o 3.8 nao aceita 'minimal' e vivia sobrecarregado (503)
MODELO = 'gemini-3.5-flash'
MAXIMO_MENSAGENS = 40
MAXIMO_CARACTERES = 2000
MAXIMO_RODADAS = 8
MAXIMO_HORARIOS = 20

SISTEMA = '''Voce e o assistente do PsicoDaily, plataforma que conecta pacientes a psicologos e psiquiatras.
Fale em portugues do Brasil, com frases curtas e acolhedoras.

Voce ajuda o paciente a: entender como a plataforma funciona, encontrar profissionais, ver horarios livres e montar um agendamento.
As ferramentas usam precos em centavos; para o paciente, mostre sempre em reais (15000 = R$ 150,00).
Use as ferramentas para qualquer dado de profissionais, horarios ou consultas; nunca invente nomes, precos ou horarios.
Para agendar, chame propor_agendamento: o paciente confirma no botao que aparece na tela. Nunca diga que a consulta ja foi marcada.

Como a plataforma funciona:
- Questionario inicial (Perfil > Preferencias): melhora as recomendacoes de profissionais.
- Busca: filtros por especialidade, abordagem, modalidade, preco, idioma, area de atuacao, avaliacao, experiencia e disponibilidade.
- Favoritos: o paciente salva profissionais e ve o proximo horario livre de cada um.
- Lista de espera: se nao houver horario, o paciente entra na lista do profissional e e avisado quando uma vaga abrir (a vaga nao fica reservada).
- Pagamento: na tela da consulta, por PIX, boleto ou cartao (credito ou debito), todos pelo banco Arkhé. O boleto vai para o CPF do paciente, que precisa ter conta na Arkhé, e vence no dia da consulta; o cartao precisa ser emitido pela Arkhé. A consulta passa de AGENDADO para CONFIRMADO quando o pagamento e confirmado (no cartao, na hora).
- Cancelamento: o paciente cancela pela tela da consulta ate 15 minutos antes do horario, com reembolso integral do que pagou; depois disso nao da mais para cancelar. Se o profissional cancelar, o reembolso tambem e integral. O reembolso e devolvido pela equipe da plataforma.
- Reagendamento: o paciente cancela e marca outro horario, ou pede ao profissional pelo chat.
- Chat: liberado entre paciente e profissional depois que existe uma consulta; aceita texto, PDF e imagens ate 10 MB.
- Videochamada: pelo botao de entrar na sala da consulta, no horario marcado.

Limites:
- Voce nao faz atendimento psicologico, diagnostico nem indica medicacao. Acolha e sugira um profissional.
- Se a pessoa falar em se machucar, suicidio ou risco imediato, oriente a ligar 188 (CVV, 24h) ou 192 (SAMU) agora, antes de qualquer outra coisa.
- Assuntos fora da plataforma e da saude mental: diga gentilmente que so ajuda com o PsicoDaily.'''

FERRAMENTAS = [
    {
        'name': 'buscar_profissionais',
        'description': 'Busca profissionais ativos por filtros. Todos opcionais; precos em centavos. Devolve ate 5.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'nome': {'type': 'string'},
                'especialidade': {'type': 'string', 'enum': ['Psicologia', 'Psiquiatria']},
                'abordagem': {'type': 'string', 'description': 'Ex.: TCC, Psicanalise, Humanista'},
                'modalidade': {'type': 'string', 'enum': ['Online', 'Presencial']},
                'preco_max': {'type': 'integer', 'description': 'Centavos, ex.: 15000 = R$ 150'},
                'idioma': {'type': 'string'},
                'area_atuacao': {'type': 'string', 'description': 'Ex.: Ansiedade, Depressao'},
                'avaliacao_min': {'type': 'number'},
                'ordenar': {'type': 'string', 'enum': ['preco', 'avaliacao', 'experiencia']},
            },
            'additionalProperties': False,
        },
    },
    {
        'name': 'recomendados',
        'description': 'Profissionais mais adequados ao questionario inicial do paciente.',
        'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
    },
    {
        'name': 'horarios_livres',
        'description': 'Horarios livres de um profissional. Datas AAAA-MM-DD; sem datas, os proximos 14 dias.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'id_profissional': {'type': 'integer'},
                'de': {'type': 'string'},
                'ate': {'type': 'string'},
            },
            'required': ['id_profissional'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'minhas_consultas',
        'description': 'Consultas do paciente (mais recentes primeiro), com status e valor.',
        'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
    },
    {
        'name': 'propor_agendamento',
        'description': 'Mostra ao paciente um botao para confirmar a consulta. Use um horario devolvido por horarios_livres.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'id_profissional': {'type': 'integer'},
                'inicio': {'type': 'string', 'description': 'AAAA-MM-DDTHH:MM'},
                'fim': {'type': 'string', 'description': 'AAAA-MM-DDTHH:MM'},
            },
            'required': ['id_profissional', 'inicio', 'fim'],
            'additionalProperties': False,
        },
    },
]

FERRAMENTAS_API = [{'type': 'function', 'function': {'name': f['name'], 'description': f['description'],
                                                     'parameters': f['input_schema']}} for f in FERRAMENTAS]

CAMPOS_PROFISSIONAL = ('id_usuario', 'nome', 'especialidade', 'abordagem', 'modalidade', 'preco_centavos',
                       'avaliacao', 'total_avaliacoes', 'areas_atuacao', 'idiomas', 'anos_experiencia')
CAMPOS_CONSULTA = ('sessao_id', 'profissional_nome', 'data_hora_inicio', 'data_hora_fim', 'status', 'valor_centavos')


def _chamar(mensagens):
    """Uma ida ao modelo; devolve a mensagem do assistente ({content, tool_calls})."""
    # low: quase tao rapido quanto minimal e escolhe melhor a ferramenta
    corpo = json.dumps({'model': MODELO, 'messages': mensagens, 'tools': FERRAMENTAS_API,
                        'reasoning_effort': 'low'}).encode()
    req = Request(URL_LLM, data=corpo, method='POST', headers={
        'Authorization': f'Bearer {os.getenv("GEMINI_API_KEY", "")}',
        'Content-Type': 'application/json',
        'User-Agent': 'psicodaily-api',
    })
    try:
        with urlopen(req, timeout=30) as resposta:
            return json.load(resposta)['choices'][0]['message']
    except HTTPError as erro:
        if erro.code == 429:
            raise ErroNegocio('Limite gratuito do assistente atingido, tente de novo mais tarde', 503)
        raise ErroNegocio('Assistente indisponivel no momento, tente de novo em instantes', 503)
    except OSError:
        # URLError e timeout de leitura
        raise ErroNegocio('Assistente indisponivel no momento, tente de novo em instantes', 503)


def _resumo(itens, campos):
    return [{campo: item.get(campo) for campo in campos} for item in itens]


def _propor(id_profissional, inicio, fim):
    inicio_dt, _ = consultas_service.ler_intervalo(inicio, fim)
    dia = inicio_dt.date().isoformat()
    livres = disponibilidade_service.horarios_livres(id_profissional, dia, dia)['horarios']
    # Vale o horario exato que a agenda devolveu; o POST /api/consultas revalida tudo na confirmacao.
    if not any(h['inicio'] == inicio[:16] and h['fim'] == fim[:16] for h in livres):
        raise ErroNegocio('Horario nao esta livre; consulte horarios_livres de novo')
    return {'id_profissional': id_profissional, 'timestamp_inicio': inicio[:16], 'timestamp_fim': fim[:16]}


def executar_ferramenta(nome, entrada, paciente_id):
    """Roda uma ferramenta pedida pelo modelo. O paciente vem sempre do token, nunca da entrada."""
    if nome == 'buscar_profissionais':
        filtros = {campo: str(valor) for campo, valor in entrada.items()}
        return _resumo(profissionais_service.buscar({**filtros, 'page_size': 5})['profissionais'], CAMPOS_PROFISSIONAL)
    if nome == 'recomendados':
        resultado = profissionais_service.recomendados(paciente_id, 'PACIENTE')
        return {'questionario_respondido': resultado['questionario_respondido'],
                'profissionais': _resumo(resultado['profissionais'][:5], CAMPOS_PROFISSIONAL)}
    if nome == 'horarios_livres':
        resultado = disponibilidade_service.horarios_livres(entrada['id_profissional'], entrada.get('de'), entrada.get('ate'))
        return {**resultado, 'horarios': resultado['horarios'][:MAXIMO_HORARIOS]}
    if nome == 'minhas_consultas':
        return _resumo(consultas_service.listar(paciente_id, 'PACIENTE')[:10], CAMPOS_CONSULTA)
    if nome == 'propor_agendamento':
        return _propor(entrada['id_profissional'], entrada['inicio'], entrada['fim'])
    raise ErroNegocio(f'Ferramenta desconhecida: {nome}')


def _validar(dados):
    if not isinstance(dados, dict) or set(dados) != {'mensagens'}:
        raise ErroNegocio('Envie {"mensagens": [{"role": "user", "content": "..."}]}')
    mensagens = dados['mensagens']
    if not isinstance(mensagens, list) or not 1 <= len(mensagens) <= MAXIMO_MENSAGENS:
        raise ErroNegocio(f'mensagens deve ser uma lista de 1 a {MAXIMO_MENSAGENS} itens')
    for mensagem in mensagens:
        if (not isinstance(mensagem, dict) or set(mensagem) != {'role', 'content'}
                or mensagem['role'] not in ('user', 'assistant')
                or not isinstance(mensagem['content'], str)
                or not 1 <= len(mensagem['content'].strip()) <= MAXIMO_CARACTERES):
            raise ErroNegocio(f'Cada mensagem tem role (user ou assistant) e content de 1 a {MAXIMO_CARACTERES} caracteres')
    if mensagens[0]['role'] != 'user' or mensagens[-1]['role'] != 'user':
        raise ErroNegocio('A conversa comeca e termina com mensagem do paciente')
    return [dict(m) for m in mensagens]


def conversar(paciente_id, papel, dados):
    if papel != 'PACIENTE':
        raise ErroNegocio('Assistente disponivel apenas para pacientes', 403)
    sistema = f'{SISTEMA}\n\nHoje: {date.today().isoformat()}'
    mensagens = [{'role': 'system', 'content': sistema}, *_validar(dados)]

    agendamento = None
    for _ in range(MAXIMO_RODADAS):
        resposta = _chamar(mensagens)
        chamadas = resposta.get('tool_calls') or []
        if not chamadas:
            return {'resposta': resposta.get('content') or '', 'agendamento': agendamento}

        # So os campos do protocolo voltam; campos extras do provedor (ex.: reasoning) podem dar 400. Os tool_calls
        # voltam intactos: no Gemini 3 eles levam a thought signature (extra_content), exigida na rodada seguinte.
        mensagens.append({'role': 'assistant', 'content': resposta.get('content') or '', 'tool_calls': chamadas})
        for chamada in chamadas:
            nome = chamada['function']['name']
            try:
                saida = executar_ferramenta(nome, json.loads(chamada['function']['arguments'] or '{}'), paciente_id)
                if nome == 'propor_agendamento':
                    agendamento = saida
                conteudo = json.dumps(saida, ensure_ascii=False, default=str)
            except ErroNegocio as erro:
                conteudo = f'Erro: {erro.mensagem}'
            except (ValueError, KeyError, TypeError):
                # Argumentos fora do schema: o modelo ve o erro e tenta de novo
                conteudo = 'Erro: argumentos invalidos para esta ferramenta'
            mensagens.append({'role': 'tool', 'tool_call_id': chamada['id'], 'name': nome, 'content': conteudo})

    raise ErroNegocio('O assistente nao concluiu a resposta, tente reformular a pergunta', 502)
