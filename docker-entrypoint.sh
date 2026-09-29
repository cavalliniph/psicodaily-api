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

exec gunicorn \
    --worker-class gevent \
    --bind 0.0.0.0:8000 \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    app:app