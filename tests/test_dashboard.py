# Features 4/27: painel do app por papel, montado com o que as outras rotas ja expoem.
from datetime import datetime, timedelta

from apoio import PACIENTE, PROFISSIONAL, executar


def nova_sessao(sessoes, dias, status):
    inicio = (datetime.now() + timedelta(days=dias)).replace(hour=10, minute=0, second=0, microsecond=0)
    sid = executar('''INSERT INTO SESSAO (PACIENTE_ID, PROFISSIONAL_ID, DATA_HORA_INICIO, DATA_HORA_FIM, STATUS, VALOR_CENTAVOS)
        VALUES (?, ?, ?, ?, ?, 15000) RETURNING SESSAO_ID''', (PACIENTE, PROFISSIONAL, inicio, inicio + timedelta(hours=1), status))[0][0]
    sessoes.append(sid)
    return sid


def test_painel_por_papel(anonimo, admin, paciente, profissional, sessoes):
    assert anonimo.get('/api/dashboard/').status_code == 401
    assert admin.get('/api/dashboard/').status_code == 403

    antes = profissional.get('/api/dashboard/').get_json()
    futura, passada = nova_sessao(sessoes, 400, 'AGENDADO'), nova_sessao(sessoes, -400, 'AGENDADO')
    executar('''INSERT INTO PAGAMENTO (SESSAO_ID, ID_COBRANCA_ARKHE, VALOR_CENTAVOS, STATUS, PAGO_EM)
        VALUES (?, ?, 15000, 'PAGO', CURRENT_TIMESTAMP)''', (futura, 900000000 + futura))

    r = paciente.get('/api/dashboard/')
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'private, no-store'
    painel = r.get_json()
    assert {'papel', 'proximas_sessoes', 'nao_lidas', 'pagamentos', 'favoritos'} <= set(painel), painel
    ids = [s['sessao_id'] for s in painel['proximas_sessoes']]
    assert passada not in ids
    assert painel['pagamentos'][0]['sessao_id'] == futura and painel['pagamentos'][0]['status'] == 'PAGO'

    painel = profissional.get('/api/dashboard/').get_json()
    assert {'proximas_sessoes', 'nao_lidas', 'ganhos_mes_centavos', 'atendimentos_mes', 'pacientes'} <= set(painel), painel
    assert painel['ganhos_mes_centavos'] == antes['ganhos_mes_centavos'] + 15000
