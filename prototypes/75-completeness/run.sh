#!/usr/bin/env bash
# PROTOTYPE (#75), wipe me. Serves the real Dashboard on a scratch database with synthetic data:
#   prototypes/75-completeness/run.sh   →   http://127.0.0.1:8075/  (ana / prototype)
# Needs the test PostgreSQL: docker compose -f compose.test.yaml up -d
set -euo pipefail
cd "$(dirname "$0")/../.."
export POSTGRES_HOST=localhost POSTGRES_PORT=5433 POSTGRES_USER=pursegraph POSTGRES_PASSWORD=pursegraph
export POSTGRES_DB=pursegraph_proto75_wipe_me DJANGO_DEBUG=1 DJANGO_SECRET_KEY=prototype DJANGO_ALLOWED_HOSTS='*'
uv run python -c "
import os, psycopg
with psycopg.connect(host='localhost', port=5433, user='pursegraph', password='pursegraph', dbname='pursegraph', autocommit=True) as c:
    c.execute(f'DROP DATABASE IF EXISTS {os.environ[\"POSTGRES_DB\"]} WITH (FORCE)')
    c.execute(f'CREATE DATABASE {os.environ[\"POSTGRES_DB\"]}')
"
uv run python manage.py migrate -v0
uv run python manage.py shell -c "exec(open('prototypes/75-completeness/seed.py').read())"
exec uv run python manage.py runserver 127.0.0.1:8075
