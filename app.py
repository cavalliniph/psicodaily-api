from flask import Flask
from flask.cli import load_dotenv
from view.auth import auth_bp
from view.usuarios import usuarios_bp
# from view.agendamento import agendamento_bp
# from view.registros import registros_bp
from view.profissionais import prof_bp
from flask_cors import CORS
from database.db import close_connection
from pathlib import Path

load_dotenv()

app = Flask(__name__)

app.register_blueprint(auth_bp)
app.register_blueprint(usuarios_bp)
# app.register_blueprint(agendamento_bp)
# app.register_blueprint(registros_bp)
app.register_blueprint(prof_bp)

app.config.from_pyfile("config.py")

# precisamos matar todas as conexoes/pool
# abertas do banco de dados,
# teardown_appcontext executa quando o app morre
app.teardown_appcontext(close_connection)

CORS(app, supports_credentials=True, origins=['http://localhost:5173'])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

