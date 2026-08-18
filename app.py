from flask import Flask
from flask.cli import load_dotenv
from view.auth import auth_bp
from flask_cors import CORS

load_dotenv()

app = Flask(__name__)
app.register_blueprint(auth_bp)
app.config.from_pyfile("config.py")

CORS(app, supports_credentials=True, origins=['http://localhost:5173'])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
