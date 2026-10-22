# Assistente de IA: validacao, ferramentas no banco real e o loop com o modelo simulado (o CI nao tem chave do Groq).
import json
from datetime import date, timedelta

import pytest

from apoio import PACIENTE, PROFISSIONAL, checar, executar
from services import assistente_service
from services.erros import ErroNegocio


@pytest.fixture
def janela_amanha(agenda_vazia):
    amanha = date.today() + timedelta(days=1)
    executar("INSERT INTO DISPONIBILIDADE (PROFISSIONAL_ID, DIA_SEMANA, HORA_INICIO, HORA_FIM) VALUES (?, ?, '09:00', '10:00')",
             (PROFISSIONAL, (amanha.weekday() + 1) % 7))
    return amanha.isoformat()


def test_rota_valida_corpo_e_papel(anonimo, paciente, profissional):
    corpo = {'mensagens': [{'role': 'user', 'content': 'oi'}]}
    checar(anonimo.post('/api/assistente/', json=corpo), 401, 'error')
    checar(profissional.post('/api/assistente/', json=corpo), 403, 'error')
    for invalido in ({}, {'mensagens': []}, {'mensagens': corpo['mensagens'], 'usuario_id': 1},
                     {'mensagens': [{'role': 'system', 'content': 'x'}]},
                     {'mensagens': [{'role': 'user', 'content': 'oi'}, {'role': 'assistant', 'content': 'ola'}]},
                     {'mensagens': [{'role': 'user', 'content': 'x' * 2001}]}):
        checar(paciente.post('/api/assistente/', json=invalido), 400, 'error')


def test_ferramentas(janela_amanha):
    encontrados = assistente_service.executar_ferramenta('buscar_profissionais', {'especialidade': 'Psicologia'}, PACIENTE)
    assert encontrados and set(encontrados[0]) == set(assistente_service.CAMPOS_PROFISSIONAL)

    livres = assistente_service.executar_ferramenta('horarios_livres', {'id_profissional': PROFISSIONAL, 'de': janela_amanha,
                                                                        'ate': janela_amanha}, PACIENTE)
    assert livres['horarios'] == [{'inicio': f'{janela_amanha}T09:00', 'fim': f'{janela_amanha}T10:00'}]

    proposta = assistente_service.executar_ferramenta(
        'propor_agendamento', {'id_profissional': PROFISSIONAL, 'inicio': f'{janela_amanha}T09:00', 'fim': f'{janela_amanha}T10:00'}, PACIENTE)
    assert proposta == {'id_profissional': PROFISSIONAL, 'timestamp_inicio': f'{janela_amanha}T09:00',
                        'timestamp_fim': f'{janela_amanha}T10:00'}
    with pytest.raises(ErroNegocio):
        assistente_service.executar_ferramenta(
            'propor_agendamento', {'id_profissional': PROFISSIONAL, 'inicio': f'{janela_amanha}T09:30', 'fim': f'{janela_amanha}T10:30'}, PACIENTE)


def _chamada(id_, nome, argumentos):
    return {'id': id_, 'type': 'function', 'function': {'name': nome, 'arguments': argumentos}}


def test_loop_executa_ferramentas_e_devolve_proposta(monkeypatch, paciente, janela_amanha):
    pedido = json.dumps({'id_profissional': PROFISSIONAL, 'inicio': f'{janela_amanha}T09:00', 'fim': f'{janela_amanha}T10:00'})
    respostas = [
        {'content': None, 'tool_calls': [_chamada('t1', 'propor_agendamento', pedido), _chamada('t2', 'horarios_livres', '{')]},
        {'content': 'Confirme no botao abaixo.'},
    ]
    enviadas = []

    def chamar(mensagens):
        enviadas.append(list(mensagens))
        return respostas.pop(0)

    monkeypatch.setattr(assistente_service, '_chamar', chamar)

    corpo = checar(paciente.post('/api/assistente/', json={'mensagens': [{'role': 'user', 'content': 'quero marcar amanha 9h'}]}),
                   200, 'resposta', 'agendamento')
    assert corpo['resposta'] == 'Confirme no botao abaixo.'
    assert corpo['agendamento']['timestamp_inicio'] == f'{janela_amanha}T09:00'
    assert enviadas[0][0]['role'] == 'system'
    proposta, invalida = enviadas[1][-2:]
    assert proposta['tool_call_id'] == 't1' and not proposta['content'].startswith('Erro')
    # JSON quebrado do modelo vira erro para ele, nao 500
    assert invalida['tool_call_id'] == 't2' and invalida['content'].startswith('Erro')
