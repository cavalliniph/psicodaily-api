import os
from dotenv import load_dotenv
import fdb
from flask import current_app

load_dotenv()

def get_connection():
    try:
        con = fdb.connect(
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_DATABASE"),
            charset=os.getenv("DB_CHARSET", "UTF8"),
        )
        return con
    except Exception as e:
        print(f"erro ao conectar ao banco: {str(e)}")
        raise RuntimeError("Erro ao conectar ao banco")
