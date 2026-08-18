from flask import current_app
from flask_bcrypt import check_password_hash, generate_password_hash
import jwt

def gerar_token(payload) -> str | None:
	try:
		token = jwt.encode(
            payload,
			current_app.config.get("SECRET_KEY"),
			algorithm='HS256'
        )
		return token
	except Exception as e:
		print(f"erro ao criar token: {str(e)}")

def senha_correta(senha_hash, senha):
	return check_password_hash(senha_hash, senha)

def criar_hash_senha(senha):
	return generate_password_hash(senha)
