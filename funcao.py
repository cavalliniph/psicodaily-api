from decimal import Decimal, InvalidOperation
import json
import os
import secrets
import threading
import unicodedata
from email.mime.text import MIMEText
import smtplib
from flask import current_app, jsonify, request
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


ESPECIALIDADES_PROFISSIONAIS = {
	"Psicologia": {
		"usuario_role": "PSICOLOGO",
		"conselho_tipo": "CRP",
	},
	"Psiquiatria": {
		"usuario_role": "PSIQUIATRA",
		"conselho_tipo": "CRM",
	},
}

DIAS_ATENDIMENTO = {
	"SEGUNDA": "Segunda",
	"TERCA": "Terca",
	"QUARTA": "Quarta",
	"QUINTA": "Quinta",
	"SEXTA": "Sexta",
	"SABADO": "Sabado",
	"DOMINGO": "Domingo",
}

TIPOS_IMAGEM_PERMITIDOS = {"image/jpeg", "image/jpg"}
EXTENSOES_IMAGEM_PERMITIDAS = {".jpg", ".jpeg"}


def resposta_erro(mensagem, status=400):
	return jsonify({ "error": mensagem }), status


def obter_campo(formulario, *nomes):
	for nome in nomes:
		valor = formulario.get(nome)

		if valor is None:
			continue

		if isinstance(valor, str):
			valor = valor.strip()

		if valor != "":
			return valor

	return ""


def somente_digitos(valor):
	return "".join(filter(str.isdigit, valor or ""))


def normalizar_texto(valor):
	texto = unicodedata.normalize("NFKD", valor or "")
	return "".join(letra for letra in texto if not unicodedata.combining(letra)).upper()


def validar_nome(nome):
	if len(nome) < 3 or len(nome) > 150:
		return False

	caracteres_permitidos = set(" .'-")
	return any(letra.isalpha() for letra in nome) and all(
		letra.isalpha() or letra in caracteres_permitidos for letra in nome
	)


def validar_imagem_usuario(imagem):
	if not imagem or not imagem.filename:
		return True

	_, extensao = os.path.splitext(imagem.filename.lower())
	tipo = (imagem.content_type or "").lower()

	return extensao in EXTENSOES_IMAGEM_PERMITIDAS and tipo in TIPOS_IMAGEM_PERMITIDOS


def salvar_imagem_usuario(imagem, id_usuario):
	if not imagem or not imagem.filename:
		return

	nome_imagem = f"{id_usuario}.jpg"
	caminho_imagem_destino = os.path.join(current_app.config['UPLOAD_FOLDER'], "usuarios")
	os.makedirs(caminho_imagem_destino, exist_ok=True)
	caminho_imagem = os.path.join(caminho_imagem_destino, nome_imagem)
	imagem.save(caminho_imagem)


def enviar_email_ativacao(email, codigo):
	threading.Thread(
		target=enviar_email,
		args=(email, "Codigo de verificacao", f"Seu codigo de verificacao e: {codigo}"),
		daemon=True
	).start()


def criar_usuario_base(cur, formulario, usuario_role, exigir_confirmacao_senha=False):
	imagem = request.files.get('imagem')
	email = obter_campo(formulario, 'email')
	nome = obter_campo(formulario, 'nome')
	telefone = obter_campo(formulario, 'telefone')
	senha = obter_campo(formulario, 'senha')
	confirmar_senha = obter_campo(formulario, 'confirmar_senha', 'confirmarSenha')
	cpf = somente_digitos(obter_campo(formulario, 'cpf'))

	if not nome or not email or not telefone or not senha or not cpf:
		return None, resposta_erro("Todos os campos de usuario sao obrigatorios")

	if not validar_nome(nome):
		return None, resposta_erro("Nome invalido")

	if not validar_email(email):
		return None, resposta_erro("Email invalido")

	if not validar_cpf(cpf):
		return None, resposta_erro("CPF invalido")

	if not validar_telefone(telefone):
		return None, resposta_erro("Telefone invalido")

	if not validar_senha(senha):
		return None, resposta_erro("Senha nao atende aos requisitos")

	if exigir_confirmacao_senha and not confirmar_senha:
		return None, resposta_erro("Confirmacao de senha e obrigatoria")

	if exigir_confirmacao_senha and senha != confirmar_senha:
		return None, resposta_erro("As senhas nao sao iguais")

	if not validar_imagem_usuario(imagem):
		return None, resposta_erro("Imagem deve ser um arquivo JPG ou JPEG")

	cur.execute("SELECT id_usuario FROM usuario WHERE email = ?", (email,))

	if cur.fetchone():
		return None, resposta_erro("Usuario ja cadastrado")

	cur.execute("SELECT id_usuario FROM usuario WHERE cpf = ?", (cpf,))

	if cur.fetchone():
		return None, resposta_erro("CPF ja cadastrado")

	senha_hash = criar_hash_senha(senha)
	codigo = f"{secrets.randbelow(1000000):06d}"

	cur.execute("""INSERT INTO usuario (nome, email, telefone, senha, cpf, codigo, usuario_role)
					  VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id_usuario""",
			 (nome, email, telefone, senha_hash, cpf, codigo, usuario_role))

	usuario_criado = cur.fetchone()

	if usuario_criado is None:
		raise RuntimeError("Banco nao retornou o usuario criado")

	id_usuario = usuario_criado[0]
	salvar_imagem_usuario(imagem, id_usuario)

	return {
		"id_usuario": id_usuario,
		"email": email,
		"codigo": codigo,
		"nome": nome,
	}, None


def obter_dias_atendimento(formulario):
	valores = []

	for campo in ("dias", "dias[]", "dias_atendimento", "diasAtendimento"):
		valores.extend(formulario.getlist(campo))

	dias_recebidos = []

	for valor in valores:
		if not valor:
			continue

		texto = valor.strip()

		if not texto:
			continue

		if texto.startswith("["):
			try:
				lista = json.loads(texto)
			except json.JSONDecodeError:
				return None, "Dias de atendimento devem ser uma lista valida"

			if not isinstance(lista, list):
				return None, "Dias de atendimento devem ser uma lista"

			dias_recebidos.extend(str(item) for item in lista)
			continue

		dias_recebidos.extend(parte.strip() for parte in texto.split(","))

	if not dias_recebidos:
		return None, "Selecione ao menos um dia de atendimento"

	dias_normalizados = []
	chaves_usadas = set()

	for dia in dias_recebidos:
		chave = normalizar_texto(dia)

		if chave not in DIAS_ATENDIMENTO:
			return None, "Dia de atendimento invalido"

		if chave in chaves_usadas:
			return None, "Dias de atendimento nao podem se repetir"

		chaves_usadas.add(chave)
		dias_normalizados.append(DIAS_ATENDIMENTO[chave])

	return dias_normalizados, None


def normalizar_valor_sessao(valor):
	texto = valor.replace("R$", "").replace(" ", "")

	if "," in texto and "." in texto:
		texto = texto.replace(".", "").replace(",", ".")
	elif "," in texto:
		texto = texto.replace(",", ".")

	try:
		valor_decimal = Decimal(texto)
	except InvalidOperation:
		return None

	if valor_decimal <= 0 or valor_decimal > Decimal("100000"):
		return None

	if valor_decimal != valor_decimal.to_integral_value():
		return None

	return int(valor_decimal)


def normalizar_conselho(valor, conselho_tipo):
	texto = valor.upper().strip()
	texto = texto.replace(" ", "")

	if conselho_tipo == "CRP":
		texto = re.sub(r"^CRP", "", texto)

		if not re.fullmatch(r"\d{2}/?\d{4,6}", texto):
			return None

		digitos = somente_digitos(texto)
		return f"{digitos[:2]}/{digitos[2:]}"

	if conselho_tipo == "CRM":
		texto = re.sub(r"^CRM", "", texto)
		texto = texto.lstrip("/")
		com_uf = re.fullmatch(r"([A-Z]{2})/?(\d{4,6})", texto)

		if com_uf:
			uf, numero = com_uf.groups()
			return f"{uf}/{numero}"

		if re.fullmatch(r"\d{4,6}", texto):
			return texto

	return None

def decodificar_token(token):
	return jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
