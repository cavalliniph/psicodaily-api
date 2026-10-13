# Precisa do Firebird no ar: python tests/test_pool.py
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import _livres, get_connection


def consulta(tempos):
    inicio = time.perf_counter()
    con = get_connection()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM USUARIO")
    cur.fetchone()
    con.close()
    tempos.append(time.perf_counter() - inicio)


def rajada(n=10):
    tempos = []
    threads = [threading.Thread(target=consulta, args=(tempos,)) for _ in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return max(tempos)


rajada()  # aquece o pool
assert _livres.qsize() == 10, _livres.qsize()
pior = rajada()
assert pior < 0.5, f"rajada com pool quente demorou {pior:.3f}s"

# Conexao morta no pool e trocada por uma nova, sem erro para a rota
_livres.queue[-1].close()
con = get_connection()
cur = con.cursor()
cur.execute("SELECT 1 FROM RDB$DATABASE")
assert cur.fetchone() == (1,)
con.close()

# O que a rota nao commitou e descartado ao devolver
con = get_connection()
cur = con.cursor()
cur.execute("UPDATE USUARIO SET NOME = NOME WHERE 1 = 0")
con.close()
assert not _livres.queue[-1].main_transaction.active

print(f"ok: pior tempo da rajada com pool quente {pior:.3f}s")
