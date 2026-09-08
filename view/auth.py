from funcao import enviar_email, gerar_token, criar_hash_senha, senha_correta, validar_email, validar_senha, validar_cpf, validar_telefone
from flask import Blueprint, current_app, jsonify, make_response, request
from database.db import get_connection
from decimal import Decimal, InvalidOperation
import json
import re
import threading
import secrets
import os
import unicodedata

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

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

@auth_bp.route('/login', methods=['POST'])
def login():
	con = get_connection()
	cur = con.cursor()

	try:
		data = request.get_json(silent=True) or {}

		email = data.get('email')
		senha = data.get('senha')

		if not email or not senha:
			return jsonify({ "error": "Email e senha sao obrigatorios" }), 400

		cur.execute("SELECT id_usuario, senha, ativo, usuario_role FROM usuario WHERE email = ?", (email,))
		usuario = cur.fetchone()

		if not usuario:
			return jsonify({ "error": "Usuario nao encontrado" }), 404

		if not senha_correta(usuario[1], senha):
			return jsonify({ "error": "Senha incorreta" }), 401

		if not usuario[2]:
			return jsonify({ "error": "Usuario inativo" }), 403

		payload = {
			'id_usuario': usuario[0],
			'usuario_role': usuario[3]
		}

		token = gerar_token(payload)

		if not token:
			raise RuntimeError("Erro ao gerar token")

		response = make_response({
			"message": "Usuario logado com sucesso",
			"usuario": {
				"id_usuario": usuario[0],
				"tipo_usuario": usuario[3]
			}
		})

		response.set_cookie("access_token", token)

		return response
	except Exception as e:
		print(str(e))
		return jsonify({ "error": "Internal server error" }), 500
	finally:
		if cur is not None:
			cur.close()

# cadastro de cliente comum
@auth_bp.route('/cadastro', methods=['POST'])
def cadastro():
	con = get_connection()
	cur = con.cursor()

	try:
		usuario, erro = criar_usuario_base(cur, request.form, 'PACIENTE')

		if erro:
			return erro

		if usuario is None:
			raise RuntimeError("Cadastro nao retornou os dados do usuario")

		con.commit()
		enviar_email_ativacao(usuario["email"], usuario["codigo"])

		return jsonify({
			"message": "Usuario cadastrado com sucesso",
			"usuario": {
				"id_usuario": usuario["id_usuario"],
				"tipo_usuario": "PACIENTE"
			}
		}), 201


	except Exception as e:
		print(f"houve um erro ao realizar o cadastro: {str(e)}")
		con.rollback()
		return jsonify({ "error": "Internal server error" }), 500
	finally:
		if cur is not None:
			cur.close()

@auth_bp.route('/cadastro_profissional', methods=['POST'])
def cadastro_profissional():
	con = get_connection()
	cur = con.cursor()

	try:
		formulario = request.form
		especialidade_recebida = obter_campo(formulario, 'especialidade')
		especialidade = next(
			(
				nome_especialidade
				for nome_especialidade in ESPECIALIDADES_PROFISSIONAIS
				if normalizar_texto(nome_especialidade) == normalizar_texto(especialidade_recebida)
			),
			None
		)

		if not especialidade:
			return resposta_erro("Especialidade deve ser Psicologia ou Psiquiatria")

		configuracao_profissional = ESPECIALIDADES_PROFISSIONAIS[especialidade]
		conselho_tipo = configuracao_profissional["conselho_tipo"]
		conselho_recebido = obter_campo(
			formulario,
			'crp_crm',
			'crp',
			'crm',
			'conselho',
			'conselho_numero'
		)

		if not conselho_recebido:
			return resposta_erro("CRP/CRM e obrigatorio")

		conselho_numero = normalizar_conselho(conselho_recebido, conselho_tipo)

		if not conselho_numero:
			return resposta_erro(f"{conselho_tipo} invalido")

		descricao = obter_campo(formulario, 'descricao')

		if len(descricao) < 10 or len(descricao) > 1000:
			return resposta_erro("Descricao deve ter entre 10 e 1000 caracteres")

		valor_recebido = obter_campo(
			formulario,
			'valor',
			'valor_sessao',
			'valorPorSessao',
			'preco',
			'preco_hora'
		)

		if not valor_recebido:
			return resposta_erro("Valor por sessao e obrigatorio")

		preco_hora = normalizar_valor_sessao(valor_recebido)

		if preco_hora is None:
			return resposta_erro("Valor por sessao deve ser um numero inteiro positivo")

		dias_atendimento, erro_dias = obter_dias_atendimento(formulario)

		if erro_dias:
			return resposta_erro(erro_dias)

		usuario, erro = criar_usuario_base(
			cur,
			formulario,
			configuracao_profissional["usuario_role"],
			exigir_confirmacao_senha=True
		)

		if erro:
			return erro

		if usuario is None:
			raise RuntimeError("Cadastro nao retornou os dados do usuario")

		cur.execute("""INSERT INTO profissional (
							usuario_id,
							conselho_tipo,
							conselho_numero,
							especialidade,
							preco_hora,
							descricao
						) VALUES (?, ?, ?, ?, ?, ?)""",
				 (usuario["id_usuario"], conselho_tipo, conselho_numero, especialidade, preco_hora, descricao))

		con.commit()
		enviar_email_ativacao(usuario["email"], usuario["codigo"])

		return jsonify({
			"message": "Profissional cadastrado com sucesso",
			"usuario": {
				"id_usuario": usuario["id_usuario"],
				"tipo_usuario": configuracao_profissional["usuario_role"]
			},
			"profissional": {
				"conselho_tipo": conselho_tipo,
				"conselho_numero": conselho_numero,
				"especialidade": especialidade,
				"preco_hora": preco_hora,
				"dias_atendimento": dias_atendimento
			}
		}), 201
	except Exception as e:
		print(f"houve um erro ao realizar o cadastro profissional: {str(e)}")
		con.rollback()
		return jsonify({ "error": "Internal server error" }), 500
	finally:
		if cur is not None:
			cur.close()

@auth_bp.route('/verificar_codigo', methods=['POST'])
def verificar_codigo():
	con = get_connection()
	cur = con.cursor()

	try:
		data = request.get_json(silent=True) or {}

		if not data:
			return jsonify({ "error": "Formato invalido" }), 400

		email = data.get('email')
		codigo = data.get('codigo')

		if not email or not codigo:
			return jsonify({ "error": "Email e codigo sao obrigatorios" }), 400

		cur.execute("SELECT id_usuario, codigo FROM usuario WHERE email = ?", (email,))
		usuario = cur.fetchone()

		if not usuario:
			return jsonify({ "error": "Usuario nao encontrado" }), 404

		if usuario[1] != codigo:
			return jsonify({ "error": "Codigo invalido" }), 401

		cur.execute("UPDATE usuario SET ativo = true, codigo = NULL WHERE id_usuario = ?", (usuario[0],))
		con.commit()

		return jsonify({ "message": "Email verificado com sucesso" }), 200
	except Exception as e:
		print(f"houve um erro ao verificar o codigo: {str(e)}")
		con.rollback()
		return jsonify({ "error": "Internal server error" }), 500
	finally:
		if cur is not None:
			cur.close()

@auth_bp.route('/esqueci_senha', methods=['POST'])
def esqueci_senha():
	con = get_connection()
	cur = con.cursor()

	try:
		data = request.get_json(silent=True) or {}
		email = data.get('email')

		if not email:
			return jsonify({ "error": "Email e obrigatorio" }), 400

		cur.execute("SELECT id_usuario FROM usuario WHERE email = ?", (email,))
		usuario = cur.fetchone()

		if not usuario:
			return jsonify({ "error": "Usuario nao encontrado" }), 404

		codigo = f"{secrets.randbelow(1000000):06d}"
		cur.execute("UPDATE usuario SET codigo = ? WHERE id_usuario = ?", (codigo, usuario[0]))
		con.commit()

		threading.Thread(
			target=enviar_email,
			args=(email, "Recuperacao de senha", f"Seu codigo para alterar a senha e: {codigo}")
		).start()

		return jsonify({ "message": "Codigo enviado para o e-mail" }), 200
	except Exception as e:
		print(f"houve um erro ao solicitar recuperacao: {str(e)}")
		con.rollback()
		return jsonify({ "error": "Internal server error" }), 500
	finally:
		if cur is not None:
			cur.close()

@auth_bp.route('/alterar_senha', methods=['POST'])
def alterar_senha():
	con = get_connection()
	cur = con.cursor()

	try:
		data = request.get_json(silent=True) or {}
		codigo = data.get('codigo')
		nova_senha = data.get('senha')

		if not codigo or not nova_senha:
			return jsonify({ "error": "Codigo e senha sao obrigatorios" }), 400

		if not validar_senha(nova_senha):
			return jsonify({ "error": "Senha nao atende aos requisitos" }), 400

		cur.execute("SELECT id_usuario FROM usuario WHERE codigo = ?", (codigo,))
		usuario = cur.fetchone()

		if not usuario:
			return jsonify({ "error": "Codigo invalido" }), 401

		cur.execute(
			"UPDATE usuario SET senha = ?, codigo = NULL WHERE id_usuario = ?",
			(criar_hash_senha(nova_senha), usuario[0])
		)
		con.commit()

		return jsonify({ "message": "Senha alterada com sucesso" }), 200
	except Exception as e:
		print(f"houve um erro ao alterar a senha: {str(e)}")
		con.rollback()
		return jsonify({ "error": "Internal server error" }), 500
	finally:
		if cur is not None:
			cur.close()

