from email.mime.text import MIMEText
import smtplib
from flask import current_app
from flask_bcrypt import check_password_hash, generate_password_hash
import jwt
import re

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

def senha_correta(senha_hash, senha):
	return check_password_hash(senha_hash, senha)

def criar_hash_senha(senha):
	return generate_password_hash(senha)

def validar_senha(senha: str):
    if not senha:
        return False

    maiuscula = minuscula = numero = especial = False

    for s in senha:
        if s.isupper():
            maiuscula = True
        elif s.islower():
            minuscula = True
        elif s.isdigit():
            numero = True
        elif not s.isalnum():
            especial = True

    if len(senha) < 8 or len(senha) > 12:
        return False

    if not (maiuscula and minuscula and numero and especial):
        return False
    return True

def enviar_email(destinatario, assunto, mensagem):
        user = "psicodaily.contato@gmail.com"
        senha = "hmdk zazs yrxn gylf"

        msg = MIMEText(mensagem)
        msg['Subject'] = assunto
        msg['From'] = user
        msg['To'] = destinatario

        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)

        server.login(user, senha)
        server.send_message(msg)
        server.quit()

def validar_cpf(cpf):
	cpf = ''.join(filter(str.isdigit, cpf))

	if len(cpf) != 11 or cpf == cpf[0] * 11:
		return False

	for i in range(9, 11):
		soma = sum(int(cpf[j]) * (i + 1 - j) for j in range(i))
		digito = (soma * 10 % 11) % 10
		if digito != int(cpf[i]):
			return False

	return True

def validar_email(email):
	padrao = r'^[\w\.-]+@[\w\.-]+\.\w+$'
	return re.match(padrao, email) is not None

def validar_telefone(telefone):
	padrao = r'^\(?\d{2}\)?[\s-]?\d{4,5}-?\d{4}$'
	return re.match(padrao, telefone) is not None  
