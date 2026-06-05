#!/bin/sh
set -eu

CONFIG_DIR="${BUDGET_DB_CONFIG_DIR:-/app/config}"
CONFIG_FILE="${CONFIG_DIR}/db.env"

generate_password() {
    python -c "import secrets; print(secrets.token_urlsafe(24))"
}

write_mysql_config() {
    mkdir -p "$CONFIG_DIR"
    : "${BUDGET_MYSQL_HOST:=mysql}"
    : "${BUDGET_MYSQL_PORT:=3306}"
    : "${BUDGET_MYSQL_DATABASE:=budget}"
    : "${BUDGET_MYSQL_USER:=budget}"
    : "${BUDGET_MYSQL_PASSWORD:=$(generate_password)}"
    : "${BUDGET_MYSQL_ROOT_USER:=root}"
    : "${BUDGET_MYSQL_ROOT_PASSWORD:=$(generate_password)}"
    {
        printf 'BUDGET_DB_BACKEND=mysql\n'
        printf 'BUDGET_MYSQL_HOST=%s\n' "$BUDGET_MYSQL_HOST"
        printf 'BUDGET_MYSQL_PORT=%s\n' "$BUDGET_MYSQL_PORT"
        printf 'BUDGET_MYSQL_DATABASE=%s\n' "$BUDGET_MYSQL_DATABASE"
        printf 'BUDGET_MYSQL_USER=%s\n' "$BUDGET_MYSQL_USER"
        printf 'BUDGET_MYSQL_PASSWORD=%s\n' "$BUDGET_MYSQL_PASSWORD"
        printf 'BUDGET_MYSQL_ROOT_USER=%s\n' "$BUDGET_MYSQL_ROOT_USER"
        printf 'BUDGET_MYSQL_ROOT_PASSWORD=%s\n' "$BUDGET_MYSQL_ROOT_PASSWORD"
    } > "$CONFIG_FILE"
    chmod 600 "$CONFIG_FILE"
}

load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        set -a
        . "$CONFIG_FILE"
        set +a
    elif [ "${BUDGET_DB_BACKEND:-sqlite}" = "mysql" ]; then
        write_mysql_config
        set -a
        . "$CONFIG_FILE"
        set +a
    fi
}

wait_for_mysql() {
    python - <<'PY'
import os
import socket
import time

host = os.environ.get("BUDGET_MYSQL_HOST", "mysql")
port = int(os.environ.get("BUDGET_MYSQL_PORT", "3306"))
deadline = time.monotonic() + int(os.environ.get("BUDGET_MYSQL_WAIT_SECONDS", "60"))
while time.monotonic() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            raise SystemExit(0)
    except OSError:
        time.sleep(1)
raise SystemExit(f"MySQL indisponible sur {host}:{port}")
PY
}

load_config

if [ "${BUDGET_DB_BACKEND:-sqlite}" = "mysql" ]; then
    wait_for_mysql
    if [ "${BUDGET_MYSQL_CREATE_DATABASE:-0}" = "1" ]; then
        python budget_cli.py --db-backend mysql --create
    fi
fi

exec "$@"
