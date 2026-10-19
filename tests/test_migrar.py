# Precisa do Firebird no ar: python tests/test_migrar.py
# Cria bancos temporarios em TEST_DB_DIR (padrao: pasta temporaria do sistema; no CI, uma pasta
# do container do Firebird) e apaga todos no fim. Nao toca no banco do .env.
import os
import shutil
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database'))
import migrar

PASTA_REAL = migrar.PASTA
DIR_BANCOS = os.getenv('TEST_DB_DIR', tempfile.gettempdir())
bancos, pastas = [], []


def novo_banco():
    caminho = f"{DIR_BANCOS.rstrip('/')}/teste_migrar_{uuid.uuid4().hex[:8]}.FDB"
    bancos.append(caminho)
    os.environ['DB_DATABASE'] = caminho
    return caminho


def pasta_com(*arquivos):
    """Pasta de migrations com a 0001 real e os arquivos extras {nome: sql}."""
    pasta = tempfile.mkdtemp()
    pastas.append(pasta)
    shutil.copy(os.path.join(PASTA_REAL, '0001_inicial.sql'), pasta)
    for nome, sql in arquivos:
        with open(os.path.join(pasta, nome), 'w', encoding='utf-8') as arquivo:
            arquivo.write(sql)
    migrar.PASTA = pasta


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


# 1. Parser: SET TERM, aspas com ; e --, comentarios, comandos de sessao do isql
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
try:
    migrar.comandos('CREATE TABLE SEM_FIM (X INTEGER)')
    raise AssertionError('comando sem terminador deveria falhar')
except ValueError:
    pass

try:
    # 2. Banco novo: sem --criar falha; com --criar sobe o schema todo; rodar de novo nao faz nada
    novo_banco()
    pasta_com()
    assert migrar.main([]) == 1
    assert migrar.main(['--criar']) == 0
    assert {'USUARIO', 'PROFISSIONAL', 'SESSAO', 'SCHEMA_MIGRATION'} <= tabelas(), tabelas()
    assert versoes() == [1]
    assert migrar.main([]) == 0 and versoes() == [1]

    # 3. Migration que quebra no meio nao deixa nada: nem a tabela, nem o registro
    pasta_com(('0002_boa.sql', 'CREATE TABLE BOA (ID INTEGER);'),
              ('0003_quebrada.sql', 'CREATE TABLE PELA_METADE (ID INTEGER);\nINSERT INTO NAO_EXISTE VALUES (1);'))
    assert migrar.main([]) == 1
    assert 'BOA' in tabelas() and 'PELA_METADE' not in tabelas(), tabelas()
    assert versoes() == [1, 2], versoes()
    # Corrigida, aplica na proxima execucao
    with open(os.path.join(migrar.PASTA, '0003_quebrada.sql'), 'w', encoding='utf-8') as arquivo:
        arquivo.write('CREATE TABLE PELA_METADE (ID INTEGER);')
    assert migrar.main([]) == 0 and versoes() == [1, 2, 3] and 'PELA_METADE' in tabelas()

    # 4. Banco que ja existia (como producao hoje): sem tabela de controle
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

    # 5. Nomes fora do padrao e versao repetida
    for nome in ('2_curto.sql', '0002-hifen.sql', '0002_Maiuscula.sql'):
        pasta_com((nome, 'SELECT 1 FROM RDB$DATABASE;'))
        assert migrar.main(['--status']) == 1, nome
    pasta_com(('0002_a.sql', ''), ('0002_b.sql', ''))
    assert migrar.main(['--status']) == 1

    print('ok: migrations (parser, atomicidade, baseline e nomes)')
finally:
    migrar.PASTA = PASTA_REAL
    for caminho in bancos:
        os.environ['DB_DATABASE'] = caminho
        try:
            migrar.conectar().drop_database()
        except Exception:
            pass
    for pasta in pastas:
        shutil.rmtree(pasta, ignore_errors=True)
