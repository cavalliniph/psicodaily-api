# Helpers dos testes. Os IDs sao os usuarios ficticios de database/seed.sql.
from app import app
from database.db import get_connection
from services.auth_service import gerar_token

PROFISSIONAL, PACIENTE, PSIQUIATRA, OUTRO_PACIENTE, ADMIN = 22, 23, 24, 25, 26
# Porta do fixture `servidor` (testes de WebSocket)
PORTA = 5057


def executar(sql, params=()):
    """Roda e commita; devolve fetchall() ou None se o comando nao tem resultado."""
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute(sql, params)
        linhas = cur.fetchall() if cur.description else None
        con.commit()
        return linhas
    finally:
        con.close()


def cliente(id_usuario, papel):
    c = app.test_client()
    with app.app_context():
        c.set_cookie('access_token', gerar_token({'id_usuario': id_usuario, 'usuario_role': papel}))
    return c


def checar(resposta, status, *chaves):
    corpo = resposta.get_json(silent=True) or {}
    assert resposta.status_code == status, (resposta.request.path, resposta.status_code, corpo)
    for chave in chaves:
        assert chave in corpo, (resposta.request.path, chave, corpo)
    return corpo
