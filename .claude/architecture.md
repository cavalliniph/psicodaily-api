# Arquitetura — PsicoDaily API

Backend Flask que conecta pacientes (`PACIENTE`) a profissionais (`PSICOLOGO`, `PSIQUIATRA`): diário de humor/sono, agendamento de sessões, prontuário, encaminhamentos, pagamento PIX e videochamada WebRTC.

## Visão geral

```
psicodaily-front (Vercel / Vite :5173)
        │  HTTPS + cookie access_token (JWT)      WebSocket /ws/signaling, /ws/chat
        ▼                                          ▼
┌──────────────────── gunicorn gthread (1 processo, 32 threads) ───────────────────┐
│ app.py ── Blueprints em view/*.py ── services/*_service.py ── funcao.py (puro)    │
│                    │                    │                     │                   │
│          database/db.py (pool)   services/upload_service   services/signaling_*   │
└────────────────────┼────────────────────┼─────────────────────┼───────────────────┘
                     ▼                    ▼                     ▼
            Firebird 4 (BANCO.FDB)   Cloudflare R2 (fotos,   salas em memória
                                     anexos privados)
                                     Arkhé (PIX)  Gmail SMTP (códigos)
```

## Camadas

| Pasta / arquivo | Papel |
|---|---|
| `app.py` | Cria o app, registra blueprints, `sock` (flask-sock), CORS (`config.ORIGENS_FRONT`, as mesmas que o handshake WS aceita) e os `errorhandler` (`ErroNegocio` → `{'error'}`; exceção inesperada → log + 500). |
| `config.py` | `SECRET_KEY` do `.env`. |
| `view/` | Rotas HTTP/WS, uma blueprint por domínio. Só leem o `request`, chamam o service e montam a resposta. |
| `funcao.py` | Validadores e normalizadores puros (senha, CPF, e-mail, telefone, nome, imagem, conselho, valor, abordagem, modalidade). |
| `util/usuarios.py` | Decorators `usuario_autenticado` / `profissional_autenticado`. |
| `services/` | Um `<dominio>_service.py` por blueprint (`auth`, `usuarios`, `registros`, `prontuario`, `profissionais`, `consultas`, `encaminhamentos`, `pagamentos`) com regras e SQL; `email_service` (SMTP + Jinja); `erros.py` (`ErroNegocio`); `upload_service` (R2 via boto3 + Pillow) e `signaling_service` (salas WebRTC). |
| `database/` | `db.py` (pool, `transacao()`, `banco_responde()`), `migrations/` (schema versionado; `0001_inicial.sql` é o baseline de produção), `migrar.py` (aplica as pendentes), `seed.sql` (dados fictícios de dev e CI). O `BANCO.FDB` local (gitignored) é só de dev. |
| `templates/` | `email_codigo.html` (Jinja) para códigos de ativação/recuperação. |
| `tests/` | pytest (`test_rotas.py` fixa status e chaves de todas as rotas); `conftest.py` com os fixtures de cliente por papel e de limpeza, `apoio.py` com IDs do seed e helpers. Precisam do Firebird no ar e desfazem o que criam. |

Não há ORM nem modelos: SQL parametrizado (`?`) direto no Firebird.

### Decisão: regras de negócio em `services/` (19/10/2026)

Antes, cada rota de `view/` abria conexão, validava, executava SQL e montava a resposta, e `funcao.py` misturava validadores puros com I/O (e-mail, upload, `criar_usuario_base` lendo `request`). Isso duplicava código (`login` × `login_mobile`, decode manual de token em `consultas`/`pagamentos`), fazia `view/prontuario.py` importar de `view/registros.py` e impedia reaproveitar regras fora do HTTP (WebSocket, jobs, webhook do WhatsApp, ferramentas do agente de IA). Por isso as camadas são:

- **`view/`**: só HTTP. Lê `request`, aplica o decorator de auth, chama o service e monta `jsonify`/headers. Não importa `get_connection` nem tem SQL.
- **`services/<dominio>_service.py`**: regras, SQL, transação e APIs externas. Funções simples (sem classes) que recebem valores já parseados e devolvem `dict`/`list`. **Não importa de `flask`** (`flask_bcrypt` pode). Erro de regra sai como `ErroNegocio(mensagem, status, **extra)` (`services/erros.py`), convertido em `{'error': msg, **extra}` por um `errorhandler` único no `app.py`.
- **`database/db.py`**: `transacao()` (context manager) faz commit no sucesso e devolve a conexão ao pool em qualquer caso.
- **`funcao.py`**: só validadores e normalizadores puros.

Sem repositórios, DTOs ou injeção de dependência: um nível a mais, não três. Migração concluída em 19/10/2026 (`plans/ultima-sprint.md`, fase 1), sem mudança de comportamento além do texto dos 500 e do 401 sem cookie em `consultas`/`pagamentos`, que agora vêm dos decorators.

## Rotas

| Prefixo | Rotas | Quem acessa |
|---|---|---|
| `/api/auth` | `POST login`, `login_mobile`, `verificar_codigo`, `esqueci_senha`, `alterar_senha`, `alterar_senha_logado`, `logout` | público / logado |
| `/api/usuarios` | `GET/PUT/PATCH /me`, `GET/PUT /me/preferencias` (questionário do paciente: `motivos` até 3 de `AREAS_ATUACAO`, `abordagem`, `modalidade`, `idioma`, `preco_max` em centavos, todos opcionais; o PUT substitui tudo; o GET devolve também `opcoes`), `GET /`, `POST /` (cadastro paciente), `POST /logout` | logado / público |
| `/api/favoritos` | `GET /` (favoritos do paciente com `nome`, `especialidade`, `preco_hora`, `foto_url`, `favoritado_em` e `proximo_horario` dos próximos 14 dias, ou `null`), `POST /<id_profissional>` (201 ao criar, 200 se já era favorito), `DELETE /<id_profissional>` | paciente |
| `/api/conteudos` | `POST /`, `PATCH /<id>`, `DELETE /<id>`: artigos do próprio profissional (`titulo` 3–200, `corpo` até 20000, texto ou Markdown, tag HTML recusada). Conteúdo de outro dono dá 404 | profissional |
| `/api/profissionais` | `GET /` (filtros `nome`, `especialidade`, `tipo_conselho`, `preco_min/max`, `disponibilidade_inicio/fim`, `abordagem`, `modalidade`, `avaliacao_min`, `idioma`, `area_atuacao` (um valor de `IDIOMAS`/`AREAS_ATUACAO` cada), `experiencia_min` (anos; sem `ano_inicio_atuacao` fica de fora), `ordenar=preco\|avaliacao\|experiencia`, sem ele por ID), `GET /recomendados` (paciente: até 10 ativos por `pontuacao`, pesos em `PESOS_RECOMENDACAO` + avaliação/5; `questionario_respondido`), `GET /<id>`, `GET /<id>/conteudos` (artigos do profissional, mais recentes primeiro), `GET /<id>/disponibilidade` (janelas semanais `{dia_semana, inicio, fim}`, 0 = domingo), `PUT /me/disponibilidade` (`{"janelas": [...]}` substitui todas; sem sobreposição no mesmo dia), `GET /<id>/horarios?de=&ate=&duracao=` (horários livres em fatias de `duracao` min, 30–120, padrão 60; período de até 31 dias, padrão 14), `POST /` (cadastro), `PATCH /me` (descrição, preço e os campos opcionais do perfil; `null`/vazio limpa). Cada profissional vem com `especialidade`, `abordagem`, `modalidade`, `formacao`, `ano_inicio_atuacao`, `anos_experiencia` (calculado), `idiomas` e `areas_atuacao` (listas, `[]` se vazio), `video_url` (embed), `avaliacao` (média com 1 casa ou `null`) e `total_avaliacoes` | público / profissional |
| `/api/registros` | `GET/POST /` (diário, paginação `limite`/`antes`), `GET /evolucao?dias=7\|30\|90` (`resumo` + `evolucaoHumor`, mesmo cálculo e formato do prontuário) | só paciente, próprios registros |
| `/api/consultas` | `GET /` (inclui `nota_avaliacao`), `POST /` (agendar; o horário tem de caber numa janela da agenda, senão 409, exceto para profissional sem nenhuma janela), `PATCH /<sessao_id>` (horário, link, status; só profissional, cancela a qualquer hora), `POST /<sessao_id>/cancelar` (só paciente, até 15 min antes, senão 409; devolve `sessao` e `reembolso_centavos`), `POST /<sessao_id>/avaliacao` (nota 1–5 e comentário; só paciente, sessão `REALIZADO`, uma vez) | logado |
| `/api/prontuario` | `GET /<paciente_id>?dias=7\|30\|90` | profissional com sessão não cancelada com o paciente |
| `/api/encaminhamentos` | `GET /`, `POST /` | profissional |
| `/api/pagamentos` | `POST /cobranca` (`{id_sessao, metodo: PIX|BOLETO|CARTAO, cartao}`, `metodo` padrão PIX; 409 se já paga; reaproveita a pendente do mesmo método; recusa da Arkhé vira 402 com o motivo dela), `GET /cobranca/<id>` (Pix ou boleto; 404 para quem não é da sessão), `GET /cobranca/<id>/pdf` (PDF do boleto), `GET /financeiro` | paciente (cobrança) / participantes (consulta) / logado |
| `/api/notificacoes` | `GET /?limite=&antes=` (`notificacoes` com `tipo`, `titulo`, `mensagem`, `dados` JSON e `lida`; `nao_lidas`; `proximo_cursor`), `POST /lidas` (`{"ids": [...]}` ou sem corpo para todas; devolve `atualizadas`) | logado, só as próprias |
| `/api/lista-espera` | `POST /` (`id_profissional`, `inicio`, `fim` no formato do agendamento; janela futura de até 31 dias), `GET /` (entradas cuja janela não terminou, com `avisado_em`), `DELETE /<id>` | paciente |
| `/api/dashboard` | `GET /`: `papel`, `proximas_sessoes` (até 5, `AGENDADO`/`CONFIRMADO` futuras), `nao_lidas`; paciente também `pagamentos` (últimos 5) e `favoritos`; profissional também `ganhos_mes_centavos` (`PAGAMENTO` pago no mês), `atendimentos_mes` e `pacientes` | paciente e profissional (admin usa `/api/admin/metricas`) |
| `/api/chat` | `GET /` (conversas: todos com sessão não cancelada, com `ultima_mensagem` e `nao_lidas`), `GET /<outro_id>?limite=&antes=\|depois=` (ordem cronológica; sem cursor as últimas, `antes` histórico, `depois` polling; marca as recebidas como lidas), `POST /<outro_id>` (`{"texto"}`, 1–2000), `POST /<outro_id>/arquivo` (multipart `arquivo` PDF/JPG/PNG até 10 MB, tipo pelos primeiros bytes, e `texto` opcional; 413 acima do limite), `GET /arquivo/<mensagem_id>` (`{url, nome, expira_em_segundos}`: URL assinada de 5 min, só para participantes). Toda mensagem traz `arquivo` (`{nome, tipo, tamanho}` ou `null`) | paciente e profissional com vínculo (senão 404) |
| `/api/admin` | `GET /metricas?dias=7\|30\|90\|365` (`faturamento_centavos` = soma de `PAGAMENTO` pago no período, `consultas_por_status` pela data da sessão, `usuarios_ativos` e `novos_cadastros` por papel, `avaliacao` `{media, total}`), `GET /auditoria?usuario_id=&acao=&limite=&antes=` (mais recentes primeiro, `proximo_cursor`), `GET /reembolsos?status=PENDENTE|PAGO` (com nome e CPF do paciente), `POST /reembolsos/<id>/pagar` (`{}` faz Pix pela Arkhé para a chave CPF, `{"manual": true}` só marca; 502 com o motivo se a Arkhé recusar, 409 se já pago) | admin (`@admin_autenticado`) |
| `/api/assistente` | `POST /` (`{"mensagens": [{role: user\|assistant, content}]}`, 1–40 mensagens de até 2000 caracteres, começa e termina com `user`) → `{resposta, agendamento}`; `agendamento` é `null` ou o corpo pronto para `POST /api/consultas` | só paciente |
| `/ws/chat` | WebSocket só de saída: empurra `{"type": "mensagem", paciente_id, profissional_id, mensagem}` de toda conversa do usuário (todas as abas/aparelhos). Envio e histórico seguem no REST; conexões em memória em `chat_service` (processo único) | paciente e profissional (cookie ou Bearer) |
| `/ws/signaling?sessao_id=` | WebSocket WebRTC: repassa `offer`/`answer`/`ice-candidate` e emite `peers`, `peer-joined`, `peer-left` | participantes da sessão |

## Modelo de dados (`database/migrations/`)

- `USUARIO`: base de todos (role `PACIENTE/PSICOLOGO/PSIQUIATRA/ADMIN`, CPF, senha bcrypt, `codigo` de 6 dígitos para ativação/recuperação, `ativo`, `CRIADO_EM`, `NULL` para quem se cadastrou antes da migration 0009). Não há rota que crie ADMIN: promover com `UPDATE USUARIO SET USUARIO_ROLE = 'ADMIN'` e novo login (o papel vai no token).
- `PROFISSIONAL`: 1:1 com usuário (`USUARIO_ID`), conselho CRP/CRM, preço, dias de atendimento, `ABORDAGEM` (lista `ABORDAGENS` em `funcao.py`) e `MODALIDADE` (`dm_modalidade`: `ONLINE/PRESENCIAL/AMBAS`). O filtro de modalidade inclui sempre `AMBAS`. Perfil completo, todos opcionais: `FORMACAO`, `ANO_INICIO_ATUACAO` (guarda o ano, não os anos, para não envelhecer), `IDIOMAS` e `AREAS_ATUACAO` (nomes canônicos de `IDIOMAS`/`AREAS_ATUACAO` em `funcao.py`, separados por vírgula; até 8 áreas) e `VIDEO_URL` (só YouTube/Vimeo, gravado já como URL de embed `youtube-nocookie.com/embed/<id>` ou `player.vimeo.com/video/<id>`). Os campos opcionais ficam em `CAMPOS_OPCIONAIS` (`services/profissionais_service.py`): incluir um campo novo é uma linha ali, mais a coluna.
- `REGISTRO`: diário do paciente (humor, sono, alimentação, exercício, anotação BLOB).
- `ENCAMINHAMENTO`: paciente → profissional, status `ATIVO/CONCLUIDO/CANCELADO`. Só cria quem tem sessão não cancelada com o paciente; `GET` lista só os do próprio profissional.
- `SESSAO`: consulta paciente × profissional; `STATUS` `AGENDADO/CONFIRMADO/REALIZADO/CANCELADO`, `VALOR_CENTAVOS` inteiro, FK opcional para encaminhamento e conversa.
- `DISPONIBILIDADE`: janelas semanais do profissional (`DIA_SEMANA` 0 = domingo, como `EXTRACT(WEEKDAY)`; `HORA_INICIO`/`HORA_FIM`). Os dias do cadastro viram janelas das 8h às 18h. `disponibilidade_service.filtro_sql` é a regra única usada no agendamento e no filtro de disponibilidade da busca; o reagendamento pelo próprio profissional não passa por ela.
- `AUDITORIA`: `USUARIO_ID` (sem FK, sobrevive à exclusão), `ACAO`, `ENTIDADE`, `ENTIDADE_ID`, `IP`, `CRIADO_EM`. `services/auditoria_service.py`: `auditar(cur, ...)` grava na transação da ação (rollback leva junto) e `auditar_avulso` usa transação própria (falha de login). Ações em `ACOES`: `LOGIN`, `LOGIN_FALHA`, `PRONTUARIO_ACESSO`, `SESSAO_AGENDADA`, `SESSAO_ALTERADA`, `ENCAMINHAMENTO_CRIADO`, `SENHA_ALTERADA`, `EMAIL_ALTERADO`. O IP vem de `IP_ATUAL` (contextvar), preenchido no `before_request` do `app.py` com o último `X-Forwarded-For` (o proxy do Northflank). Testes que disparam essas ações apagam as linhas criadas.
- `NOTIFICACAO`: `USUARIO_ID`, `TIPO` (`TIPOS` em `services/notificacoes_service.py`), `TITULO`/`MENSAGEM` prontos para exibir, `DADOS` (JSON), `LIDA`. `notificar(cur, ...)` grava na transação da ação e **devolve** o e-mail: o chamador chama `enviar_emails(...)` depois do `with transacao()`, para não avisar de algo que sofreu rollback. Hoje o e-mail é o único canal.
- `PREFERENCIA_PACIENTE`: `PACIENTE_ID` (PK), `RESPOSTAS` (JSON validado por `preferencias_service`), `ATUALIZADO_EM`.
- `MENSAGEM`: chat; a conversa é o par `PACIENTE_ID`+`PROFISSIONAL_ID`, `REMETENTE_ID`, `TEXTO` UTF8 (vazio quando é só anexo), `LIDA`, `ARQUIVO_CHAVE`/`ARQUIVO_NOME`/`ARQUIVO_TIPO`/`ARQUIVO_TAMANHO` (nulos sem anexo). `CONVERSA`/`CONVERSA_MENSAGEM` do baseline estão sem uso. Novas mensagens chegam pelo `/ws/chat`; ao reconectar, o front busca o que perdeu com `depois`.
- `PAGAMENTO`: `SESSAO_ID`, `ID_COBRANCA_ARKHE` (único por método desde a 0017: no cartão é o `id_compra` da Arkhé, de outra tabela dela), `METODO` (`PIX`/`BOLETO`/`CARTAO`), `VALOR_CENTAVOS`, `STATUS` `PENDENTE`/`PAGO`, `PAGO_EM`. Só o que passou pela API: cobranças criadas antes da migration 0012 não existem aqui.
- `REEMBOLSO`: um por `PAGAMENTO` (único), `VALOR_CENTAVOS` integral, `STATUS` `PENDENTE`/`PAGO`, `ID_MOVIMENTACAO_ARKHE` quando pago por Pix da Arkhé. Criado na transação do cancelamento (paciente ou profissional) e quando uma cobrança é paga depois que a sessão já foi cancelada.
- `LISTA_ESPERA`: paciente, profissional, janela `INICIO_DESEJADO`–`FIM_DESEJADO`, `AVISADO_EM`. Quando o profissional cancela uma sessão futura (`consultas_service.atualizar`), `lista_espera_service.avisar_vaga` avisa a entrada mais antiga ainda não avisada cuja janela cobre o horário, exceto a do próprio paciente da sessão. Não reserva a vaga.
- `FAVORITO`: PK `(PACIENTE_ID, PROFISSIONAL_ID)`, apagado junto com qualquer um dos dois.
- `CONTEUDO`: artigos do profissional (`TITULO`, `CORPO` BLOB UTF8, `PUBLICADO_EM`, `ATUALIZADO_EM`), apagados junto com o profissional.
- `AVALIACAO`: nota 1–5 e comentário do paciente por sessão (`UQ_AVALIACAO_SESSAO`); a busca junta a média por profissional numa tabela derivada (`ORIGEM_PROFISSIONAL` em `services/profissionais_service.py`).
- `CONVERSA`, `CONVERSA_PARTICIPANTE`, `CONVERSA_MENSAGEM`: existem no schema, sem rotas ainda.

Valores enumerados são `DOMAIN`s com `CHECK`; a validação das rotas espelha esses domínios (ex.: `DOMINIOS` em `services/registros_service.py`).

## Fluxos principais

**Autenticação.** `POST /api/auth/login` confere bcrypt e `ativo`, gera JWT HS256 com `{id_usuario, usuario_role, iat, exp}` (8h) e grava no cookie `access_token` (`httponly`, `secure`, `SameSite=None`, `max_age` 8h). Os decorators e os dois WebSockets passam por `auth_service.usuario_do_token`, que recusa token sem `exp`, vencido, de usuário inativo ou com `iat` anterior a `USUARIO.SENHA_ALTERADA_EM` (UTC); o payload vira o primeiro argumento da rota. Toda troca de senha grava `SENHA_ALTERADA_EM` e derruba os tokens antigos; `alterar_senha_logado` devolve cookie novo. Cadastro e "esqueci a senha" gravam `USUARIO.codigo` e mandam e-mail em thread (`enviar_email_codigo_async`). O código de recuperação expira em 15 min (`CODIGO_EXPIRA_EM`), o de ativação não expira (não há reenvio; um código de "esqueci a senha" também ativa). Na 5ª falha (`CODIGO_TENTATIVAS`) o código é apagado.

**Pool de conexões (`database/db.py`).** `LifoQueue` de até 10 conexões `fdb`. `get_connection()` reaproveita uma livre (testa com `SELECT 1 FROM RDB$DATABASE`, descarta se morta) ou abre nova. `ConexaoDoPool.close()` faz **rollback** e devolve ao pool, então toda rota precisa de `commit()` explícito e de `close()` no `finally`.

**Agendamento.** `POST /api/consultas` usa `reservar_participantes`: `SELECT ... WITH LOCK` nos dois usuários em ordem fixa de ID, serializando agendamentos concorrentes sem deadlock, e então checa conflito de horário com sessões não canceladas. `PATCH` muda status (`REALIZADO` só após o fim; `CANCELADO`) separado de horário/link.

**Videochamada.** O WebSocket valida cookie, `sessao_id`, se o usuário é participante, status ≠ `CANCELADO` e janela (abre 15 min antes do início até o fim). Fecha a conexão do banco **antes** de entrar no loop e repassa `offer/answer/ice-candidate` aos outros sockets da sala `sessao:<id>`. Presença: quem entra recebe `{"type": "peers", "participantes": [{id_usuario, nome}]}`; os outros recebem `peer-joined` e, na saída, `peer-left` (mesmos campos, nunca o e-mail). Se o outro participante não está na sala, `consultas_service.avisar_entrada_na_sala` manda um e-mail com o link `FRONT_URL/videochamada/<id>`, uma vez por sessão e por quem entrou (dedupe em memória). Salas vivem num `dict` em memória protegido por um lock, por isso há **um único processo**; cada chamada ocupa uma thread.

No front, a página em uso é `TesteVideo.jsx`, que ignora os eventos de presença até alguém tratá-los. `src/utils/videoCall.js` espera outro protocolo (`join`/`joined`/`ready` com `call_id`) que o backend nunca implementou e não é importado por nenhuma página.

**Pagamento.** `POST /api/pagamentos/cobranca` lê `VALOR_CENTAVOS` da sessão do paciente e cobra na Arkhé (`ARKHE_BASE_URL`, credenciais `CLIENT_ID`/`CLIENT_SECRET`, via `urllib`), convertendo para reais: Pix (`/cobrancas/pix`) e boleto (`/cobrancas/boletos`, pagador pelo CPF do paciente, que precisa ter conta na Arkhé, vencendo no dia da consulta) ficam `PENDENTE` em `PAGAMENTO`; o cartão (`/vendas/cartao`, só cartão emitido pela Arkhé) é aprovado na hora e já grava `PAGO`, confirma a sessão e notifica. Os dados do cartão só passam pela API, não são gravados. Antes de cobrar de novo, as pendentes são consultadas na Arkhé, para não cobrar uma sessão que já foi paga. A Arkhé não cancela nem estorna cobrança: trocar de método deixa a anterior aberta. Não há webhook: o status só muda quando alguém consulta `GET /cobranca/<id>`; ao ver `status` 1 da Arkhé, `_confirmar` marca `PAGO`, passa a sessão de `AGENDADO` para `CONFIRMADO` e notifica o profissional (`PAGAMENTO_CONFIRMADO`), uma vez só. `GET /financeiro` agrega saldo, resumo e movimentações da conta Arkhé.

**Cancelamento e reembolso (24).** O paciente cancela por `POST /api/consultas/<id>/cancelar` até `ANTECEDENCIA_CANCELAMENTO` (15 min) antes do início; depois disso não cancela. O profissional cancela pelo `PATCH` a qualquer hora. Os dois caminhos passam por `consultas_service._ao_cancelar`, na mesma transação: `pagamentos_service.registrar_reembolso` (100% de cada pagamento pago), `lista_espera_service.avisar_vaga` e notificação `SESSAO_CANCELADA` à outra parte. A Arkhé não estorna (o código dela é público em github.com/GPontin78/back_arkche): o admin paga o reembolso em `POST /api/admin/reembolsos/<id>/pagar`, que tenta `POST /api/v1/pagamentos/pix` da Arkhé para a chave CPF do paciente com `X-Idempotency-Key: psicodaily-reembolso-<id>`. Isso só funciona se o outro grupo incluir o nosso Client ID em `ARKHE_API_PAGAMENTOS_CLIENT_IDS` e se o paciente tiver cadastrado o CPF como chave Pix lá, o que não é automático. Senão, a rota devolve o motivo e o admin paga por fora com `{"manual": true}`. Não há tela de "conta Arkhé": a Arkhé só identifica cliente por CPF/CNPJ e não tem API de vínculo para terceiros, então usamos o CPF do cadastro (decidido em 22/10/2026).

**Assistente de IA.** `services/assistente_service.py` chama um LLM no plano gratuito do Groq (`openai/gpt-oss-120b`, API no formato da OpenAI via `urllib`, `GROQ_API_KEY`) num loop de tool calling de até 8 rodadas. As ferramentas são as funções que já existem: `profissionais_service.buscar`/`recomendados`, `disponibilidade_service.horarios_livres`, `consultas_service.listar`, e o paciente vem sempre do token. O assistente **não grava nada**: `propor_agendamento` só confere o horário em `horarios_livres` e devolve `agendamento`, que o front mostra como botão e envia ao `POST /api/consultas`, que revalida tudo. Sem estado no servidor: o front reenvia o histórico em texto a cada mensagem. `ErroNegocio` ou argumento inválido de uma ferramenta volta ao modelo como `Erro: ...`; falha do Groq vira 503 (429 = limite gratuito). Profissional sem nenhuma janela de agenda não tem horários em `horarios_livres`, então o assistente não propõe horário para ele. Plano gratuito: o Groq pode guardar logs; não é adequado a dados reais de pacientes.

**Fotos de perfil.** Upload pelo Pillow (corrige EXIF, converte para JPEG, máx. 512×512) para o bucket R2 `psicodaily` em `usuarios/<id>.jpg`, `Cache-Control: no-cache`. A URL é derivada do ID (`url_foto_usuario`), sem coluna no banco.

**Arquivos privados (F6).** Bucket R2 `psicodaily-objects` (`R2_BUCKET_PRIVADO`), sem acesso público, mesmo endpoint e token das fotos. `upload_service.enviar_privado` grava e `url_assinada` gera a URL de download (localmente, sem chamar o R2) com `Content-Disposition: attachment` e o nome original. Anexos do chat ficam em `chat/<paciente>-<profissional>/<uuid>.<ext>`; o upload acontece fora da transação, e se o `INSERT` falhar depois o objeto fica órfão. CORS do bucket: só `GET`/`HEAD` das origens do front.

## Execução e deploy

- **Produção no Northflank** (combined service com build da `main`). Toda decisão de infra parte disso. Firebird não é addon do Northflank, então o banco tem que viver num volume Single Read/Write do serviço: 1 instância e alguns segundos fora do ar por deploy. Desde 19/10/2026, o banco de produção fica no volume `firebird-data`, montado em `/var/lib/firebird/data` (`DB_DATABASE=/var/lib/firebird/data/BANCO.FDB`), com backups `gbak` em `/var/lib/firebird/data/backups` e readiness probe em `/api/saude`. Snapshot de volume não está habilitado na conta, então ainda não há backup fora do volume.

- **Docker**: `python:3.14-slim` + Firebird 4 no mesmo container, sem `.FDB` na imagem. O banco fica em `DB_DATABASE` (padrão `/data/BANCO.FDB`, o volume). O `docker-entrypoint.sh`:
  1. cria o banco, se ele não existir, só com `CRIAR_BANCO=1` (modo embarcado, antes do servidor: o `CREATE DATABASE` remoto recusa a senha inicial da imagem); senão sai com erro;
  2. sobe o Firebird;
  3. troca a senha do SYSDBA para `DB_PASSWORD`. O `security4.fdb` mora na imagem, então isso acontece a cada boot;
  4. faz `gbak` em `/data/backups`, guardando os 5 últimos;
  5. roda `migrar.py`;
  6. sobe o gunicorn em `:8000`.

  Se qualquer passo falhar, o container sai antes de receber tráfego. `GET /api/saude` é o readiness probe. `TZ=America/Sao_Paulo` (as rotas comparam com `datetime.now()` local).
- **CI**: `.github/workflows/ci.yml` (Firebird 4 oficial em serviço, banco do zero com migrations + seed, `pytest`) em todo push e PR. Não faz deploy.
- **Dev (WSL)**: `run.sh` sobe um gunicorn ouvindo em `127.0.0.1:8000` e `:8001`.
- **Por que gthread e não gevent**: `fdb` chama `libfbclient` via ctypes, o que bloquearia o loop do gevent.

## Pontos de atenção

- Checkup de segurança de 19/10/2026 em `decisions/seguranca-adiada.md` (achados S1–S23, adiados em 20/10/2026 até as features ficarem prontas). Os mais graves:
  - Repo **público** com a senha SMTP do Gmail hard-coded em `services/email_service.py` (`enviar_email`) e com o `BANCO.FDB`, que tem dados reais.
  - ~~Código sem expiração nem limite de tentativas~~: resolvido (S3). Sem rate limit (S11), pedir códigos novos ainda permite tentar 5 por e-mail enviado.
  - ~~JWT sem `exp`~~: resolvido (S4). Logout ainda não revoga o token no servidor (refresh token e sessões ficam para a feature 10).
  - ~~`GET /api/encaminhamentos` lista os de todos os profissionais~~: resolvido (S5/S6).
  - ~~WebSocket sem checagem de `Origin`~~: resolvido (S7), `origem_permitida()` recusa `Origin` fora de `ORIGENS_FRONT`; sem `Origin` (app mobile) passa e depende do token.
- `dias_atendimento` é validado no cadastro de profissional, mas não é gravado: não existe modelo de agenda.
- O estado das salas em memória impede escalar horizontalmente sem um broker (ex.: Redis pub/sub).
- O `BANCO.FDB` saiu do git em 19/10/2026, mas continua no histórico público até um `git filter-repo` ou até o repo ficar privado. Mudança de schema é sempre uma migration nova.
- Backup só existe dentro do próprio volume (`gbak` a cada deploy). Se o volume se perder, perde-se tudo: falta um backup diário para fora (pendência da F0).
- O charset padrão do banco é `ISO8859_1`. As colunas de texto livre (`USUARIO.NOME`, `USUARIO.EMAIL`, `PROFISSIONAL.FORMACAO`, `AVALIACAO.COMENTARIO`) passaram para UTF8 nas migrations 0002 a 0004, e os BLOBs de texto já eram UTF8. As demais `VARCHAR` continuam em ISO8859_1 porque só recebem vocabulário fixo, dígitos ou URL validada. Coluna de texto nova precisa declarar `CHARACTER SET UTF8`.
