# Cria bancos temporarios em TEST_DB_DIR (padrao: pasta temporaria do sistema; no CI, uma pasta
# do container do Firebird) e apaga todos no fim. Nao toca no banco do .env.
import os
import shutil
import sys
import tempfile
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database'))
import migrar

PASTA_REAL = migrar.PASTA
DIR_BANCOS = os.getenv('TEST_DB_DIR', tempfile.gettempdir())


@pytest.fixture
def novo_banco(monkeypatch):
    """Aponta DB_DATABASE para um banco novo (so neste teste); apaga todos os criados no fim."""
    bancos = []

    def criar():
        caminho = f"{DIR_BANCOS.rstrip('/')}/teste_migrar_{uuid.uuid4().hex[:8]}.FDB"
        bancos.append(caminho)
        monkeypatch.setenv('DB_DATABASE', caminho)

    yield criar
    for caminho in bancos:
        monkeypatch.setenv('DB_DATABASE', caminho)
        try:
            migrar.conectar().drop_database()
        except Exception:
            pass


@pytest.fixture
def pasta_com(monkeypatch, tmp_path_factory):
    """Troca a pasta de migrations por uma com a 0001 real e os arquivos extras (nome, sql)."""
    def criar(*arquivos):
        pasta = tmp_path_factory.mktemp('migrations')
        shutil.copy(os.path.join(PASTA_REAL, '0001_inicial.sql'), pasta)
        for nome, sql in arquivos:
            (pasta / nome).write_text(sql, encoding='utf-8')
        monkeypatch.setattr(migrar, 'PASTA', str(pasta))
    return criar


def consulta(sql, params=()):
    con = migrar.conectar()
    try:
        cur = con.cursor()
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        con.close()


def tabelas():
    return {linha[0].strip() for linha in consulta(
        "SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0")}


def versoes():
    return [linha[0] for linha in consulta('SELECT VERSAO FROM SCHEMA_MIGRATION ORDER BY VERSAO')]


def test_parser_set_term_aspas_comentarios_e_comandos_do_isql():
    script = """
SET SQL DIALECT 3;
/* comentario; com ponto e virgula */
CREATE TABLE T (X VARCHAR(20) DEFAULT 'a;b--c');  -- fim de linha
COMMIT WORK;
SET TERM ^ ;
CREATE PROCEDURE P AS
BEGIN
  INSERT INTO T (X) VALUES ('it''s; ok');
END^
SET TERM ; ^
INSERT INTO T (X) VALUES ('z');
"""
    lista = migrar.comandos(script)
    assert len(lista) == 3, lista
    assert lista[0] == "CREATE TABLE T (X VARCHAR(20) DEFAULT 'a;b--c')", lista[0]
    assert lista[1].startswith('CREATE PROCEDURE P') and "'it''s; ok');\nEND" in lista[1], lista[1]
    with pytest.raises(ValueError):
        migrar.comandos('CREATE TABLE SEM_FIM (X INTEGER)')


def test_banco_novo_e_migration_quebrada_nao_deixa_nada(novo_banco, pasta_com):
    # Sem --criar falha; com --criar sobe o schema todo; rodar de novo nao faz nada
    novo_banco()
    pasta_com()
    assert migrar.main([]) == 1
    assert migrar.main(['--criar']) == 0
    assert {'USUARIO', 'PROFISSIONAL', 'SESSAO', 'SCHEMA_MIGRATION'} <= tabelas(), tabelas()
    assert versoes() == [1]
    assert migrar.main([]) == 0 and versoes() == [1]

    # Migration que quebra no meio nao deixa nada: nem a tabela, nem o registro
    pasta_com(('0002_boa.sql', 'CREATE TABLE BOA (ID INTEGER);'),
              ('0003_quebrada.sql', 'CREATE TABLE PELA_METADE (ID INTEGER);\nINSERT INTO NAO_EXISTE VALUES (1);'))
    assert migrar.main([]) == 1
    assert 'BOA' in tabelas() and 'PELA_METADE' not in tabelas(), tabelas()
    assert versoes() == [1, 2], versoes()
    # Corrigida, aplica na proxima execucao
    with open(os.path.join(migrar.PASTA, '0003_quebrada.sql'), 'w', encoding='utf-8') as arquivo:
        arquivo.write('CREATE TABLE PELA_METADE (ID INTEGER);')
    assert migrar.main([]) == 0 and versoes() == [1, 2, 3] and 'PELA_METADE' in tabelas()


def test_banco_existente_sem_controle_exige_baseline(novo_banco, pasta_com):
    # Como a producao antes da F0: tabelas, mas sem SCHEMA_MIGRATION
    novo_banco()
    pasta_com()
    assert migrar.main(['--criar']) == 0
    con = migrar.conectar()
    con.cursor().execute('DROP TABLE SCHEMA_MIGRATION')
    con.commit()
    con.close()
    assert migrar.main([]) == 1, 'banco com tabelas e sem controle deveria exigir --baseline'
    assert migrar.main(['--baseline', '1']) == 0 and versoes() == [1]
    assert migrar.main(['--baseline', '1']) == 1, '--baseline so vale uma vez'
    pasta_com(('0002_nova.sql', 'ALTER TABLE USUARIO ADD TESTE_MIGRAR SMALLINT;'))
    assert migrar.main([]) == 0 and versoes() == [1, 2]


@pytest.mark.parametrize('arquivos', [
    [('2_curto.sql', 'SELECT 1 FROM RDB$DATABASE;')],
    [('0002-hifen.sql', 'SELECT 1 FROM RDB$DATABASE;')],
    [('0002_Maiuscula.sql', 'SELECT 1 FROM RDB$DATABASE;')],
    [('0002_a.sql', ''), ('0002_b.sql', '')],
])
def test_nome_fora_do_padrao_ou_versao_repetida(pasta_com, arquivos):
    pasta_com(*arquivos)
    assert migrar.main(['--status']) == 1
