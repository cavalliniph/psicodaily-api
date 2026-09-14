from flask import Flask
from flask.cli import load_dotenv
from view.auth import auth_bp
from view.usuarios import usuarios_bp
# from view.agendamento import agendamento_bp
# from view.registros import registros_bp
from view.profissionais import prof_bp
from view.consultas import cons_bp
from flask_cors import CORS
from pathlib import Path

load_dotenv()

app = Flask(__name__)

app.register_blueprint(auth_bp)
app.register_blueprint(usuarios_bp)
# app.register_blueprint(agendamento_bp)
# app.register_blueprint(registros_bp)
app.register_blueprint(prof_bp)
app.register_blueprint(cons_bp)

app.config.from_pyfile("config.py")

CORS(app, supports_credentials=True, origins=['http://localhost:5173'])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

