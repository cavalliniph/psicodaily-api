FROM python:3.14-slim

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        firebird4.0-server \
        firebird4.0-utils \
        libfbclient2 \
    && dpkg -l | grep -E 'firebird|libfbclient' \
    && test -x /usr/lib/firebird/4.0/bin/firebird \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown firebird:firebird /app/database/BANCO.FDB

EXPOSE 8000

CMD /bin/sh -c '\
    /usr/lib/firebird/4.0/bin/firebird -i & \
    sleep 2 && \
    PASS=$(grep "^ISC_PASSWORD=" /etc/firebird/4.0/SYSDBA.password | cut -d= -f2) && \
    /usr/bin/isql-fb -user SYSDBA -password "$PASS" /app/database/BANCO.FDB <<EOF
ALTER USER SYSDBA SET PASSWORD '\''sysdba'\'';
COMMIT;
EOF
    exec gunicorn \
        --bind 0.0.0.0:8000 \
        --access-logfile - \
        --error-logfile - \
        --capture-output \
        app:app'