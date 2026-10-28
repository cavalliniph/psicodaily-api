# Segurança adiada (fase 2 da última sprint)

> **Decisão (20/10/2026):** a fase 2 sai da sprint para o time focar em entregar as features. Volta quando o resto de `plans/ultima-sprint.md` estiver completo.
> Já feitos antes da decisão: S3, S4, S5, S6, S7, S8 e S13. S22 fechou com a F6 (20/10/2026); S9 fecha com a feature 32, se ela vier antes.
> Até lá continuam abertos, entre outros: senha SMTP no repo público (S1, revogar a senha do Gmail não depende de código), sem rate limit (S11), sem limite de corpo/imagem (S10), financeiro da conta inteira visível a todo profissional (S9).

## Checkup de segurança

Leitura completa de `app.py`, `funcao.py`, `util/`, `database/db.py`, `services/`, `view/*`, Dockerfile e entrypoint em 19/10/2026.
**Sem SQL injection**: toda query usa `?`, e as colunas dinâmicas (`UPDATE ... SET {definicoes}`) vêm de listas fixas no código.

### Achados

| # | Sev. | Onde | Problema | Correção |
|---|---|---|---|---|
| S1 | Crítica | `services/email_service.py::enviar_email` | Senha SMTP do Gmail no código, em repo público | Item 0.1 + `SMTP_USER`/`SMTP_PASSWORD` no `.env`. **Feito** (28/10/2026): só no `.env` e no Northflank. Decisão do time: a senha não será revogada, então a que está no histórico público continua válida |
| S2 | Crítica | `database/BANCO.FDB`, `usuarios/*.jpg` | Dados pessoais e de saúde reais no repo público | Item 0.2 |
| S3 | ~~Alta~~ | `auth.py` `alterar_senha`, `verificar_codigo` | Código de 6 dígitos **sem expiração nem limite de tentativas**: dá para disparar `esqueci_senha` e testar 10⁶ códigos em `alterar_senha`, tomando qualquer conta pelo e-mail | **Feito** (20/10/2026): migration `0015_seguranca_auth`; recuperação expira em 15 min, ativação sem validade (não há reenvio), 5ª falha apaga o código, `compare_digest` |
| S4 | ~~Alta~~ | `services/auth_service.py::gerar_token` | JWT **sem `exp`**: token roubado vale para sempre; logout, troca de senha e desativação não o invalidam | **Feito** (20/10/2026): `exp` 8h + `iat`, `auth_service.usuario_do_token` nos decorators e nos WS (recusa token sem `exp`, usuário inativo e `iat` < `SENHA_ALTERADA_EM`); troca logada devolve cookie novo. No deploy, todo mundo precisa logar de novo |
| S5 | ~~Alta~~ | `encaminhamentos_service.listar` | `GET /api/encaminhamentos/` devolve **todos** os encaminhamentos (CID e motivo) de todos os profissionais | **Feito** (20/10/2026): só os do próprio profissional |
| S6 | ~~Média~~ | `encaminhamentos.py` POST | Qualquer profissional cria encaminhamento para qualquer `id_usuario`; não valida se é paciente, nem tipo e tamanho de `motivo`/`id_cid`; aceita campos extras | **Feito** (20/10/2026): vínculo + papel `PACIENTE` (404 único), campos permitidos, `motivo` até 2000, `id_cid` no formato CID-10 |
| S7 | ~~Média~~ | `signaling.py` | **Cross-site WebSocket hijacking**: o cookie é `SameSite=None` e o handshake WS não passa por CORS. Um site malicioso aberto pelo participante na janela da sessão entra na sala e lê SDP/ICE (IP real) | **Feito** (20/10/2026): `config.ORIGENS_FRONT` + `origem_permitida()` no signaling e no chat |
| S8 | ~~Média~~ | `pagamentos_service.consultar_cobranca` | `GET /cobranca/<id>`: qualquer usuário logado consulta qualquer cobrança da Arkhé (IDOR) | **Feito** com a F2 (20/10/2026) |
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
| S22 | ~~Info~~ | `upload_service.py` | Bucket R2 público (`r2.dev`): serve para foto de perfil, **não** para documentos do chat nem transcrições | **Feito** com a F6 (20/10/2026): anexos do chat no bucket privado; o público fica só com fotos de perfil |
| S23 | Info | `prontuario.py` | O profissional vê a `anotacao` de todos os registros do paciente, e o vínculo nunca expira | Aceito: a sprint não pede diário privado (ver feature 26). Rever só se o produto pedir |

CSRF nas rotas JSON: baixo risco. `get_json` exige `Content-Type: application/json`, o que força preflight, e o preflight é barrado pelo CORS. Manter todas as rotas autenticadas só com JSON ou multipart via `PATCH`, nunca `POST` de formulário com cookie.

### Ordem de correção

S1 → S3 → S4 → S5 → S13 → S7 → S10 → S6 → S15 → S11 → S12 → S14 → resto. S8 e S9 entram junto com F2 e a feature 32.
Cada correção leva um assert em `tests/test_seguranca.py` (ex.: 6ª tentativa de código retorna 401 mesmo com o código certo; WS com `Origin` estranho é fechado; listagem de encaminhamentos não traz o de outro profissional).
