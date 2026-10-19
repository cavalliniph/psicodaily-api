# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

PsicoDaily API: Flask backend (Portuguese codebase) for a mental-health platform connecting patients (`PACIENTE`) with professionals (`PSICOLOGO`, `PSIQUIATRA`). Frontend: `psicodaily-front` (Vercel, Vite on :5173).

## Claude files

Everything Claude-related lives in `.claude/`: this file, `architecture.md`, `skills/` (real folders, not symlinks), `skills-lock.json` and `install.cmd` (Claude Code installer for CMD). Don't create Claude docs, skills or config at the repo root or in `.agents/`. `.claude/` is excluded from the Docker image (`.dockerignore`).

## Commands

- Install: `pip install -r requirements.txt` (venv in `.venv`). Copy `.env.example` to `.env`.
- Dev (WSL): `./run.sh` runs gunicorn gthread with one process on 127.0.0.1:8000 and :8001.
- Dev (Windows, no WSL/Docker): Firebird 4 runs as the `FirebirdServerDefaultInstance` service (SYSDBA/`sysdba`). Run `.venv\Scripts\python app.py` (Flask dev server, threaded, port 5000; gunicorn doesn't run on Windows). In `.env`, `DB_DATABASE` is the absolute path to `database/BANCO.FDB`. Leave `ENDPOINT_URL` commented out until you have real R2 keys: the `<account-id>` placeholder crashes boto3 at import.
- Docker: `Dockerfile` bundles Firebird 4 + `database/BANCO.FDB`; `docker-entrypoint.sh` starts Firebird, then gunicorn on :8000.
- Tests: no framework. Assert scripts need Firebird running and undo whatever they create. Run each with `.venv\Scripts\python tests/<file>.py` (`test_pool.py`, `test_profissionais.py`). Route tests use Flask's `test_client` and set a cookie created with `gerar_token`.

## Architecture

Full map (routes, data model, flows, known risks) in [architecture.md](architecture.md). Read it before touching cross-cutting code, and update it when routes, tables or infra change.

- `app.py` registers one Blueprint per domain from `view/*.py` (auth, usuarios, registros, prontuario, profissionais, consultas, encaminhamentos, pagamentos, signaling). Routes live under `/api/...`.
- **Database**: Firebird via `fdb`, raw SQL only (no ORM). Schema and CHECK domains are in `database/schema.sql`. Routes call `get_connection()` from `database/db.py` and must call `con.close()` in `finally`. `close()` rolls back anything uncommitted and returns the connection to a LIFO pool (max 10). So **commit explicitly** before close.
- **Auth**: JWT (HS256, `SECRET_KEY`) in the `access_token` cookie. Decorators in `util/usuarios.py`: `usuario_autenticado` and `profissional_autenticado` pass the decoded payload (`id_usuario`, `usuario_role`) as the first argument. Role checks inside routes read `usuario_role`.
- `funcao.py` holds the shared helpers: tokens, password hashing/validation, CPF/email/phone validation, email sending (Jinja template `templates/email_codigo.html`), `criar_usuario_base`, and professional-specific normalizers. Check it before writing a new validator.
- **Video calls**: WebSocket `/ws/signaling?sessao_id=` (flask-sock), which relays WebRTC offer/answer/ICE. Rooms live **in memory** in `services/signaling_service.py`, so the server must run as **one process** (gthread, 32 threads). Don't add workers or switch to gevent: `fdb` uses ctypes and would block the event loop.
- **Payments**: `view/pagamentos.py` proxies the external Arkhé PIX API (`ARKHE_BASE_URL`, `CLIENT_ID`/`CLIENT_SECRET`) using `urllib`.
- **Profile photos**: Cloudflare R2 via boto3 + Pillow (`services/upload_service.py`; env `ENDPOINT_URL`, `ACCESS_KEY_ID`, `SECRET_ACCESS_KEY`, `R2_PUBLIC_URL`).
- CORS origins are hard-coded in `app.py`; add new frontend hosts there.

## Conventions

- Error responses: `jsonify({'error': msg}), status`.
- Validate request bodies against allowed fields and domain values (see `view/registros.py`) and reject unknown fields. Never trust `usuario_id` from the body; take it from the token.
- Commit messages: Conventional Commits in Portuguese (`feat: ...`, `fix: ...`).
