import pytest

from apoio import ADMIN, OUTRO_PACIENTE, PACIENTE, PROFISSIONAL, PSIQUIATRA, cliente, executar
from app import app


@pytest.fixture
def anonimo():
    return app.test_client()


@pytest.fixture
def paciente():
    return cliente(PACIENTE, 'PACIENTE')


@pytest.fixture
def outro_paciente():
    return cliente(OUTRO_PACIENTE, 'PACIENTE')


@pytest.fixture
def profissional():
    return cliente(PROFISSIONAL, 'PSICOLOGO')


@pytest.fixture
def psiquiatra():
    return cliente(PSIQUIATRA, 'PSIQUIATRA')


@pytest.fixture
def admin():
    return cliente(ADMIN, 'ADMIN')


@pytest.fixture(autouse=True)
def ultima_auditoria():
    """Login, agendamento etc. gravam em AUDITORIA: todo teste apaga as linhas que criou."""
    ultima = executar('SELECT COALESCE(MAX(AUDITORIA_ID), 0) FROM AUDITORIA')[0][0]
    yield ultima
    executar('DELETE FROM AUDITORIA WHERE AUDITORIA_ID > ?', (ultima,))


@pytest.fixture
def ultima_notificacao():
    """Apaga as notificacoes criadas pelo teste."""
    ultima = executar('SELECT COALESCE(MAX(NOTIFICACAO_ID), 0) FROM NOTIFICACAO')[0][0]
    yield ultima
    executar('DELETE FROM NOTIFICACAO WHERE NOTIFICACAO_ID > ?', (ultima,))


@pytest.fixture
def sessoes():
    """Lista onde o teste guarda os SESSAO_ID que criou; a AVALIACAO sai junto (cascade)."""
    criadas = []
    yield criadas
    for sessao_id in criadas:
        executar('DELETE FROM SESSAO WHERE SESSAO_ID = ?', (sessao_id,))


@pytest.fixture
def encaminhamentos():
    criados = []
    yield criados
    for encaminhamento_id in criados:
        executar('DELETE FROM ENCAMINHAMENTO WHERE ENCAMINHAMENTO_ID = ?', (encaminhamento_id,))


@pytest.fixture
def agenda_vazia():
    """Agenda do profissional 22 vazia durante o teste e restaurada no fim."""
    original = executar('SELECT DIA_SEMANA, HORA_INICIO, HORA_FIM FROM DISPONIBILIDADE WHERE PROFISSIONAL_ID = ?',
                        (PROFISSIONAL,))
    executar('DELETE FROM DISPONIBILIDADE WHERE PROFISSIONAL_ID = ?', (PROFISSIONAL,))
    yield
    executar('DELETE FROM DISPONIBILIDADE WHERE PROFISSIONAL_ID = ?', (PROFISSIONAL,))
    for linha in original:
        executar('INSERT INTO DISPONIBILIDADE (PROFISSIONAL_ID, DIA_SEMANA, HORA_INICIO, HORA_FIM) VALUES (?, ?, ?, ?)',
                 (PROFISSIONAL, *linha))
