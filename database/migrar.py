"""Aplica as migrations de database/migrations/ em ordem.

    python database/migrar.py                  aplica as pendentes
    python database/migrar.py --criar          antes, cria o banco vazio se ele nao existir
    python database/migrar.py --baseline 1     banco que ja existia: registra ate a 0001 como aplicada, sem executar
    python database/migrar.py --status         lista aplicadas e pendentes
    python database/migrar.py --criar --seed database/seed.sql   banco de dev/CI com dados ficticios

Conexao pelas mesmas variaveis do app (DB_HOST, DB_DATABASE, DB_USER, DB_PASSWORD, DB_CHARSET).
Cada arquivo roda numa transacao so, junto com o registro em SCHEMA_MIGRATION:
se um comando falha, nada daquele arquivo fica aplicado. Sai com codigo 1 em qualquer erro.
"""
import argparse
import os
import re
import sys

import fdb
from dotenv import load_dotenv

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
ARQUIVO = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
# Comandos de sessao do isql: nao sao SQL para o servidor
IGNORADOS = re.compile(r"^(SET\s+(SQL\s+DIALECT|NAMES|AUTODDL)\b|COMMIT(\s+WORK)?$)", re.I)


def conectar():
    return fdb.connect(host=os.getenv("DB_HOST"), database=os.getenv("DB_DATABASE"),
                       user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
                       charset=os.getenv("DB_CHARSET", "UTF8"))


def criar_banco():
    # CREATE DATABASE nunca sobrescreve um arquivo existente.
    alvo = f"{os.getenv('DB_HOST')}:{os.getenv('DB_DATABASE')}" if os.getenv("DB_HOST") else os.getenv("DB_DATABASE")
    fdb.create_database(
        sql=f"CREATE DATABASE '{alvo}' USER '{os.getenv('DB_USER')}' PASSWORD '{os.getenv('DB_PASSWORD')}' "
            "PAGE_SIZE 16384 DEFAULT CHARACTER SET ISO8859_1"
    ).close()
    print(f"banco criado: {alvo}")


def comandos(texto):
    """Divide um script do isql em comandos, respeitando aspas, comentarios e SET TERM."""
    terminador, atual, resultado = ";", [], []
    i = 0
    while i < len(texto):
        if texto.startswith("/*", i):
            fim = texto.find("*/", i + 2)
            i = len(texto) if fim < 0 else fim + 2
            continue
        if texto.startswith("--", i):
            fim = texto.find("\n", i)
            i = len(texto) if fim < 0 else fim
            continue
        if texto[i] in "'\"":
            aspa, j = texto[i], i + 1
            while j < len(texto) and not (texto[j] == aspa and not texto.startswith(aspa * 2, j)):
                j += 2 if texto.startswith(aspa * 2, j) else 1
            atual.append(texto[i:j + 1])
            i = j + 1
            continue
        if texto.startswith(terminador, i):
            comando = "".join(atual).strip()
            atual, i = [], i + len(terminador)
            novo = re.match(r"SET\s+TERM\s+(\S+)\s*$", comando, re.I)
            if novo:
                terminador = novo.group(1)
            elif comando and not IGNORADOS.match(comando):
                resultado.append(comando)
            continue
        atual.append(texto[i])
        i += 1
    if "".join(atual).strip():
        raise ValueError(f"comando sem terminador '{terminador}' no fim do arquivo")
    return resultado


def migrations():
    encontradas = {}
    for nome in sorted(os.listdir(PASTA)):
        casamento = ARQUIVO.match(nome)
        if not casamento:
            if nome.endswith(".sql"):
                raise ValueError(f"nome fora do padrao NNNN_descricao.sql: {nome}")
            continue
        versao = int(casamento.group(1))
        if versao in encontradas:
            raise ValueError(f"versao {versao} repetida: {encontradas[versao]} e {nome}")
        encontradas[versao] = nome
    return sorted(encontradas.items())


def tabela_existe(cur, nome):
    cur.execute("SELECT 1 FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = ?", (nome,))
    return cur.fetchone() is not None


def preparar_controle(con, baseline):
    cur = con.cursor()
    if tabela_existe(cur, "SCHEMA_MIGRATION"):
        if baseline is not None:
            raise ValueError("--baseline e so para banco sem SCHEMA_MIGRATION")
        return
    if tabela_existe(cur, "USUARIO") and baseline is None:
        raise ValueError("o banco ja tem tabelas, mas nenhuma migration registrada. "
                         "Se ele esta no schema da 0001, rode com --baseline 1")
    cur.execute("""CREATE TABLE SCHEMA_MIGRATION (
        VERSAO INTEGER NOT NULL PRIMARY KEY,
        NOME VARCHAR(100) NOT NULL,
        APLICADA_EM TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)""")
    con.commit()
    if baseline is not None:
        registradas = [(v, n) for v, n in migrations() if v <= baseline]
        if not registradas:
            raise ValueError(f"nenhuma migration ate a versao {baseline}")
        cur.executemany("INSERT INTO SCHEMA_MIGRATION (VERSAO, NOME) VALUES (?, ?)", registradas)
        con.commit()
        for versao, nome in registradas:
            print(f"baseline: {nome} registrada sem executar")


def aplicadas(con):
    cur = con.cursor()
    if not tabela_existe(cur, "SCHEMA_MIGRATION"):
        return set()
    cur.execute("SELECT VERSAO FROM SCHEMA_MIGRATION")
    return {linha[0] for linha in cur.fetchall()}


def executar_arquivo(con, caminho, registrar=None):
    """Roda o script numa transacao; registrar=(versao, nome) grava em SCHEMA_MIGRATION na mesma."""
    with open(caminho, encoding="utf-8") as arquivo:
        lista = comandos(arquivo.read())
    cur = con.cursor()
    try:
        for comando in lista:
            cur.execute(comando)
        if registrar:
            cur.execute("INSERT INTO SCHEMA_MIGRATION (VERSAO, NOME) VALUES (?, ?)", registrar)
        con.commit()
    except Exception:
        con.rollback()
        raise
    return len(lista)


def aplicar(con, versao, nome):
    total = executar_arquivo(con, os.path.join(PASTA, nome), registrar=(versao, nome))
    print(f"aplicada: {nome} ({total} comandos)")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--criar", action="store_true", help="cria o banco vazio se ele nao existir")
    parser.add_argument("--baseline", type=int, metavar="VERSAO", help="registra ate VERSAO como aplicadas, sem executar")
    parser.add_argument("--status", action="store_true", help="so lista aplicadas e pendentes")
    parser.add_argument("--seed", metavar="ARQUIVO", help="depois das migrations, roda este SQL (dados de dev/CI)")
    args = parser.parse_args(argv)
    load_dotenv()

    try:
        try:
            con = conectar()
        except fdb.DatabaseError:
            if not args.criar:
                raise
            criar_banco()
            con = conectar()
        try:
            if args.status:
                feitas = aplicadas(con)
                for versao, nome in migrations():
                    print(("aplicada " if versao in feitas else "pendente ") + nome)
                return 0
            preparar_controle(con, args.baseline)
            feitas = aplicadas(con)
            pendentes = [(v, n) for v, n in migrations() if v not in feitas]
            for versao, nome in pendentes:
                aplicar(con, versao, nome)
            print("schema em dia" if not pendentes else f"{len(pendentes)} migration(s) aplicada(s)")
            if args.seed:
                print(f"seed: {executar_arquivo(con, args.seed)} comandos de {args.seed}")
            return 0
        finally:
            con.close()
    except Exception as erro:
        print(f"migracao falhou: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
