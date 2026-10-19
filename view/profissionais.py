from flask import Blueprint, jsonify, request
from datetime import datetime
from database.db import get_connection
from services.upload_service import upload_service
from util.usuarios import profissional_autenticado
from funcao import (
	ESPECIALIDADES_PROFISSIONAIS,
	criar_usuario_base,
	enviar_email_ativacao,
	normalizar_abordagem,
	normalizar_conselho,
	normalizar_modalidade,
	normalizar_texto,
	normalizar_valor_sessao,
	obter_campo,
	obter_dias_atendimento,
	resposta_erro,
)

prof_bp = Blueprint('profissionais', __name__, url_prefix='/api/profissionais')

LIMITE_PAGINACAO = 2147483647

COLUNAS_PROFISSIONAL = """
	u.ID_USUARIO
	 , u.NOME
	 , p.DESCRICAO
	 , p.CONSELHO_NUMERO
	 , p.CONSELHO_TIPO
	 , p.PRECO_HORA AS PRECO_CENTAVOS
	 , p.ESPECIALIDADE
	 , p.ABORDAGEM
	 , p.MODALIDADE
"""

ORIGEM_PROFISSIONAL = """
FROM PROFISSIONAL p
INNER JOIN USUARIO u ON u.ID_USUARIO = p.USUARIO_ID
"""


def serializar_profissional(colunas, linha):
	profissional = dict(zip(colunas, linha))
	profissional['foto_url'] = upload_service.url_foto_usuario(profissional['id_usuario'])
	return profissional

@prof_bp.route('/', methods=['GET'])
def profissionais():
	con = None
	cur = None

	try:
		parametros: dict[str, int] = {}
		for nome, padrao, limite in (
			('page_size', 10, 100),
			('page', 1, LIMITE_PAGINACAO),
			('preco_min', None, LIMITE_PAGINACAO),
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
		preco_min = parametros.get('preco_min')
		preco_max = parametros.get('preco_max')

		if preco_min is not None and preco_max is not None and preco_min > preco_max:
			return resposta_erro('preco_min nao pode ser maior que preco_max')

		nome = request.args.get('nome', '').strip()

		especialidade = None
		if 'especialidade' in request.args:
			especialidade_recebida = normalizar_texto(request.args['especialidade'].strip())
			especialidade = next(
				(nome for nome in ESPECIALIDADES_PROFISSIONAIS if normalizar_texto(nome) == especialidade_recebida),
				None,
			)
			if especialidade is None:
				return resposta_erro('Especialidade deve ser Psicologia ou Psiquiatria')

		conselho_padrao = ESPECIALIDADES_PROFISSIONAIS[especialidade]['conselho_tipo'] if especialidade else None
		conselho_recebido = request.args.get('tipo_conselho')
		conselho = conselho_recebido.strip().upper() if conselho_recebido else conselho_padrao

		if conselho is not None and conselho not in ('CRP', 'CRM'):
			return jsonify({ 'error': 'tipo_conselho deve ser CRP ou CRM' }), 400

		if especialidade and conselho != conselho_padrao:
			return resposta_erro('tipo_conselho incompativel com a especialidade')

		abordagem = None
		if 'abordagem' in request.args:
			abordagem = normalizar_abordagem(request.args['abordagem'])
			if abordagem is None:
				return resposta_erro('Abordagem invalida')

		modalidade = None
		if 'modalidade' in request.args:
			modalidade = normalizar_modalidade(request.args['modalidade'])
			if modalidade is None:
				return resposta_erro('Modalidade deve ser Online ou Presencial')

		inicio = None
		fim = None
		if 'disponibilidade_inicio' in request.args or 'disponibilidade_fim' in request.args:
			if not request.args.get('disponibilidade_inicio') or not request.args.get('disponibilidade_fim'):
				return resposta_erro('Informe disponibilidade_inicio e disponibilidade_fim juntos')
			try:
				inicio = datetime.strptime(request.args['disponibilidade_inicio'], '%Y-%m-%dT%H:%M')
				fim = datetime.strptime(request.args['disponibilidade_fim'], '%Y-%m-%dT%H:%M')
			except ValueError:
				return resposta_erro('Disponibilidade deve usar o formato AAAA-MM-DDTHH:MM, sem fuso horario')
			if fim <= inicio:
				return resposta_erro('disponibilidade_fim deve ser posterior a disponibilidade_inicio')

		offset = (page - 1) * page_size

		if offset > LIMITE_PAGINACAO:
			return jsonify({ 'error': f'offset deve ser no maximo {LIMITE_PAGINACAO}' }), 400

		filtros = ORIGEM_PROFISSIONAL + " WHERE u.ATIVO = TRUE"
		params: list[str | int | datetime] = []

		if conselho is not None:
			filtros += " AND LOWER(p.CONSELHO_TIPO) = LOWER(?)"
			params.append(conselho)

		if especialidade is not None:
			filtros += " AND LOWER(p.ESPECIALIDADE) = LOWER(?)"
			params.append(especialidade)

		if nome:
			filtros += " AND UPPER(u.NOME) CONTAINING UPPER(?)"
			params.append(nome)

		if abordagem is not None:
			filtros += " AND p.ABORDAGEM = ?"
			params.append(abordagem)

		if modalidade is not None:
			# Quem atende nos dois formatos aparece em qualquer filtro de modalidade.
			filtros += " AND p.MODALIDADE IN (?, 'AMBAS')"
			params.append(modalidade)

		if preco_min is not None:
			filtros += " AND p.PRECO_HORA >= ?"
			params.append(preco_min)

		if preco_max is not None:
			filtros += " AND p.PRECO_HORA BETWEEN 0 AND ?"
			params.append(preco_max)

		if inicio is not None and fim is not None:
			filtros += """
			AND NOT EXISTS (
				SELECT 1 FROM SESSAO s
				WHERE s.PROFISSIONAL_ID = p.USUARIO_ID
				AND s.STATUS <> 'CANCELADO'
				AND s.DATA_HORA_INICIO < ?
				AND s.DATA_HORA_FIM > ?
			)
			"""
			params.extend([fim, inicio])

		query = "SELECT FIRST ? SKIP ?" + COLUNAS_PROFISSIONAL + filtros + " ORDER BY u.ID_USUARIO"

		con = get_connection()
		cur = con.cursor()
		cur.execute(query, (page_size, offset, *params))
		resultados = cur.fetchall()

		columns = [desc[0].lower() for desc in cur.description]
		payload = [serializar_profissional(columns, row) for row in resultados]

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
		if con is not None:
			con.close()

@prof_bp.route('/<int:id>', methods=['GET'])
def profissional(id):
	con = get_connection()
	cur = con.cursor()

	try:
		cur.execute("SELECT" + COLUNAS_PROFISSIONAL + ORIGEM_PROFISSIONAL
					+ " WHERE p.USUARIO_ID = ? AND u.ATIVO = TRUE", (id,))

		resultado = cur.fetchone()

		if resultado is None:
			return jsonify({ 'error': 'Profissional não encontrado' }), 404

		columns = [desc[0].lower() for desc in cur.description]
		payload = serializar_profissional(columns, resultado)

		return jsonify({ 'message': 'Profissionais obtidos com sucesso', 'profissionais': payload }), 200
	except Exception as e:
		print(f"[{__name__}]: {str(e)}")
		return jsonify({ 'error': 'Internal Server Error' }), 500
	finally:
		if cur is not None:
			cur.close()
		if con is not None:
			con.close()


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
			return resposta_erro("Valor em reais deve ser positivo, ate 100000, com no maximo duas casas decimais")

		dias_atendimento, erro_dias = obter_dias_atendimento(formulario)

		if erro_dias:
			return resposta_erro(erro_dias)

		abordagem = None
		abordagem_recebida = obter_campo(formulario, 'abordagem')
		if abordagem_recebida:
			abordagem = normalizar_abordagem(abordagem_recebida)
			if abordagem is None:
				return resposta_erro("Abordagem invalida")

		modalidade = None
		modalidade_recebida = obter_campo(formulario, 'modalidade')
		if modalidade_recebida:
			modalidade = normalizar_modalidade(modalidade_recebida)
			if modalidade is None:
				return resposta_erro("Modalidade deve ser Online, Presencial ou Ambas")

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
							descricao,
							abordagem,
							modalidade
						) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
				 (usuario["id_usuario"], conselho_tipo, conselho_numero, especialidade, preco_hora, descricao,
				  abordagem, modalidade))

		con.commit()
		enviar_email_ativacao(usuario["email"], usuario["codigo"], usuario["nome"])

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
				"dias_atendimento": dias_atendimento,
				"abordagem": abordagem,
				"modalidade": modalidade
			}
		}), 201
	except Exception as e:
		print(f"houve um erro ao realizar o cadastro profissional: {str(e)}")
		con.rollback()
		return jsonify({ "error": "Internal server error" }), 500
	finally:
		if cur is not None:
			cur.close()
		if con is not None:
			con.close()


@prof_bp.route('/me', methods=['PATCH'])
@profissional_autenticado
def atualizar_profissional(dados_usuario):
	formulario = request.get_json(silent=True) or {}
	if not isinstance(formulario, dict) or not formulario or not set(formulario).issubset(
			{'descricao', 'preco_hora', 'abordagem', 'modalidade'}):
		return resposta_erro("Informe apenas descricao, preco_hora, abordagem e/ou modalidade")

	atualizacoes = {}
	if 'descricao' in formulario:
		descricao = obter_campo(formulario, 'descricao')
		if len(descricao) < 10 or len(descricao) > 1000:
			return resposta_erro("Descricao deve ter entre 10 e 1000 caracteres")
		atualizacoes['DESCRICAO'] = descricao
	if 'preco_hora' in formulario:
		preco_hora = normalizar_valor_sessao(obter_campo(formulario, 'preco_hora'))
		if preco_hora is None:
			return resposta_erro("Valor em reais deve ser positivo, ate 100000, com no maximo duas casas decimais")
		atualizacoes['PRECO_HORA'] = preco_hora
	# Vazio ou null limpa a coluna.
	for campo, normalizar, mensagem in (
		('abordagem', normalizar_abordagem, "Abordagem invalida"),
		('modalidade', normalizar_modalidade, "Modalidade deve ser Online, Presencial ou Ambas"),
	):
		if campo not in formulario:
			continue
		valor = formulario[campo]
		if valor is not None and not isinstance(valor, str):
			return resposta_erro(mensagem)
		if valor is None or not valor.strip():
			atualizacoes[campo.upper()] = None
			continue
		normalizado = normalizar(valor)
		if normalizado is None:
			return resposta_erro(mensagem)
		atualizacoes[campo.upper()] = normalizado

	con = get_connection()
	cur = con.cursor()
	try:
		definicoes = ", ".join(f"{coluna} = ?" for coluna in atualizacoes)
		cur.execute(f"UPDATE PROFISSIONAL SET {definicoes} WHERE USUARIO_ID = ?",
					(*atualizacoes.values(), dados_usuario.get('id_usuario')))
		con.commit()
		return jsonify({ 'message': 'Perfil profissional atualizado' }), 200
	except Exception as e:
		print(f"[{__name__}]: {str(e)}")
		con.rollback()
		return jsonify({ 'error': 'Internal Server Error' }), 500
	finally:
		cur.close()
		if con is not None:
			con.close()
