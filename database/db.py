import os

from dotenv import load_dotenv
from time import perf_counter
from flask import g
from sqlalchemy import create_engine

# import fdb (legado)

# - por que fdb foi removido?
# acontece que a própria documentação do fdb no pypi menciona que
# é legado pra versões firebird acima de 2.x.x
# aqui a fonte >> https://pypi.org/project/fdb/2.0.4/

# a partir disso, outro problema que passaríamos mais cedo
# ou mais tarde é a falta de pooling de conexões, nós precisamos
# disso pra facilitar o acesso e diminuir a latencia de criar conexão
# toda santa vez, performance importa

load_dotenv()

DIRNAME = os.path.dirname(__file__)
DB_PATH = os.path.join(DIRNAME, "BANCO.FDB").replace("\\", "/")

#firebird+firebird://<username>:<password>@<host>:<port>/<database_path>[?charset=UTF8&key=value&...]

engine = create_engine(
	f"firebird+firebird://"
	f"{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
	f"@localhost/{DB_PATH}",
	pool_size=5,
	max_overflow=10,
	pool_timeout=10,
	pool_pre_ping=True,
)

def get_connection():
	if "db" not in g:
		g.db = engine.raw_connection()
	return g.db

def close_connection(exception=None):
	con = g.pop("db", None)

	if con is None:
		return

	try:
		if exception is not None:
			con.rollback()
	finally:
		con.close()

# def get_connection():
#     try:
#         start = perf_counter() # comecando a contar
        
#         con = fdb.connect(
#             user=os.getenv("DB_USER"),
#             password=os.getenv("DB_PASSWORD"),
#             # host=os.getenv("DB_HOST"),
#             database=os.path.join(DIRNAME, "BANCO.FDB"),
#         )

#         print(f"[{__name__}]: {(perf_counter() - start) * 1000:.2f}ms")
		
#         return con
#     except Exception as e:
#         print(f"erro ao conectar ao banco: {str(e)}")

# con = get_connection()

