#!/bin/sh
# Dev local (WSL). Um só processo escutando nas duas portas: as salas do signaling
# ficam em memória, então dois processos separados quebrariam a videochamada.
cd "$(dirname "$0")"
exec .venv/bin/gunicorn \
    --worker-class gthread \
    --threads 32 \
    --bind 127.0.0.1:8000 \
    --bind 127.0.0.1:8001 \
    app:app
