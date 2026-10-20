import threading
import time

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


def test_rajada_com_pool_quente():
    # Aquece com 10 conexoes abertas ao mesmo tempo: numa rajada, uma thread rapida devolve
    # a conexao antes de outra pedir, e o pool fica com menos de 10 se ja havia alguma livre
    conexoes = [get_connection() for _ in range(10)]
    for con in conexoes:
        con.close()
    assert _livres.qsize() == 10, _livres.qsize()
    pior = rajada()
    assert pior < 0.5, f"rajada com pool quente demorou {pior:.3f}s"


def test_conexao_morta_e_trocada():
    get_connection().close()
    _livres.queue[-1].close()
    con = get_connection()
    cur = con.cursor()
    cur.execute("SELECT 1 FROM RDB$DATABASE")
    assert cur.fetchone() == (1,)
    con.close()


def test_devolver_descarta_o_que_nao_foi_commitado():
    con = get_connection()
    cur = con.cursor()
    cur.execute("UPDATE USUARIO SET NOME = NOME WHERE 1 = 0")
    con.close()
    assert not _livres.queue[-1].main_transaction.active
