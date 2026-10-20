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
2. **`database/BANCO.FDB` versionado e público** (a F0 tira o arquivo do git e da imagem daqui em diante): contém CPF, e-mail, telefone, hash de senha e diário de humor (dado de saúde, LGPD art. 11). Decidir com o time:
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
| S22 | Info | `upload_service.py` | Bucket R2 público (`r2.dev`): serve para foto de perfil, **não** para documentos do chat nem transcrições | Bucket privado + URL assinada (fundação F6) |
| S23 | Info | `prontuario.py` | O profissional vê a `anotacao` de todos os registros do paciente, e o vínculo nunca expira | Aceito: a sprint não pede diário privado (ver feature 26). Rever só se o produto pedir |

CSRF nas rotas JSON: baixo risco. `get_json` exige `Content-Type: application/json`, o que força preflight, e o preflight é barrado pelo CORS. Manter todas as rotas autenticadas só com JSON ou multipart via `PATCH`, nunca `POST` de formulário com cookie.

### Ordem de correção

S1 → S3 → S4 → S5 → S13 → S7 → S10 → S6 → S15 → S11 → S12 → S14 → resto. S8 e S9 entram junto com F2 e a feature 32.
Cada correção leva um assert em `tests/test_seguranca.py` (ex.: 6ª tentativa de código retorna 401 mesmo com o código certo; WS com `Origin` estranho é fechado; listagem de encaminhamentos não traz o de outro profissional).

---

## 3. Fundações

Várias tarefas da sprint dependem das mesmas peças. Construir cada uma só quando a primeira feature que a usa entrar. A exceção é a F0, que vem **antes da próxima feature**.

### F0. Banco persistente, migrations e CI no Northflank

**Status (19/10/2026): implantada em produção.** Banco no volume `firebird-data` (`/var/lib/firebird/data/BANCO.FDB`), baseline aplicado, entrypoint novo no ar (`6256598`), readiness probe em `/api/saude`, `BANCO.FDB` fora do git. Conferido: as contagens de usuários, sessões e registros batem entre o banco antigo e o do volume, e os dados sobreviveram a três deploys seguidos. **Fora de escopo** (decisão de 19/10/2026: é um projeto de curso técnico, então nada de infra além do necessário para os dados não se perderem): backup fora do volume, proteção da `main` no GitHub e senha forte do banco. A senha volta, se der tempo, na fase de segurança (S14).

Histórico da implantação, mantido como referência: O Northflank faz deploy automático da `main`, e a imagem nova não leva mais o `.FDB`: sem o volume preparado, a produção sobe sem banco (o entrypoint se recusa a criar um vazio sem `CRIAR_BANCO=1`, então o deploy falha em vez de apagar dados). Já testado:
- todos os `tests/` num banco criado do zero (migrations + seed), localmente e contra a imagem oficial `firebirdsql/firebird:4`, como no CI;
- o container com volume Docker: banco novo; deploy normal com backup e dados preservados; banco de produção sem baseline (recusa subir); baseline local seguido de upload; migration nova; migration quebrada (não sobe e não deixa nada pela metade); rollback para a imagem anterior.

**Por que agora:** o `Dockerfile` copia o `database/BANCO.FDB` do repositório para a imagem, e o Firebird abre esse arquivo. No Northflank o disco do container é efêmero: a cada deploy, o banco de produção volta a ser a cópia do git, e tudo o que os usuários gravaram desde o deploy anterior some. No caminho inverso, dados pessoais do banco de desenvolvimento vão para o repo público (item 0.2). Cada feature nova com tabela ou coluna piora as duas coisas.

**Restrições do Northflank que definem o desenho**
- Firebird não existe como addon (só Postgres, MySQL, MongoDB, Redis, RabbitMQ e MinIO). O banco fica num **volume** anexado a um serviço.
- Volume *Single Read/Write*: o serviço fica com 1 instância (o signaling já exige isso) e, no deploy, o container antigo termina antes de o novo subir. São alguns segundos fora do ar por deploy, e só um processo abre o `.FDB` por vez, o que é bom para o Firebird.
- Um job não monta esse volume enquanto o serviço está de pé. Por isso a migration roda **no start do próprio container**: é o padrão *command override* da documentação do Northflank (migra e só sobe o app se der certo), e não um job separado.
- Volumes têm snapshot nativo, com agenda (hourly, daily ou weekly) e retenção, e podem ser clonados a partir de um snapshot.

**Desenho**

| Peça | Como |
|---|---|
| Volume | O `firebird-data` que já existe (ReadWriteOnce, montado em `/var/lib/firebird/data`). Em produção, `DB_DATABASE=/var/lib/firebird/data/BANCO.FDB`; fora dela, o padrão do entrypoint é `/data/BANCO.FDB`. O entrypoint faz `chown -R firebird:firebird` na pasta e guarda os backups em `<pasta>/backups` |
| Imagem | Só código: `database/*.FDB` entra no `.dockerignore` e sai do git (`git rm --cached`). Sai também o `chown` do `.FDB` no `Dockerfile` |
| Primeiro boot | Se `/data/BANCO.FDB` não existe e `CRIAR_BANCO=1`, o entrypoint cria um banco vazio em **modo embarcado, antes de subir o servidor**: o `CREATE DATABASE` remoto recusa a senha inicial da imagem. Sem a variável, o container sai com erro, para um volume esquecido não virar banco vazio em produção |
| Migrations | `database/migrations/NNNN_descricao.sql`, aplicadas em ordem por `database/migrar.py` (~50 linhas, com o `fdb` que já está instalado). Controle na tabela `SCHEMA_MIGRATION (VERSAO, NOME, APLICADA_EM)`. Cada arquivo roda numa transação só: se falhar, nada fica pela metade |
| Baseline | `0001_inicial.sql`, extraído com `isql -x` do `.FDB` da `main` em `43fb231`, que é o que a produção roda. Recriado do zero, o DDL sai idêntico (comparado com `diff`). O `schema.sql` saiu do repo: estava desatualizado (faltava a tabela `CID`, listava uma `CONVERSA_PARTICIPANTE` que não existe) e não rodava do zero. No banco de produção, o `0001` só é registrado como aplicado (`--baseline 1`) |
| Entrypoint | 1. cria o banco, se for um ambiente novo → 2. sobe o Firebird → 3. troca a senha do SYSDBA para `DB_PASSWORD` (o `security4.fdb` mora na imagem, então é a cada boot) → 4. `gbak` para `/data/backups/antes-<data-hora>.fbk` (guarda os 5 últimos) → 5. `migrar.py` → 6. `exec gunicorn`. Qualquer erro encerra o container |
| Backup | Snapshot diário do volume, com 14 dias de retenção (backup schedule do Northflank), mais o `gbak` de antes de cada deploy. O `gbak` é consistente; o snapshot pega o arquivo com o Firebird rodando |
| Health check | `GET /api/saude` (200 se `SELECT 1` responde) como readiness probe, para o Northflank só mandar tráfego depois de migrar e subir |
| Segredos | `DB_PASSWORD`, `SECRET_KEY` e as credenciais da Arkhé, do R2 e do SMTP num secret group do projeto. O entrypoint passa a usar `DB_PASSWORD` no lugar do `'sysdba'` fixo, o que adianta o S14 |
| Dev local | `python database/migrar.py` no banco local, mais `database/seed.sql` com dados **fictícios**: os usuários 22, 23 e 25 que os testes usam, com CPFs inventados. Para um banco limpo, basta apagar o `.FDB` e rodar os dois |

**Regras para alterar tabelas sem perder dados**
1. Migration aplicada nunca é editada; corrige-se com uma migration nova.
2. No mesmo deploy, só mudanças aditivas: coluna `NULL` ou com `DEFAULT`, tabela nova, índice. O código da versão anterior continua funcionando com o schema novo, então voltar o deploy é seguro.
3. Mudança destrutiva em dois deploys (expand/contract): o deploy 1 cria o novo e copia os dados; o deploy 2, depois de confirmado, remove o antigo.
4. DDL e DML em arquivos separados: no Firebird, uma coluna criada só pode ser usada por `UPDATE` depois do commit.
5. `ADD COLUNA ... DEFAULT x` **não preenche as linhas que já existem** (elas leem `NULL`); se precisar, faça um `UPDATE` noutra migration.
6. Toda coluna de texto nova leva `CHARACTER SET UTF8`, porque o padrão do banco é `ISO8859_1` (ver F0.1). Trocar o charset de uma coluna existente com `ALTER COLUMN ... TYPE` é **ignorado em silêncio** pelo Firebird.

**CI/CD**
- **GitHub Actions** (`.github/workflows/ci.yml`), em todo PR e push na `main`: serviço Firebird 4 (`firebirdsql/firebird`), `apt install libfbclient2`, `pip install -r requirements.txt`, banco vazio → `migrar.py` do zero → `seed.sql` → os scripts de `tests/`. Isso pega SQL quebrado e regressão antes do deploy.
- **Proteção da `main`** no GitHub: merge só por PR com o CI verde. O Northflank continua com build e deploy automáticos da `main` (combined service), então só código testado chega lá. Se o time preferir continuar com push direto na `main`, a alternativa é desligar o CD automático e fazer o último passo do Actions disparar o workflow do Northflank por webhook.
- **Deploy:** build da `main` → deploy → entrypoint (backup, migration, app) → readiness probe. Se a migration falhar, o container não fica saudável: corrige-se com uma migration nova ou com redeploy do build anterior, que funciona no schema atual por causa das regras 2 e 3.
- **Restauração:** `gbak -c` a partir de `/data/backups` via `northflank exec service`, ou clonar o volume a partir de um snapshot e anexá-lo ao serviço.

**Implantação (uma vez)**

Estado do Northflank conferido em 19/10/2026 (só leitura):
- Projeto `psicodaily`, serviço combined `psicodaily-api`, build só da `main` e 1 instância.
- Já existe o volume `firebird-data` (10 GB, ReadWriteOnce), montado em **`/var/lib/firebird/data`**, mas **vazio**: o serviço usa `DB_DATABASE=/app/database/BANCO.FDB`, a cópia da imagem, que é zerada a cada deploy.
- Não há backup agendado nem health check.

1. ~~Local: `0001`, `migrar.py`, `seed.sql`, `GET /api/saude`, entrypoint e CI.~~ Feito na branch `f0-migrations` (CI verde no GitHub).
2. ~~Backup agendado do volume~~: indisponível na conta (ver pendências). A senha forte ficou para o S14.
3. ~~**Janela de poucos minutos**~~ Feito às 19h05 (BRT) (o que for gravado entre 3a e 4 se perde). Tudo pelo `northflank exec service`, dentro do container atual:
   - a. `gbak -b -user SYSDBA -password <senha atual> 127.0.0.1:/app/database/BANCO.FDB /var/lib/firebird/data/inicial.fbk`, que é consistente mesmo com o banco aberto;
   - b. `gbak -c -user SYSDBA -password <senha atual> /var/lib/firebird/data/inicial.fbk 127.0.0.1:/var/lib/firebird/data/BANCO.FDB`;
   - c. baseline: `northflank upload service file --localPath database --remotePath /tmp/f0/database` e depois `cd /tmp/f0 && DB_DATABASE=/var/lib/firebird/data/BANCO.FDB python database/migrar.py --baseline 1`.
4. ~~Feito às 19h06.~~ Trocar `DB_DATABASE` para `/var/lib/firebird/data/BANCO.FDB` no serviço. Isso redeploya a **imagem atual**, que já funciona com o banco no volume, e é aqui que os dados passam a sobreviver aos deploys. Conferir login e busca; fazer um restart e conferir de novo.
5. ~~Feito às 19h08 e probe às 19h10.~~ Merge da `f0-migrations` na `main`: o entrypoint novo faz backup, migra e sobe. No log, conferir "Backup antes das migrations" e "schema em dia". Depois disso, readiness probe HTTP em `/api/saude`, porta 8000. Antes do merge ela não funciona, porque a imagem antiga não tem a rota.
6. ~~Feito.~~ `git rm --cached database/BANCO.FDB` na `main`. Daqui em diante os dados pessoais param de ir para o repo; o histórico só limpa com `git filter-repo` ou com o repo privado.
7. Proteção da `main` no GitHub: merge só por PR com o job `CI / testes` verde.
8. ~~Feito.~~ Atualizar `CLAUDE.md` e `architecture.md` com o caminho real do banco em produção.

**Pronto quando:** um deploy da `main` com uma migration nova mantém os dados de produção; o CI aplica as migrations do zero e os testes passam; existem um snapshot e um `gbak` recentes. Teste final recomendado: logo depois do passo 4, fazer um deploy vazio (redeploy) e conferir que os dados continuam lá.
Esforço: M (2 a 4 dias), quase tudo na implantação única.

### F0.1. Texto livre em UTF8 (logo depois da F0)

**Feito (19/10/2026):** migrations `0002_texto_utf8_colunas`, `0003_texto_utf8_copia` e `0004_texto_utf8_troca` para `USUARIO.NOME`, `USUARIO.EMAIL`, `PROFISSIONAL.FORMACAO` e `AVALIACAO.COMENTARIO` (mesmo nome, posição e `NOT NULL`). Testadas no banco de dev, com cópia dos dados de produção, e num banco do zero. Os testes de rotas, perfil e avaliação gravam e leem “ ”, –, emoji e “李”, e falhavam com 500 antes das migrations.

Achado ao montar o baseline: o banco tem `DEFAULT CHARACTER SET ISO8859_1`, e toda coluna `VARCHAR` sem charset explícito herda isso. Travessão (–), aspas curvas (“ ”), que o teclado do celular e o Word inserem sozinhos, emoji e letras fora do Latin-1 dão **500** (`Cannot transliterate character between character sets`). Testado em `PATCH /api/profissionais/me` com `formacao`: acento passa; travessão, aspas curvas e emoji quebram. Os BLOBs de texto (descrição, anotação, motivo) já são UTF8.

Colunas de texto livre afetadas: `PROFISSIONAL.FORMACAO`, `AVALIACAO.COMENTARIO`, `USUARIO.NOME` (o `validar_nome` aceita letras não latinas). As de vocabulário fixo (abordagem, idiomas, conselho) não precisam mudar.

Receita, já que o `ALTER ... CHARACTER SET` é ignorado; uma migration por passo:
1. `ALTER TABLE X ADD COL_NOVA VARCHAR(n) CHARACTER SET UTF8`
2. `UPDATE X SET COL_NOVA = COL`
3. `ALTER TABLE X DROP COL` e `ALTER TABLE X ALTER COLUMN COL_NOVA TO COL`

O nome continua o mesmo, então o código não muda; as rotas leem colunas pelo nome, nunca pela posição. Fazer no mesmo deploy só porque nenhum código depende da coluna antiga; restrições `NOT NULL` voltam no passo 3. Teste: gravar e ler `formacao` e `comentario` com “ ” – e emoji.

| ID | Fundação | O que é | Desbloqueia |
|---|---|---|---|
| F1 | **Disponibilidade** | **Feito** (19/10/2026): migration `0006_disponibilidade`, `services/disponibilidade_service.py`, agendamento e busca respeitam a agenda (profissional sem janela aceita qualquer horário, como antes), cadastro grava os dias das 8h às 18h. Plano original: Tabela `DISPONIBILIDADE (PROFISSIONAL_ID, DIA_SEMANA, HORA_INICIO, HORA_FIM)` + `horarios_livres(profissional_id, de, ate)` em `consultas_service`. Hoje não existe agenda: `dias_atendimento` do cadastro é validado e **descartado** (não há coluna), e qualquer horário sem conflito é aceito | 6, 7, 21, 29, 31, S12 |
| F2 | **Pagamento persistido** | **Feito** (20/10/2026): migration `0012_pagamento`; cobrança gravada na criação, consulta só pelos participantes (fecha S8), Pix pendente reaproveitado, pagamento confirma a sessão (`CONFIRMADO`) e notifica o profissional; faturamento do admin passa a vir daqui. Sem webhook nem `TAXA_CENTAVOS` (entra com a 32). Plano original: Tabela `PAGAMENTO (SESSAO_ID, ID_COBRANCA_ARKHE, METODO, VALOR_CENTAVOS, STATUS, PAGO_EM, TAXA_CENTAVOS)`. Status atualizado por webhook da Arkhé (se ela tiver) ou por consulta ao abrir a tela | 13, 17, 24, 25, 27, 32, S8 |
| F3 | **Notificações** | **Feito** (20/10/2026): migration `0010_notificacao` (com `TITULO`/`MENSAGEM` prontos para exibir), `notificar(cur, ...)` devolve o e-mail para o chamador enviar depois do commit, `GET /api/notificacoes` e `POST /api/notificacoes/lidas`. Front: sino com `nao_lidas`. Plano original: Tabela `NOTIFICACAO (USUARIO_ID, TIPO, DADOS, LIDA, CRIADO_EM)` + `notificacoes_service.notificar(usuario_id, tipo, dados)`, que grava e despacha nos canais ativos (e-mail hoje, WhatsApp/push depois). `GET /api/notificacoes` | 4, 6, 13, 14, 27, 30 |
| F4 | **Auth para mobile** | **Feito** (20/10/2026): decorators e WS do signaling aceitam `Authorization: Bearer`. Plano original: Decorators aceitam `Authorization: Bearer` além do cookie (hoje `login_mobile` devolve o token, mas nenhuma rota lê o header). Inclui o WS do signaling | 1, 4, 23, 27 |
| F5 | **Auditoria** | **Feito** (20/10/2026): migration `0008_auditoria`, `services/auditoria_service.py`, chamado no login, prontuário, sessões, encaminhamento, senha e e-mail. Plano original: Tabela `AUDITORIA (USUARIO_ID, ACAO, ENTIDADE, ENTIDADE_ID, IP, CRIADO_EM)` + `auditar(cur, ...)` chamado dentro dos services, na mesma transação | 20, 10, 11, 18 |
| F6 | **Arquivos privados** | Segundo bucket R2, privado, com URL assinada de curta duração (`generate_presigned_url` do boto3, já instalado) | 11, 19 |
| F7 | **Jobs periódicos** | Thread daemon iniciada no `app.py` que roda a cada minuto (lembretes, lista de espera, reconciliação de pagamento). Cabe no processo único. Um cron job do Northflank não montaria o volume do banco (F0), então teria que chamar uma rota interna da API em vez de abrir o `.FDB` | 6, 30 |
| F8 | **Papel ADMIN** | **Feito** (20/10/2026): migration `0009_papel_admin` (domínio com `ADMIN` + `USUARIO.CRIADO_EM`), `admin_autenticado` (também em `GET /api/usuarios/`), admin fictício 26 no seed. Promover em produção por `UPDATE`. Plano original: `dm_role` não tem `ADMIN`, mas `usuarios.py` e `consultas.py` já checam esse papel. `ALTER DOMAIN` + decorator `admin_autenticado` | 25, S9 |

Schema: cada mudança é um arquivo novo em `database/migrations/` (regras na F0).
Pendências de schema conferidas no banco real: o default de `SESSAO.STATUS` é `'AGENDADA'`, que o domínio rejeita (hoje inofensivo, porque o `INSERT` sempre informa o status). `CONVERSA` e `CONVERSA_MENSAGEM` têm PK sem `IDENTITY`, e `CONVERSA_PARTICIPANTE` não existe. Corrigir junto com a feature 18 (chat).

---

## 4. Features

Esforço: **P** até 1 dia · **M** 2 a 4 dias · **G** uma semana ou mais. **?** marca decisão de produto que precisa vir antes do código.

### Onda A: dados que já existem (sem fundação)

| # | Tarefa | Backend | Esf. |
|---|---|---|---|
| 28 | Acompanhamento de humor com gráficos | **Feito** (19/10/2026): `GET /api/registros/evolucao?dias=7\|30\|90` devolve `dias`, `resumo` e `evolucaoHumor`; o cálculo (`registros_service.evolucao`) é o mesmo do prontuário | P |
| 26 | Diário pessoal | **Já existe** (`/api/registros`, com anotação livre). "Privado" na descrição da sprint foi tratado como erro (19/10/2026). Falta só `PATCH`/`DELETE /api/registros/<id>`, se o front precisar | P |
| 29 | Busca por especialidade, abordagem, preço, disponibilidade, modalidade, avaliação | **Feito** (`filtros-busca-profissionais.md`). A disponibilidade usa a agenda da F1 desde 19/10/2026 | P (com F1) |
| 15 | Filtros avançados | **Feito** (20/10/2026): `idioma`, `area_atuacao`, `experiencia_min` e `ordenar` em `GET /api/profissionais/`. Front: controles na tela de busca. Plano original: Somar aos de 29: `idioma`, `area_atuacao`, `experiencia_min`, `ordenar=preco\|avaliacao\|experiencia`. Campos já existem (feature 3); filtrar lista com `(',' \|\| p.IDIOMAS \|\| ',') CONTAINING ',<nome>,'` | P |
| 3 | Perfil completo (formação, especialidades, abordagem, experiência, idiomas, vídeo) | **Feito no backend** (19/10/2026): `formacao`, `ano_inicio_atuacao` (+ `anos_experiencia`), `idiomas`, `areas_atuacao` ("especialidades" = áreas de atuação, lista fixa, até 8) e `video_url` (só link do YouTube/Vimeo, normalizado para embed), no cadastro, no `PATCH /me`, na busca e no detalhe. Front: mostrar os campos e trocar o `experiencia` de `DescricaoPsicologo.jsx` por `anos_experiencia` | M |
| 7 | Favoritar psicólogos e acompanhar disponibilidade | **Feito** (20/10/2026): migration `0007_favorito`, `GET/POST/DELETE /api/favoritos`, com o próximo horário livre (F1). Front: botão de favoritar no perfil e lista de favoritos. Plano original: `FAVORITO (PACIENTE_ID, PROFISSIONAL_ID, PK composta)`; `POST/DELETE /api/favoritos/<id>`, `GET /api/favoritos` com o próximo horário livre (F1) | P + F1 |
| 8 | Conteúdos e artigos no perfil | **Feito** (19/10/2026): migration `0005_conteudo`, `POST/PATCH/DELETE /api/conteudos` e `GET /api/profissionais/<id>/conteudos`. Front: renderizar `corpo` como texto ou Markdown sem HTML. Plano original: `CONTEUDO (PROFISSIONAL_ID, TITULO, CORPO BLOB, PUBLICADO_EM)`; CRUD em `/api/conteudos` para o dono, `GET /api/profissionais/<id>/conteudos` público. Texto puro ou Markdown, **sem HTML** (XSS no front) | M |
| 14 | Avisar quando o outro entrar na sala | **Feito no backend** (19/10/2026): eventos `peers`/`peer-joined`/`peer-left` no WS e e-mail com link para quem ainda não entrou. Falta o front (`TesteVideo.jsx`) mostrar a presença. Quando F3 existir, trocar o e-mail por `notificar()` | P |
| 20 | Log de auditoria | **Feito** (20/10/2026), com `GET /api/admin/auditoria` (filtros `usuario_id`, `acao`, paginação por cursor). Plano original: F5. Ações mínimas: login, falha de login, acesso a prontuário, alteração de sessão, encaminhamento, troca de senha/e-mail. `GET /api/admin/auditoria` (F8) | M |
| 25 | Painel administrativo | **Feito no backend** (20/10/2026): `GET /api/admin/metricas?dias=7\|30\|90\|365`; faturamento pelas sessões `REALIZADO` até a F2; novos cadastros só contam a partir da migration 0009. Front: tela do painel. Plano original: F8 + `GET /api/admin/metricas?dias=`: faturamento (F2, ou `SUM(VALOR_CENTAVOS)` de `REALIZADO` antes de F2), consultas por status, usuários ativos por papel, novos cadastros, avaliação média | M |

### Onda B: agenda e dinheiro (F1, F2, F3)

| # | Tarefa | Backend | Esf. |
|---|---|---|---|
| — | Agenda do profissional | **Feito** com a F1 (19/10/2026). Front: tela de agenda (`PUT /me/disponibilidade`) e agendamento a partir de `GET /<id>/horarios`. Plano original: F1: `GET/PUT /api/profissionais/me/disponibilidade`, `GET /api/profissionais/<id>/horarios?de=&ate=`. Agendar passa a exigir horário dentro da disponibilidade. Persistir os `dias_atendimento` do cadastro aqui | M |
| 6 | Lista de espera | **Feito** (20/10/2026): migration `0011_lista_espera`, `POST/GET/DELETE /api/lista-espera`; o cancelamento de sessão futura avisa (F3) o primeiro compatível. Fora: avisar ao abrir disponibilidade nova ou ao reagendar. Front: botão "entrar na lista de espera" no perfil e lista no painel do paciente. Plano original: `LISTA_ESPERA (PACIENTE_ID, PROFISSIONAL_ID, INICIO_DESEJADO, FIM_DESEJADO, AVISADO_EM)`. Ao cancelar uma sessão (ou abrir disponibilidade), notifica (F3) o primeiro da fila compatível. Primeiro a agendar leva a vaga, sem reserva | M |
| 24 | Cancelamento e reembolso | **?** Regras (ex.: ≥24h reembolso total, <24h 50%, falta 0). `PATCH /api/consultas/<id>` hoje só aceita profissional; adicionar cancelamento pelo paciente. Reembolso via Arkhé: **? confirmar se a API faz estorno de PIX**, senão fica registro `REEMBOLSO_PENDENTE` para o admin | M |
| 32 | Financeiro do psicólogo (realizadas, recebido, taxas, repasses) | Sobre F2: `GET /api/pagamentos/financeiro` por profissional, a partir de `PAGAMENTO` + `TAXA_PLATAFORMA` (env). `REPASSE (PROFISSIONAL_ID, PERIODO, VALOR_CENTAVOS, STATUS)`. **?** repasse manual pelo admin ou automático. Fecha S9 | M |
| 17 | PIX, cartão e boleto | **? Verificar se a Arkhé tem cartão e boleto.** Se tiver: `METODO` em `PAGAMENTO` + rota por método. Se não: gateway extra (Asaas, Mercado Pago, Stripe) atrás da mesma interface de `pagamentos_service`. Cartão **nunca** passa pelo nosso servidor (tokenização do gateway no front) | M a G |
| 4 / 27 | Dashboards mobile do psicólogo e do paciente | **Feito no backend** (20/10/2026): `GET /api/dashboard`. Front/mobile: telas iniciais. Plano original: Front/mobile. Backend: `GET /api/dashboard`, que monta por papel o que já existe (próximas sessões, pacientes do dia, ganhos de F2, notificações não lidas de F3, favoritos de 7). Uma rota em vez de N chamadas no mobile | P (depois de F2/F3/7) |

### Onda C: comunicação (F3, F5, F6)

| # | Tarefa | Backend | Esf. |
|---|---|---|---|
| 18 | Chat seguro paciente × profissional | **Feito** (20/10/2026): migration `0014_mensagem` (tabela nova; `CONVERSA*` do baseline sem uso), `/api/chat` com polling em vez de WS (serve web e app com Bearer e não depende de S7). Fora: criptografia em repouso, auditoria por mensagem. Front: tela de conversas com polling a cada poucos segundos. Plano original: Usar `CONVERSA*` (corrigir o schema, ver seção 3). Só abre conversa quem tem vínculo (sessão não cancelada). REST para histórico paginado + WS `/ws/chat` (mesmo esquema do signaling: memória, processo único, checagem de `Origin` de S7). Auditar a abertura (F5). **?** Criptografar `MENSAGEM` em repouso | G |
| 19 | Arquivos pelo chat | F6: upload para o bucket privado com tipo (PDF, JPG, PNG) e tamanho (10 MB) validados; mensagem guarda a chave, e o download gera URL assinada após checar o participante | M |
| 30 | WhatsApp: confirmações, lembretes, cancelamentos, alterações | **? Provedor**: Meta Cloud API (oficial, exige templates aprovados) ou Z-API/Twilio. `services/whatsapp_service.py` vira um canal de F3. Lembretes: job F7 (24h e 1h antes). `USUARIO.ACEITA_WHATSAPP` (opt-in, LGPD) | M |
| 13 | Link de consulta, comprovante e pagamento pelo WhatsApp | Eventos de F3 (`sessao_agendada`, `pagamento_confirmado`) já roteados para o canal WhatsApp de 30 | P (depois de 30) |
| 12 / 31 | Cancelar, reagendar e agendar pelo WhatsApp | Webhook `POST /api/whatsapp/webhook` (assinatura do provedor validada). Identifica o usuário pelo telefone **verificado** (não confiar no número sem verificação). Menu por botões, sem IA no começo: listar sessões, cancelar (regras de 24), horários livres (F1). Depois pode ligar no agente (16) | G |

### Onda D: inteligência

| # | Tarefa | Backend | Esf. |
|---|---|---|---|
| 5 | Questionário inicial | **Feito** (20/10/2026): migration `0013_preferencia_paciente`, `GET/PUT /api/usuarios/me/preferencias` (sem gênero: o perfil não tem esse campo). Front: tela do questionário. Plano original: `PREFERENCIA_PACIENTE (PACIENTE_ID PK, RESPOSTAS BLOB JSON, ATUALIZADO_EM)`. Perguntas fixas no código (motivo, abordagem preferida, faixa de preço, modalidade, idioma, gênero do profissional?), validadas contra a lista. `GET/PUT /api/pacientes/me/preferencias` | P |
| 2 | Recomendação de psicólogos | **Feito** (20/10/2026): `GET /api/profissionais/recomendados`, pontuação em Python sobre todos os ativos. Front: seção "recomendados para você". Plano original: Sem ML: `GET /api/profissionais/recomendados`, que reaproveita a query de busca e ordena por pontuação simples (abordagem +3, preço na faixa +2, modalidade +2, idioma +1, avaliação). Pesos numa constante | P (depois de 5 e 3) |
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

1. Fase 0 → Fase 1 (refatoração). A Fase 2 (segurança) ficou para o final, a pedido do time
2. Onda A: 28, 14 e 3 (feitas) → **F0 (banco persistente, migrations e CI no Northflank)** → F0.1 (texto em UTF8) → 7 (com F1), 8, F5+20, F8+25
3. F1 agenda → 6, 29 completo; F2 → 24, 32, 17; F3 → 4/27
4. 5 → 2; 30 → 13 → 12/31; 18 → 19
5. 16/21/22 e 11 por último: mais caros e com mais decisões em aberto

### Decisões para levar ao time (agrupadas)

1. Repo privado ou limpeza do histórico (0.2)
2. Vídeo de apresentação: link externo ou upload (3)
3. Regras de cancelamento e reembolso; a Arkhé estorna PIX? (24)
4. A Arkhé tem cartão e boleto? Senão, qual gateway (17)
5. Taxa da plataforma e forma de repasse (32)
6. Provedor de WhatsApp (30)
7. Transcrição: consentimento, retenção, acesso (11)
8. Planos de assinatura (9)
9. F0: merge na `main` só por PR com CI verde, ou manter push direto e disparar o deploy do Northflank pelo Actions?
10. F0: aceitar alguns segundos fora do ar por deploy (volume Single Read/Write)?
