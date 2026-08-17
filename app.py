import os
from flask import Flask
from flask.cli import load_dotenv
from view.teste import teste_bp

load_dotenv()
app = Flask(__name__)
app.register_blueprint(teste_bp)

if __name__ == '__main__':
    app.run(debug=True, port=os.environ.get('PORT'))
