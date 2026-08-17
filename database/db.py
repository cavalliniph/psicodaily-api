import os
from dotenv import load_dotenv
import fdb

load_dotenv()

DIRNAME = os.path.dirname(__file__)

def get_connection():
    try:
        conn = fdb.connect(
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            database=os.path.join(DIRNAME, "BANCO.FDB"),
        )
        return conn
    except Exception as e:
        print(f"erro ao conectar ao banco: {str(e)}")

conn = get_connection()
