#!/bin/sh
set -e

# Fail at start, not at the first import, if the Statement files directory isn't writable.
if [ -n "${PURSEGRAPH_STATEMENT_FILES:-}" ] && ! [ -w "$PURSEGRAPH_STATEMENT_FILES" ]; then
    echo "Can't write to $PURSEGRAPH_STATEMENT_FILES: create the host directory, owned by PURSEGRAPH_USER ($(id -u):$(id -g))." >&2
    exit 1
fi

python manage.py migrate --noinput

exec "$@"
