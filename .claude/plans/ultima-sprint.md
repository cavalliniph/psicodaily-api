# Última sprint: refatoração, segurança e features pendentes

> Escopo: **somente este repositório (psicodaily-api)**. Fonte: `ultima-sprint-pendentes.md` (33 tarefas, 06/10/2026).
> Itens que são só front ou mobile aparecem aqui apenas com o que a API precisa expor.

Ordem de execução:

0. Urgente, fora do código (hoje)
1. Refatoração `view/` → `services/` (não muda comportamento)
2. Correções de segurança
3. Fundações compartilhadas pelas features
4. Features, em ondas por dependência

Cada fase termina com os testes verdes. Cada domínio refatorado ou cada feature vira um commit (`refactor: ...`, `fix: ...`, `feat: ...`).

---

## 0. Urgente (antes de qualquer código)

O repositório `cavalliniph/psicodaily-api` é **público** no GitHub.

1. **Revogar a senha de app do Gmail** `psicodaily.contato@gmail.com` (estava em `funcao.py:59`, hoje em `services/email_service.py`, desde o commit `5750063`). Gerar uma nova e colocá-la só no `.env` (item S1). Apagar do código não basta: ela já está no histórico público.
2. **`database/BANCO.FDB` versionado e público**: contém CPF, e-mail, telefone, hash de senha e diário de humor (dado de saúde, LGPD art. 11). Decidir com o time:
   - tornar o repo privado (mais rápido), **ou**
   - trocar o `.FDB` por um banco só com dados fictícios e reescrever o histórico (`git filter-repo --path database/BANCO.FDB --invert-paths`, com force push combinado com o time).
   O `.gitignore` já tem `database/*.FDB`, mas o arquivo foi adicionado antes e continua rastreado.
3. Mesma decisão para `usuarios/8.jpg` e `usuarios/9.jpg` (fotos de usuário rastreadas).

---

## 1. Refatoração: regras de negócio em `services/` (concluída em 19/10/2026)

Decisão registrada em `architecture.md` (seção "Camadas") e resumida no `CLAUDE.md`.

### Regra de camadas

| Camada | Pode | Não pode |
|---|---|---|
| `view/<dominio>.py` | Ler `request` (JSON, args, files), aplicar decorator de auth, chamar o service, montar `jsonify` e headers (`Cache-Control`) | SQL, regra de negócio, abrir conexão |
| `services/<dominio>_service.py` | Validar regras, SQL, transação, chamar APIs externas (Arkhé, R2, SMTP) | Importar `flask` (`request`, `jsonify`, `current_app`) |
| `funcao.py` | Validadores e normalizadores **puros** (CPF, e-mail, senha, conselho, valor) | I/O (banco, e-mail, upload) |

Erros de negócio saem do service como `ErroNegocio(mensagem, status)`; um único `errorhandler` em `app.py` devolve `jsonify({'error': msg}), status`. Exceções inesperadas caem num handler genérico que loga com `app.logger.exception` e devolve 500. Isso apaga os ~25 blocos `try/except/finally` repetidos nas rotas.

### Peças novas (as únicas)

```python
# services/erros.py
class ErroNegocio(Exception):
    def __init__(self, mensagem, status=400):
        super().__init__(mensagem)
        self.mensagem, self.status = mensagem, status
```

```python
# database/db.py
@contextmanager
def transacao():
    con = get_connection()
    cur = con.cursor()
    try:
        yield cur
        con.commit()
    finally:
        cur.close()
        con.close()  # rollback do que nao commitou + devolve ao pool
```

```python
# app.py
@app.errorhandler(ErroNegocio)
def erro_negocio(erro):
    return jsonify({'error': erro.mensagem}), erro.status
```

Sem classes de service, sem repositórios, sem DTOs: cada service é um módulo de funções que recebem valores simples (`id_usuario`, `dict` já parseado) e devolvem `dict`/`list` prontos para o `jsonify`. `upload_service` e `signaling_service` continuam como estão.

### Mapa de movimentação

| Origem | Destino | Observação |
|---|---|---|
| `view/registros.py`: `DOMINIOS`, `COLUNAS`, `serializar`, `validar`, SQL | `services/registros_service.py` | `prontuario` deixa de importar de `view/` |
| `view/prontuario.py`: vínculo, resumo, evolução de humor | `services/prontuario_service.py` | `evolucao_humor()` fica reutilizável pela feature 28 |
| `view/encaminhamentos.py` | `services/encaminhamentos_service.py` | |
| `view/auth.py`: login (duplicado em `login_mobile`), código, senha | `services/auth_service.py` | `login` e `login_mobile` passam a chamar a mesma `autenticar()` |
| `funcao.py`: `gerar_token`, `decodificar_token`, hash de senha | `services/auth_service.py` | `SECRET_KEY` lido de `config`, não de `current_app` |
| `funcao.py`: `enviar_email*` | `services/email_service.py` | |
| `funcao.py`: `criar_usuario_base`, `salvar_imagem_usuario` | `services/usuarios_service.py` | Recebe `dict` + arquivo, não lê `request` |
| `view/usuarios.py`: `/me` GET/PATCH, listagem | `services/usuarios_service.py` | |
| `view/profissionais.py`: filtros, SQL, cadastro, PATCH | `services/profissionais_service.py` | A view só converte `request.args` em `dict` |
| `view/consultas.py`: `ler_intervalo`, `reservar_participantes`, agendar, atualizar, avaliar | `services/consultas_service.py` | |
| `view/pagamentos.py`: `_arkhe_request`, `_conta`, `_numero`, `_movimentacao` | `services/pagamentos_service.py` | |
| `view/signaling.py`: checagem de participante/janela | `services/consultas_service.py` (`pode_entrar_na_sala`) | |
| Decode manual do cookie em `consultas.py` e `pagamentos.py` | `@usuario_autenticado` | `profissional_autenticado` passa a reaproveitar `usuario_autenticado` |
| `resposta_erro` em `funcao.py` | apagar | Substituído por `ErroNegocio` |
| `util/datas.py::parsear_data` | apagar se continuar sem uso | Hoje nenhum arquivo importa |

### Rede de segurança

1. **Antes de mover qualquer coisa**: `tests/test_rotas.py`, um teste de caracterização com `test_client` que chama cada rota no caminho feliz e em 1 ou 2 erros, e confere status + chaves do JSON. Deve passar no código atual.
2. Refatorar um domínio por commit, nesta ordem (do menor acoplamento para o maior): registros → prontuário → encaminhamentos → usuários/auth (+ `funcao.py`) → profissionais → consultas → pagamentos → signaling.
3. Depois de cada domínio: `test_rotas.py`, `test_profissionais.py` e `test_pool.py` verdes.
4. Mudança de comportamento aceita: o texto das mensagens de 500 fica unificado. Conferir no `psicodaily-front` se alguma tela compara a string da mensagem.
5. Atualizar `architecture.md` (tabela de camadas e "Pontos de atenção") no último commit da fase.

Pronto quando: nenhum `view/*.py` importa `get_connection` e nenhum `services/*.py` importa `flask`.

```bash
grep -l get_connection view/*.py     # vazio
grep -l "from flask import" services/*.py   # vazio (flask_bcrypt pode)
```

---

## 2. Checkup de segurança

Leitura completa de `app.py`, `funcao.py`, `util/`, `database/db.py`, `services/`, `view/*`, Dockerfile e entrypoint em 19/10/2026.
**Sem SQL injection**: toda query usa `?`, e as colunas dinâmicas (`UPDATE ... SET {definicoes}`) vêm de listas fixas no código.

### Achados

| # | Sev. | Onde | Problema | Correção |
|---|---|---|---|---|
| S1 | Crítica | `services/email_service.py::enviar_email` | Senha SMTP do Gmail no código, em repo público | Item 0.1 + `SMTP_USER`/`SMTP_PASSWORD` no `.env` |
| S2 | Crítica | `database/BANCO.FDB`, `usuarios/*.jpg` | Dados pessoais e de saúde reais no repo público | Item 0.2 |
| S3 | Alta | `auth.py` `alterar_senha`, `verificar_codigo` | Código de 6 dígitos **sem expiração nem limite de tentativas**: dá para disparar `esqueci_senha` e testar 10⁶ códigos em `alterar_senha`, tomando qualquer conta pelo e-mail | Colunas `CODIGO_EXPIRA_EM` (15 min) e `CODIGO_TENTATIVAS`; invalida o código na 5ª falha; `secrets.compare_digest` |
| S4 | Alta | `services/auth_service.py::gerar_token` | JWT **sem `exp`**: token roubado vale para sempre; logout, troca de senha e desativação não o invalidam | `exp` de 8h (cookie com `max_age` igual) + `iat`; o decorator recusa token com `iat` anterior a `USUARIO.SENHA_ALTERADA_EM`. Refresh token fica para a feature 10 |
| S5 | Alta | `encaminhamentos_service.listar` | `GET /api/encaminhamentos/` devolve **todos** os encaminhamentos (CID e motivo) de todos os profissionais | Filtrar `WHERE PSICOLOGO_ID = ?` (ou paciente do vínculo) |
| S6 | Média | `encaminhamentos.py` POST | Qualquer profissional cria encaminhamento para qualquer `id_usuario`; não valida se é paciente, nem tipo e tamanho de `motivo`/`id_cid`; aceita campos extras | Exigir vínculo (sessão não cancelada), `USUARIO_ROLE = 'PACIENTE'`, validar campos conforme convenção do `CLAUDE.md` |
| S7 | Média | `signaling.py` | **Cross-site WebSocket hijacking**: o cookie é `SameSite=None` e o handshake WS não passa por CORS. Um site malicioso aberto pelo participante na janela da sessão entra na sala e lê SDP/ICE (IP real) | Recusar handshake cujo `Origin` não está na lista do CORS (mover a lista para uma constante compartilhada) |
| S8 | Média | `pagamentos_service.consultar_cobranca` | `GET /cobranca/<id>`: qualquer usuário logado consulta qualquer cobrança da Arkhé (IDOR) | Persistir cobrança na tabela `PAGAMENTO` (fundação F2) e checar o dono |
| S9 | Média | `pagamentos_service.financeiro` | `GET /financeiro`: todo profissional vê saldo e extrato da conta PJ inteira da plataforma | Resolvido pela feature 32 (financeiro por profissional); até lá, restringir a `ADMIN` |
| S10 | Média | `app.py` | Sem `MAX_CONTENT_LENGTH`: upload e corpo de qualquer tamanho; `Image.open` sem limite de pixels (decompression bomb) | `MAX_CONTENT_LENGTH = 5 MB`; `Image.MAX_IMAGE_PIXELS = 25_000_000`; `Image.open(..., formats=['JPEG'])` |
| S11 | Média | todas as rotas públicas | Sem rate limit: força bruta de login, envio em massa de e-mail (`esqueci_senha`, cadastro) e esgotamento da cota do Gmail | Contador em memória por IP+rota (cabe no processo único), ex. 10/min em `auth/*`. `ponytail:` some ao escalar para N processos |
| S12 | Média | `consultas.py` agendar | Paciente agenda sem limite de duração nem quantidade: uma sessão de 1 ano ou 500 sessões bloqueiam a agenda do profissional | Duração entre 30 e 120 min, no máximo N sessões `AGENDADO` não pagas por paciente; fica completo com a fundação F1 |
| S13 | ~~Média~~ | `auth.py` (antigo) | `print` do e-mail e dos códigos no log | **Feito** na fase 1 (prints removidos) |
| S14 | Média | `docker-entrypoint.sh`, `.env` | App conecta como `SYSDBA` com senha `sysdba` | Usuário Firebird só com permissão nas tabelas da app; senha via env |
| S15 | Baixa | `auth.py` login, `esqueci_senha` | Enumeração de usuário: 404 "não encontrado" vs 401 "senha incorreta" | Resposta única `401 Email ou senha invalidos`; `esqueci_senha` sempre 200 |
| S16 | Baixa | `usuarios.py` PATCH `/me` | Troca de e-mail sem senha atual e sem reverificar: quem pegar um token troca o e-mail da conta e assume o "esqueci a senha" | Exigir `senha_atual` para trocar e-mail e mandar código ao novo e-mail |
| S17 | Baixa | `app.py` CORS | `http://10.92.11.34:5173` e `localhost` liberados com credenciais em produção | Origens via env (`CORS_ORIGINS`), dev só no `.env` local |
| S18 | Baixa | `config.py` | Sem `SECRET_KEY`, ou com o valor do `.env.example`, o app sobe e assina tokens com chave previsível | Falhar no import se a chave tiver menos de 32 caracteres |
| S19 | Baixa | `funcao.py::validar_senha` | Senha limitada a **12** caracteres | Máximo de 64 (bcrypt aceita até 72 bytes) |
| S20 | Baixa | `pagamentos.py` | `detalhes` repassa ao cliente a resposta crua da Arkhé | Logar o detalhe e devolver só a mensagem |
| S21 | Baixa | `auth.py` login | `email`/`senha` não-string ou `SENHA` nula no banco geram 500 | Checar `isinstance(..., str)` |
| S22 | Info | `upload_service.py` | Bucket R2 público (`r2.dev`): serve para foto de perfil, **não** para documentos do chat nem transcrições | Bucket privado + URL assinada (fundação F6) |
| S23 | Info | `prontuario.py` | O profissional vê a `anotacao` de todos os registros do paciente, e o vínculo nunca expira | Decisão de produto na feature 26 (diário privado) |

CSRF nas rotas JSON: baixo risco. `get_json` exige `Content-Type: application/json`, o que força preflight, e o preflight é barrado pelo CORS. Manter todas as rotas autenticadas só com JSON ou multipart via `PATCH`, nunca `POST` de formulário com cookie.

### Ordem de correção

S1 → S3 → S4 → S5 → S13 → S7 → S10 → S6 → S15 → S11 → S12 → S14 → resto. S8 e S9 entram junto com F2 e a feature 32.
Cada correção leva um assert em `tests/test_seguranca.py` (ex.: 6ª tentativa de código retorna 401 mesmo com o código certo; WS com `Origin` estranho é fechado; listagem de encaminhamentos não traz o de outro profissional).

---

## 3. Fundações

Várias tarefas da sprint dependem das mesmas peças. Construir cada uma só quando a primeira feature que a usa entrar.

| ID | Fundação | O que é | Desbloqueia |
|---|---|---|---|
| F1 | **Disponibilidade** | Tabela `DISPONIBILIDADE (PROFISSIONAL_ID, DIA_SEMANA, HORA_INICIO, HORA_FIM)` + `horarios_livres(profissional_id, de, ate)` em `consultas_service`. Hoje não existe agenda: `dias_atendimento` do cadastro é validado e **descartado** (não há coluna), e qualquer horário sem conflito é aceito | 6, 7, 21, 29, 31, S12 |
| F2 | **Pagamento persistido** | Tabela `PAGAMENTO (SESSAO_ID, ID_COBRANCA_ARKHE, METODO, VALOR_CENTAVOS, STATUS, PAGO_EM, TAXA_CENTAVOS)`. Status atualizado por webhook da Arkhé (se ela tiver) ou por consulta ao abrir a tela | 13, 17, 24, 25, 27, 32, S8 |
| F3 | **Notificações** | Tabela `NOTIFICACAO (USUARIO_ID, TIPO, DADOS, LIDA, CRIADO_EM)` + `notificacoes_service.notificar(usuario_id, tipo, dados)`, que grava e despacha nos canais ativos (e-mail hoje, WhatsApp/push depois). `GET /api/notificacoes` | 4, 6, 13, 14, 27, 30 |
| F4 | **Auth para mobile** | Decorators aceitam `Authorization: Bearer` além do cookie (hoje `login_mobile` devolve o token, mas nenhuma rota lê o header). Inclui o WS do signaling | 1, 4, 23, 27 |
| F5 | **Auditoria** | Tabela `AUDITORIA (USUARIO_ID, ACAO, ENTIDADE, ENTIDADE_ID, IP, CRIADO_EM)` + `auditar(cur, ...)` chamado dentro dos services, na mesma transação | 20, 10, 11, 18 |
| F6 | **Arquivos privados** | Segundo bucket R2, privado, com URL assinada de curta duração (`generate_presigned_url` do boto3, já instalado) | 3 (vídeo), 11, 19 |
| F7 | **Jobs periódicos** | Thread daemon iniciada no `app.py` que roda a cada minuto (lembretes, lista de espera, reconciliação de pagamento). Cabe no processo único. `ponytail:` vira cron externo (Northflank job) se o processo for replicado | 6, 30 |
| F8 | **Papel ADMIN** | `dm_role` não tem `ADMIN`, mas `usuarios.py` e `consultas.py` já checam esse papel. `ALTER DOMAIN` + decorator `admin_autenticado` | 25, S9 |

Schema: sem migrações. Toda mudança vai no `schema.sql` **e** é aplicada no `BANCO.FDB`, como no plano `filtros-busca-profissionais.md`.
Corrigir junto, no schema: as FKs de `CONVERSA_*` e `ENCAMINHAMENTO` apontam para `USUARIO(USUARIO_ID)`, mas a coluna é `ID_USUARIO`; as PKs de `CONVERSA*` não são `IDENTITY`; o default de `SESSAO.STATUS` é `'AGENDADA'`, que o domínio rejeita.

---

## 4. Features

Esforço: **P** até 1 dia · **M** 2 a 4 dias · **G** uma semana ou mais. **?** marca decisão de produto que precisa vir antes do código.

### Onda A: dados que já existem (sem fundação)

| # | Tarefa | Backend | Esf. |
|---|---|---|---|
| 28 | Acompanhamento de humor com gráficos | `GET /api/registros/evolucao?dias=7\|30\|90` reutilizando `prontuario_service.evolucao_humor()` | P |
| 26 | Diário pessoal privado | **?** Diário separado ou flag no registro. Sugestão: coluna `REGISTRO.COMPARTILHADO BOOLEAN DEFAULT TRUE`; o prontuário omite a `anotacao` quando for `FALSE` | P |
| 29 | Busca por especialidade, abordagem, preço, disponibilidade, modalidade, avaliação | **Feito** (`filtros-busca-profissionais.md`). Falta só a disponibilidade usar F1 em vez de "sem conflito" | P (com F1) |
| 15 | Filtros avançados | Somar aos de 29: `idioma`, `experiencia_min`, `ordenar=preco\|avaliacao\|experiencia`. Depende dos campos de 3 | P |
| 3 | Perfil completo (formação, especialidades, abordagem, experiência, idiomas, vídeo) | `PROFISSIONAL`: `FORMACAO BLOB`, `ANOS_EXPERIENCIA SMALLINT`, `IDIOMAS VARCHAR(200)` (lista fixa em `funcao.py`, como `ABORDAGENS`), `VIDEO_URL`. Vídeo: **?** link do YouTube/Vimeo (P) ou upload para R2 (M, F6). Aceitar no cadastro e no `PATCH /me`, devolver na busca | M |
| 7 | Favoritar psicólogos e acompanhar disponibilidade | `FAVORITO (PACIENTE_ID, PROFISSIONAL_ID, PK composta)`; `POST/DELETE /api/favoritos/<id>`, `GET /api/favoritos` com o próximo horário livre (F1) | P + F1 |
| 8 | Conteúdos e artigos no perfil | `CONTEUDO (PROFISSIONAL_ID, TITULO, CORPO BLOB, PUBLICADO_EM)`; CRUD em `/api/conteudos` para o dono, `GET /api/profissionais/<id>/conteudos` público. Texto puro ou Markdown, **sem HTML** (XSS no front) | M |
| 14 | Avisar quando o outro entrar na sala | No `signaling_service.join`, mandar `{"type": "peer-joined"}` para quem já está na sala; se o outro não estiver conectado, `notificar()` (F3) | P (+F3 para quem está fora) |
| 20 | Log de auditoria | F5. Ações mínimas: login, falha de login, acesso a prontuário, alteração de sessão, encaminhamento, troca de senha/e-mail. `GET /api/admin/auditoria` (F8) | M |
| 25 | Painel administrativo | F8 + `GET /api/admin/metricas?dias=`: faturamento (F2, ou `SUM(VALOR_CENTAVOS)` de `REALIZADO` antes de F2), consultas por status, usuários ativos por papel, novos cadastros, avaliação média | M |

### Onda B: agenda e dinheiro (F1, F2, F3)

| # | Tarefa | Backend | Esf. |
|---|---|---|---|
| — | Agenda do profissional | F1: `GET/PUT /api/profissionais/me/disponibilidade`, `GET /api/profissionais/<id>/horarios?de=&ate=`. Agendar passa a exigir horário dentro da disponibilidade. Persistir os `dias_atendimento` do cadastro aqui | M |
| 6 | Lista de espera | `LISTA_ESPERA (PACIENTE_ID, PROFISSIONAL_ID, INICIO_DESEJADO, FIM_DESEJADO, AVISADO_EM)`. Ao cancelar uma sessão (ou abrir disponibilidade), notifica (F3) o primeiro da fila compatível. Primeiro a agendar leva a vaga, sem reserva | M |
| 24 | Cancelamento e reembolso | **?** Regras (ex.: ≥24h reembolso total, <24h 50%, falta 0). `PATCH /api/consultas/<id>` hoje só aceita profissional; adicionar cancelamento pelo paciente. Reembolso via Arkhé: **? confirmar se a API faz estorno de PIX**, senão fica registro `REEMBOLSO_PENDENTE` para o admin | M |
| 32 | Financeiro do psicólogo (realizadas, recebido, taxas, repasses) | Sobre F2: `GET /api/pagamentos/financeiro` por profissional, a partir de `PAGAMENTO` + `TAXA_PLATAFORMA` (env). `REPASSE (PROFISSIONAL_ID, PERIODO, VALOR_CENTAVOS, STATUS)`. **?** repasse manual pelo admin ou automático. Fecha S9 | M |
| 17 | PIX, cartão e boleto | **? Verificar se a Arkhé tem cartão e boleto.** Se tiver: `METODO` em `PAGAMENTO` + rota por método. Se não: gateway extra (Asaas, Mercado Pago, Stripe) atrás da mesma interface de `pagamentos_service`. Cartão **nunca** passa pelo nosso servidor (tokenização do gateway no front) | M a G |
| 4 / 27 | Dashboards mobile do psicólogo e do paciente | Front/mobile. Backend: `GET /api/dashboard`, que monta por papel o que já existe (próximas sessões, pacientes do dia, ganhos de F2, notificações não lidas de F3, favoritos de 7). Uma rota em vez de N chamadas no mobile | P (depois de F2/F3/7) |

### Onda C: comunicação (F3, F5, F6)

| # | Tarefa | Backend | Esf. |
|---|---|---|---|
| 18 | Chat seguro paciente × profissional | Usar `CONVERSA*` (corrigir o schema, ver seção 3). Só abre conversa quem tem vínculo (sessão não cancelada). REST para histórico paginado + WS `/ws/chat` (mesmo esquema do signaling: memória, processo único, checagem de `Origin` de S7). Auditar a abertura (F5). **?** Criptografar `MENSAGEM` em repouso | G |
| 19 | Arquivos pelo chat | F6: upload para o bucket privado com tipo (PDF, JPG, PNG) e tamanho (10 MB) validados; mensagem guarda a chave, e o download gera URL assinada após checar o participante | M |
| 30 | WhatsApp: confirmações, lembretes, cancelamentos, alterações | **? Provedor**: Meta Cloud API (oficial, exige templates aprovados) ou Z-API/Twilio. `services/whatsapp_service.py` vira um canal de F3. Lembretes: job F7 (24h e 1h antes). `USUARIO.ACEITA_WHATSAPP` (opt-in, LGPD) | M |
| 13 | Link de consulta, comprovante e pagamento pelo WhatsApp | Eventos de F3 (`sessao_agendada`, `pagamento_confirmado`) já roteados para o canal WhatsApp de 30 | P (depois de 30) |
| 12 / 31 | Cancelar, reagendar e agendar pelo WhatsApp | Webhook `POST /api/whatsapp/webhook` (assinatura do provedor validada). Identifica o usuário pelo telefone **verificado** (não confiar no número sem verificação). Menu por botões, sem IA no começo: listar sessões, cancelar (regras de 24), horários livres (F1). Depois pode ligar no agente (16) | G |

### Onda D: inteligência

| # | Tarefa | Backend | Esf. |
|---|---|---|---|
| 5 | Questionário inicial | `PREFERENCIA_PACIENTE (PACIENTE_ID PK, RESPOSTAS BLOB JSON, ATUALIZADO_EM)`. Perguntas fixas no código (motivo, abordagem preferida, faixa de preço, modalidade, idioma, gênero do profissional?), validadas contra a lista. `GET/PUT /api/pacientes/me/preferencias` | P |
| 2 | Recomendação de psicólogos | Sem ML: `GET /api/profissionais/recomendados`, que reaproveita a query de busca e ordena por pontuação simples (abordagem +3, preço na faixa +2, modalidade +2, idioma +1, avaliação). Pesos numa constante | P (depois de 5 e 3) |
| 16 / 22 / 21 | Agente de IA: navegação, dúvidas (plataforma, pagamentos, consultas), disponibilidade e agendamento | **Um** endpoint `POST /api/assistente` com Claude API (SDK `anthropic`, tool use). Ferramentas = funções dos services: `buscar_profissionais`, `horarios_livres` (F1), `minhas_consultas`, `agendar_consulta` (**só com confirmação explícita do usuário**, devolvida ao front como ação, nunca executada direto pelo modelo). FAQ no system prompt. Não manda dado de saúde (registros, prontuário) ao modelo. Modelo e parâmetros: conferir com a skill `claude-api` na hora de implementar. Rate limit por usuário (custo) | G |
| 11 | Transcrição das consultas | **? Decisão ética/legal antes de tudo**: consentimento explícito das duas partes a cada sessão (CFP e LGPD), retenção, quem acessa. A chamada é P2P (o servidor não recebe o áudio). Opção: o cliente grava localmente e sobe o áudio para o bucket privado (F6); job de STT; texto em `TRANSCRICAO (SESSAO_ID, TEXTO BLOB)` visível só ao profissional, com auditoria (F5) | G |

### Fora deste repositório ou dependendo de decisão

| # | Tarefa | O que cabe à API |
|---|---|---|
| 1 | App mobile completo | F4 (Bearer), `GET /api/dashboard`, notificações push (`DISPOSITIVO (USUARIO_ID, TOKEN_PUSH)` como canal de F3) |
| 23 | Chamada de vídeo pelo app e pela web | **Web já funciona.** Para o app: F4 no WS e credenciais de TURN (`GET /api/consultas/<id>/ice-servers`, coturn ou Cloudflare TURN). Sem TURN, a chamada falha em parte das redes móveis (NAT simétrico) |
| 10 | Permissões, biometria, sessões, dados sensíveis | Biometria é do app (protege o token salvo no aparelho). API: S4 + refresh token com tabela `SESSAO_LOGIN` (listar e encerrar sessões em `/api/auth/sessoes`), F8, F5 e S22/S23 |
| 9 | Assinatura para psicólogos | **? Produto**: planos, preço, benefícios (destaque na busca? taxa menor?). Depende de cobrança recorrente no gateway (17). Não começar sem essa definição |
| 33 | "Paulinho tem que fazer mágica" | Não é tarefa de backend |

### Sequência sugerida

1. Fase 0 → Fase 1 (refatoração) → Fase 2 (S1 a S13 pelo menos)
2. Onda A: 28, 26, 14, 3, 7 (com F1), 8, F5+20, F8+25
3. F1 agenda → 6, 29 completo; F2 → 24, 32, 17; F3 → 4/27
4. 5 → 2; 30 → 13 → 12/31; 18 → 19
5. 16/21/22 e 11 por último: mais caros e com mais decisões em aberto

### Decisões para levar ao time (agrupadas)

1. Repo privado ou limpeza do histórico (0.2)
2. Diário: flag de compartilhamento ou diário separado (26)
3. Vídeo de apresentação: link externo ou upload (3)
4. Regras de cancelamento e reembolso; a Arkhé estorna PIX? (24)
5. A Arkhé tem cartão e boleto? Senão, qual gateway (17)
6. Taxa da plataforma e forma de repasse (32)
7. Provedor de WhatsApp (30)
8. Transcrição: consentimento, retenção, acesso (11)
9. Planos de assinatura (9)
