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

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

CMD ["/usr/local/bin/docker-entrypoint.sh"]
