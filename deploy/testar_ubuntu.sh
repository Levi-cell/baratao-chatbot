#!/usr/bin/env bash
# pg_virtualenv cria e remove um PostgreSQL exclusivo para esta execução.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"
export PYTHONDONTWRITEBYTECODE=1
export PYTHON_DOTENV_DISABLED=1
export BARATAO_PYTHON="${BARATAO_PYTHON:-/opt/chatbot/venv/bin/python}"
exec pg_virtualenv bash -eu -o pipefail -c '
    export PGHOST=127.0.0.1
    createdb baratao_fluxo_teste
    createdb baratao_consumo_teste
    export BARATAO_TEST_DSN="host=$PGHOST port=$PGPORT user=$PGUSER dbname=baratao_fluxo_teste"
    export BARATAO_CONSUMO_TEST_DSN="host=$PGHOST port=$PGPORT user=$PGUSER dbname=baratao_consumo_teste"
    export DB_HOST="$PGHOST" DB_PORT="$PGPORT" DB_USER="$PGUSER" DB_PASSWORD="$PGPASSWORD" DB_NAME=baratao_fluxo_teste
    export DB_SSLMODE=disable DB_SSLROOTCERT="" REDIS_HOST=127.0.0.1 REDIS_PORT=1
    export META_ACCESS_TOKEN=token-de-teste META_GRAPH_API_VERSION=27.0 META_WEBHOOK_VERIFY_TOKEN=teste
    export META_APP_SECRET=teste DJANGO_SECRET_KEY=chave-local-de-teste DJANGO_ALLOWED_HOSTS=localhost,testserver
    "$BARATAO_PYTHON" -m unittest discover -s tests -v
    createdb baratao_admin_teste
    cd callback
    DB_NAME=baratao_admin_teste PYTHONPATH="$PWD:$PWD/.." DJANGO_SETTINGS_MODULE=callback.settings \
        "$BARATAO_PYTHON" -m unittest -v tests.admin_central_postgres
'
