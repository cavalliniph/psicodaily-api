from flask import current_app
import jwt

def gerar_token(payload):
	try:
		token = jwt.encode(
            payload,
			current_app.config.get("SECRET_KEY"),
			algorithm='HS256'
        )
		return token
	except Exception as e:
		print(f"erro ao criar token: {str(e)}")
