from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlsplit
import json
import os
import unicodedata
import re

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

ABORDAGENS = ["TCC", "Psicanálise", "Humanista", "Gestalt", "Comportamental"]
MODALIDADES = {"ONLINE", "PRESENCIAL", "AMBAS"}
IDIOMAS = ["Português", "Inglês", "Espanhol", "Francês", "Italiano", "Alemão", "Libras"]
AREAS_ATUACAO = [
	"Ansiedade", "Depressão", "Estresse", "Burnout", "Autoestima", "Relacionamentos", "Família",
	"Luto", "Trauma", "TDAH", "Autismo", "Transtornos alimentares", "Dependência química",
	"Sexualidade", "Orientação profissional", "Infância e adolescência",
]
MAXIMO_AREAS_ATUACAO = 8


def _opcao(valor, opcoes):
	recebida = normalizar_texto(str(valor).strip())
	return next((nome for nome in opcoes if normalizar_texto(nome) == recebida), None)


def normalizar_abordagem(valor):
	return _opcao(valor, ABORDAGENS)


def normalizar_modalidade(valor):
	modalidade = normalizar_texto(str(valor).strip())
	return modalidade if modalidade in MODALIDADES else None


def normalizar_lista(valor, opcoes, maximo):
	"""Lista, texto JSON ("[...]") ou CSV -> nomes canonicos separados por virgula; None se invalida."""
	if isinstance(valor, str):
		texto = valor.strip()
		if texto.startswith("["):
			try:
				valor = json.loads(texto)
			except json.JSONDecodeError:
				return None
		else:
			valor = texto.split(",")
	if not isinstance(valor, list):
		return None

	itens = []
	for item in valor:
		if not isinstance(item, str):
			return None
		if not item.strip():
			continue
		nome = _opcao(item, opcoes)
		if nome is None:
			return None
		if nome not in itens:
			itens.append(nome)

	if not itens or len(itens) > maximo:
		return None
	return ",".join(itens)


def normalizar_ano_inicio(valor):
	if isinstance(valor, bool):
		return None
	try:
		ano = int(str(valor).strip())
	except ValueError:
		return None
	return ano if 1950 <= ano <= date.today().year else None


def normalizar_formacao(valor):
	if not isinstance(valor, str):
		return None
	texto = valor.strip()
	return texto if 3 <= len(texto) <= 1000 else None


def normalizar_video_url(valor):
	"""Link do YouTube ou Vimeo -> URL de embed canonica; None se nao for um deles."""
	if not isinstance(valor, str) or len(valor) > 500:
		return None
	try:
		partes = urlsplit(valor.strip())
	except ValueError:
		return None
	if partes.scheme not in ("http", "https"):
		return None
	host = (partes.hostname or "").removeprefix("www.").removeprefix("m.")
	caminho = [parte for parte in partes.path.split("/") if parte]

	if host in ("youtube.com", "youtube-nocookie.com", "youtu.be"):
		video = None
		if host == "youtu.be" and caminho:
			video = caminho[0]
		elif caminho == ["watch"]:
			video = parse_qs(partes.query).get("v", [""])[0]
		elif len(caminho) == 2 and caminho[0] in ("embed", "shorts", "live"):
			video = caminho[1]
		if video and re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
			return f"https://www.youtube-nocookie.com/embed/{video}"
		return None

	if host == "player.vimeo.com" and len(caminho) == 2 and caminho[0] == "video":
		numero, hash_privado = caminho[1], parse_qs(partes.query).get("h", [""])[0]
	elif host == "vimeo.com" and caminho:
		# Video nao listado: vimeo.com/<numero>/<hash>
		numero, hash_privado = caminho[0], caminho[1] if len(caminho) == 2 else ""
	else:
		return None
	if not numero.isdigit() or (hash_privado and not re.fullmatch(r"[0-9a-f]{6,20}", hash_privado)):
		return None
	return f"https://player.vimeo.com/video/{numero}" + (f"?h={hash_privado}" if hash_privado else "")

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
	"""Converte a entrada em reais para centavos inteiros do banco."""
	texto = str(valor).replace("R$", "").replace(" ", "")

	if "," in texto and "." in texto:
		texto = texto.replace(".", "").replace(",", ".")
	elif "," in texto:
		texto = texto.replace(",", ".")

	try:
		valor_decimal = Decimal(texto)
	except InvalidOperation:
		return None

	if not valor_decimal.is_finite() or valor_decimal <= 0 or valor_decimal > Decimal("100000"):
		return None

	centavos = valor_decimal * 100
	if centavos != centavos.to_integral_value():
		return None

	return int(centavos)


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
