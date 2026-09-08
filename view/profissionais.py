from flask import Blueprint, jsonify, request
from database.db import get_connection
from funcao import (
	ESPECIALIDADES_PROFISSIONAIS,
	criar_usuario_base,
	enviar_email_ativacao,
	normalizar_conselho,
	normalizar_texto,
	normalizar_valor_sessao,
	obter_campo,
	obter_dias_atendimento,
	resposta_erro,
)

prof_bp = Blueprint('profissionais', __name__, url_prefix='/api/profissionais')

LIMITE_PAGINACAO = 2147483647

@prof_bp.route('/', methods=['GET'])
def profissionais():
	cur = None

	try:
		parametros: dict[str, int] = {}
		for nome, padrao, limite in (
			('page_size', 10, 100),
			('page', 1, LIMITE_PAGINACAO),
			('preco_max', None, LIMITE_PAGINACAO),
		):
			valor = request.args.get(nome, padrao)

			if valor is None:
				continue

			try:
				valor = int(valor)
			except (TypeError, ValueError):
				return jsonify({ 'error': f'{nome} deve ser um numero inteiro' }), 400

			if valor < 1 or valor > limite:
				return jsonify({ 'error': f'{nome} deve estar entre 1 e {limite}' }), 400

			parametros[nome] = valor

		page_size = parametros['page_size']
		page = parametros['page']
		preco_max = parametros.get('preco_max')
		conselho = request.args.get('tipo_conselho', 'crp').strip().upper()

		if conselho not in ('CRP', 'CRM'):
			return jsonify({ 'error': 'tipo_conselho deve ser CRP ou CRM' }), 400

		offset = (page - 1) * page_size

		if offset > LIMITE_PAGINACAO:
			return jsonify({ 'error': f'offset deve ser no maximo {LIMITE_PAGINACAO}' }), 400

		filtros = """
		FROM PROFISSIONAL p
		INNER JOIN USUARIO u ON u.ID_USUARIO = p.USUARIO_ID
		WHERE u.ATIVO = TRUE
		AND LOWER(p.CONSELHO_TIPO) = LOWER(?)
		"""
		params: list[str | int] = [conselho]

		if preco_max is not None:
			filtros += " AND p.PRECO_HORA BETWEEN 0 AND ?"
			params.append(preco_max)

		query = """
		SELECT FIRST ? SKIP ? u.ID_USUARIO
			 , u.NOME
			 , p.DESCRICAO
			 , p.CONSELHO_NUMERO
			 , p.CONSELHO_TIPO
			 , p.PRECO_HORA AS PRECO_CENTAVOS
		""" + filtros + " ORDER BY u.ID_USUARIO"

		con = get_connection()
		cur = con.cursor()
		cur.execute(query, (page_size, offset, *params))
		resultados = cur.fetchall()

		columns = [desc[0].lower() for desc in cur.description]
		payload = [dict(zip(columns, row)) for row in resultados]

		cur.execute("SELECT COUNT(*) " + filtros, tuple(params))
		total_res = cur.fetchone()

		if not total_res:
			raise RuntimeError("Banco nao retornou a contagem")

		total = total_res[0]

		total_pages = (total + page_size - 1) // page_size

		return jsonify({
			'message': 'Profissionais obtidos com sucesso',
			'page': page,
			'page_size': page_size,
			'total': total,
			'total_pages': total_pages,
			'profissionais': payload
		}), 200
	except Exception as e:
		print(f"[{__name__}]: {str(e)}")
		return jsonify({ 'error': 'Internal Server Error' }), 500
	finally:
		if cur is not None:
			cur.close()

@prof_bp.route('/<int:id>', methods=['GET'])
def profissional(id):
	con = get_connection()
	cur = con.cursor()

	try:
		cur.execute("""
		SELECT u.ID_USUARIO
			 , u.NOME
			 , p.DESCRICAO
			 , p.CONSELHO_NUMERO
			 , p.CONSELHO_TIPO
			 , p.PRECO_HORA AS PRECO_CENTAVOS
		FROM PROFISSIONAL p
		INNER JOIN USUARIO u ON u.ID_USUARIO = p.USUARIO_ID
		WHERE usuario_id = ?""", (id,))

		resultado = cur.fetchone()

		if resultado is None:
			return jsonify({ 'error': 'Profissional não encontrado' }), 404

		columns = [desc[0].lower() for desc in cur.description]
		payload = dict(zip(columns, resultado))

		return jsonify({ 'message': 'Profissionais obtidos com sucesso', 'profissionais': payload }), 200
	except Exception as e:
		print(f"[{__name__}]: {str(e)}")
		return jsonify({ 'error': 'Internal Server Error' }), 500
	finally:
		if cur is not None:
			cur.close()


@prof_bp.route('/', methods=['POST'])
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
