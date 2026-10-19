# Arquitetura — PsicoDaily API

Backend Flask que conecta pacientes (`PACIENTE`) a profissionais (`PSICOLOGO`, `PSIQUIATRA`): diário de humor/sono, agendamento de sessões, prontuário, encaminhamentos, pagamento PIX e videochamada WebRTC.

## Visão geral

```
psicodaily-front (Vercel / Vite :5173)
        │  HTTPS + cookie access_token (JWT)      WebSocket /ws/signaling
        ▼                                          ▼
┌──────────────────── gunicorn gthread (1 processo, 32 threads) ───────────────────┐
│ app.py ── Blueprints em view/*.py ── services/*_service.py ── funcao.py (puro)    │
│                    │                    │                     │                   │
│          database/db.py (pool)   services/upload_service   services/signaling_*   │
└────────────────────┼────────────────────┼─────────────────────┼───────────────────┘
                     ▼                    ▼                     ▼
            Firebird 4 (BANCO.FDB)   Cloudflare R2 (fotos)   salas em memória
                                     Arkhé (PIX)  Gmail SMTP (códigos)
```

## Camadas

| Pasta / arquivo | Papel |
|---|---|
| `app.py` | Cria o app, registra blueprints, `sock` (flask-sock), CORS (origens fixas) e os `errorhandler` (`ErroNegocio` → `{'error'}`; exceção inesperada → log + 500). |
| `config.py` | `SECRET_KEY` do `.env`. |
| `view/` | Rotas HTTP/WS, uma blueprint por domínio. Só leem o `request`, chamam o service e montam a resposta. |
| `funcao.py` | Validadores e normalizadores puros (senha, CPF, e-mail, telefone, nome, imagem, conselho, valor, abordagem, modalidade). |
| `util/usuarios.py` | Decorators `usuario_autenticado` / `profissional_autenticado`. |
| `services/` | Um `<dominio>_service.py` por blueprint (`auth`, `usuarios`, `registros`, `prontuario`, `profissionais`, `consultas`, `encaminhamentos`, `pagamentos`) com regras e SQL; `email_service` (SMTP + Jinja); `erros.py` (`ErroNegocio`); `upload_service` (R2 via boto3 + Pillow) e `signaling_service` (salas WebRTC). |
| `database/` | `db.py` (pool e `transacao()`), `schema.sql`, `BANCO.FDB` (banco versionado no repo). |
| `templates/` | `email_codigo.html` (Jinja) para códigos de ativação/recuperação. |
| `tests/` | Scripts com asserts (`test_rotas.py` fixa status e chaves de todas as rotas, `test_profissionais.py`, `test_pool.py`); precisam do Firebird no ar e desfazem o que criam. |

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
| `/api/usuarios` | `GET/PUT/PATCH /me`, `GET /`, `POST /` (cadastro paciente), `POST /logout` | logado / público |
| `/api/profissionais` | `GET /` (filtros `nome`, `especialidade`, `tipo_conselho`, `preco_min/max`, `disponibilidade_inicio/fim`, `abordagem`, `modalidade`, `avaliacao_min`), `GET /<id>`, `POST /` (cadastro), `PATCH /me` (descrição, preço, abordagem, modalidade). Cada profissional vem com `especialidade`, `abordagem`, `modalidade`, `avaliacao` (média com 1 casa ou `null`) e `total_avaliacoes` | público / profissional |
| `/api/registros` | `GET/POST /` (diário, paginação `limite`/`antes`), `GET /evolucao?dias=7\|30\|90` (`resumo` + `evolucaoHumor`, mesmo cálculo e formato do prontuário) | só paciente, próprios registros |
| `/api/consultas` | `GET /` (inclui `nota_avaliacao`), `POST /` (agendar), `PATCH /<sessao_id>` (horário, link, status), `POST /<sessao_id>/avaliacao` (nota 1–5 e comentário; só paciente, sessão `REALIZADO`, uma vez) | logado |
| `/api/prontuario` | `GET /<paciente_id>?dias=7\|30\|90` | profissional com sessão não cancelada com o paciente |
| `/api/encaminhamentos` | `GET /`, `POST /` | profissional |
| `/api/pagamentos` | `POST /cobranca`, `GET /cobranca/<id>`, `GET /financeiro` | paciente (cobrança) / logado |
| `/ws/signaling?sessao_id=` | WebSocket WebRTC: repassa `offer`/`answer`/`ice-candidate` e emite `peers`, `peer-joined`, `peer-left` | participantes da sessão |

## Modelo de dados (`database/schema.sql`)

- `USUARIO`: base de todos (role, CPF, senha bcrypt, `codigo` de 6 dígitos para ativação/recuperação, `ativo`).
- `PROFISSIONAL`: 1:1 com usuário (`USUARIO_ID`), conselho CRP/CRM, preço, dias de atendimento, `ABORDAGEM` (lista `ABORDAGENS` em `funcao.py`) e `MODALIDADE` (`dm_modalidade`: `ONLINE/PRESENCIAL/AMBAS`), as duas opcionais. O filtro de modalidade inclui sempre `AMBAS`.
- `REGISTRO`: diário do paciente (humor, sono, alimentação, exercício, anotação BLOB).
- `ENCAMINHAMENTO`: paciente → profissional, status `ATIVO/CONCLUIDO/CANCELADO`.
- `SESSAO`: consulta paciente × profissional; `STATUS` `AGENDADO/CONFIRMADO/REALIZADO/CANCELADO`, `VALOR_CENTAVOS` inteiro, FK opcional para encaminhamento e conversa.
- `AVALIACAO`: nota 1–5 e comentário do paciente por sessão (`UQ_AVALIACAO_SESSAO`); a busca junta a média por profissional numa tabela derivada (`ORIGEM_PROFISSIONAL` em `services/profissionais_service.py`).
- `CONVERSA`, `CONVERSA_PARTICIPANTE`, `CONVERSA_MENSAGEM`: existem no schema, sem rotas ainda.

Valores enumerados são `DOMAIN`s com `CHECK`; a validação das rotas espelha esses domínios (ex.: `DOMINIOS` em `services/registros_service.py`).

## Fluxos principais

**Autenticação.** `POST /api/auth/login` confere bcrypt e `ativo`, gera JWT HS256 com `{id_usuario, usuario_role}` e grava no cookie `access_token` (`httponly`, `secure`, `SameSite=None`). Os decorators decodificam o cookie e passam o payload como primeiro argumento da rota. Cadastro e "esqueci a senha" gravam `USUARIO.codigo` e mandam e-mail em thread (`enviar_email_codigo_async`).

**Pool de conexões (`database/db.py`).** `LifoQueue` de até 10 conexões `fdb`. `get_connection()` reaproveita uma livre (testa com `SELECT 1 FROM RDB$DATABASE`, descarta se morta) ou abre nova. `ConexaoDoPool.close()` faz **rollback** e devolve ao pool, então toda rota precisa de `commit()` explícito e de `close()` no `finally`.

**Agendamento.** `POST /api/consultas` usa `reservar_participantes`: `SELECT ... WITH LOCK` nos dois usuários em ordem fixa de ID, serializando agendamentos concorrentes sem deadlock, e então checa conflito de horário com sessões não canceladas. `PATCH` muda status (`REALIZADO` só após o fim; `CANCELADO`) separado de horário/link.

**Videochamada.** O WebSocket valida cookie, `sessao_id`, se o usuário é participante, status ≠ `CANCELADO` e janela (abre 15 min antes do início até o fim). Fecha a conexão do banco **antes** de entrar no loop e repassa `offer/answer/ice-candidate` aos outros sockets da sala `sessao:<id>`. Presença: quem entra recebe `{"type": "peers", "participantes": [{id_usuario, nome}]}`; os outros recebem `peer-joined` e, na saída, `peer-left` (mesmos campos, nunca o e-mail). Se o outro participante não está na sala, `consultas_service.avisar_entrada_na_sala` manda um e-mail com o link `FRONT_URL/videochamada/<id>`, uma vez por sessão e por quem entrou (dedupe em memória). Salas vivem num `dict` em memória protegido por um lock, por isso há **um único processo**; cada chamada ocupa uma thread.

No front, a página em uso é `TesteVideo.jsx`, que ignora os eventos de presença até alguém tratá-los. `src/utils/videoCall.js` espera outro protocolo (`join`/`joined`/`ready` com `call_id`) que o backend nunca implementou e não é importado por nenhuma página.

**Pagamento.** `POST /api/pagamentos/cobranca` lê `VALOR_CENTAVOS` da sessão do paciente e cria cobrança PIX na Arkhé (`ARKHE_BASE_URL`, credenciais `CLIENT_ID`/`CLIENT_SECRET`, via `urllib`), convertendo para reais. `GET /financeiro` agrega saldo, resumo e movimentações da conta Arkhé.

**Fotos de perfil.** Upload pelo Pillow (corrige EXIF, converte para JPEG, máx. 512×512) para o bucket R2 `psicodaily` em `usuarios/<id>.jpg`, `Cache-Control: no-cache`. A URL é derivada do ID (`url_foto_usuario`), sem coluna no banco.

## Execução e deploy

- **Docker**: `python:3.14-slim` + Firebird 4 no mesmo container; `docker-entrypoint.sh` sobe o Firebird, define a senha SYSDBA e inicia gunicorn em `:8000`. `TZ=America/Sao_Paulo` (as rotas comparam com `datetime.now()` local).
- **Dev (WSL)**: `run.sh` sobe um gunicorn ouvindo em `127.0.0.1:8000` e `:8001`.
- **Por que gthread e não gevent**: `fdb` chama `libfbclient` via ctypes, o que bloquearia o loop do gevent.

## Pontos de atenção

- Checkup de segurança de 19/10/2026 em `plans/ultima-sprint.md` (seção 2, achados S1–S23). Os mais graves:
  - Repo **público** com a senha SMTP do Gmail hard-coded em `services/email_service.py` (`enviar_email`) e com o `BANCO.FDB`, que tem dados reais.
  - Código de ativação/recuperação sem expiração nem limite de tentativas: força bruta toma qualquer conta pelo e-mail.
  - O JWT não tem `exp`: o token vale até a troca do `SECRET_KEY`.
  - `GET /api/encaminhamentos` lista os encaminhamentos de todos os profissionais.
  - WebSocket sem checagem de `Origin` (cookie `SameSite=None`).
- `dm_role` não inclui `ADMIN`, embora `usuarios.py` e `consultas.py` testem esse papel.
- `dias_atendimento` é validado no cadastro de profissional, mas não é gravado: não existe modelo de agenda.
- O estado das salas em memória impede escalar horizontalmente sem um broker (ex.: Redis pub/sub).
- `BANCO.FDB` está versionado. Alterações de schema precisam ser aplicadas no arquivo e refletidas em `schema.sql`.
