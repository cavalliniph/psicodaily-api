from flask import Flask
from flask.cli import load_dotenv
from view.auth import auth_bp
from view.usuarios import usuarios_bp
# from view.agendamento import agendamento_bp
from view.registros import registros_bp
from view.prontuario import prontuario_bp
from view.profissionais import prof_bp
from view.consultas import cons_bp
from view.encaminhamentos import encam_bp
from view.pagamentos import pagamentos_bp
from flask_cors import CORS
# from pathlib import Path

from extensions.websocket import sock
from view.signaling import signaling_bp

load_dotenv()

app = Flask(__name__)
sock.init_app(app)

app.register_blueprint(signaling_bp)

app.register_blueprint(auth_bp)
app.register_blueprint(usuarios_bp)
# app.register_blueprint(agendamento_bp)
app.register_blueprint(registros_bp)
app.register_blueprint(prontuario_bp)
app.register_blueprint(prof_bp)
app.register_blueprint(cons_bp)
app.register_blueprint(encam_bp)
app.register_blueprint(pagamentos_bp)

app.config.from_pyfile("config.py")

CORS(
    app,
    supports_credentials=True,
    origins=[
        'http://localhost:5173'
    ]
)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
