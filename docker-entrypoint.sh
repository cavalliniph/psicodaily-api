#!/bin/sh
set -e

echo "Starting Firebird..."

 /usr/lib/firebird/4.0/bin/firebird -i &

sleep 5

PASS=$(grep "^ISC_PASSWORD=" /etc/firebird/4.0/SYSDBA.password | cut -d= -f2)

printf "ALTER USER SYSDBA SET PASSWORD 'sysdba';\nCOMMIT;\n" | \
    /usr/bin/isql-fb \
    -user SYSDBA \
    -password "$PASS" \
    127.0.0.1:/app/database/BANCO.FDB

echo "Starting Gunicorn..."

# gthread e nao gevent: o fdb chama o libfbclient via ctypes, que o gevent nao torna
# cooperativo, entao cada query travava o worker inteiro. 1 worker porque as salas do
# signaling ficam em memoria; cada chamada de video ocupa uma thread enquanto dura.
exec gunicorn \
    --worker-class gthread \
    --threads 32 \
    --bind 0.0.0.0:8000 \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    app:app