import os.path
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Front autorizado: CORS do app.py e Origin do handshake WebSocket (S7). O app mobile nao manda Origin.
ORIGENS_FRONT = [
    'http://localhost:5173',
    # Front buildado servido pelo nginx local (Dockerfile do front), que repassa /api e /ws
    'http://localhost:8080',
    'https://psicodaily-front.vercel.app',
    'http://10.92.11.34:5173',
]
