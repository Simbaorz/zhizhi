#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

set -a
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/.env"
fi
if [[ -f "${PROJECT_ROOT}/.env.local" ]]; then
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/.env.local"
fi
set +a

PROJECT_HOME="${PROJECT_HOME:-${PROJECT_ROOT}}"
if [[ ! -d "${PROJECT_HOME}" ]]; then
  echo "PROJECT_HOME does not exist: ${PROJECT_HOME}" >&2
  exit 1
fi
PROJECT_HOME="$(cd "${PROJECT_HOME}" && pwd)"
export PROJECT_HOME

WEB_CONFIG="${PROJECT_ROOT}/conf/web.yml"
ADMIN_CONFIG="${PROJECT_ROOT}/conf/admin.yml"
WORKER_CONFIG="${PROJECT_ROOT}/conf/worker.yml"

WEB_API_HOST="${WEB_API_HOST:-127.0.0.1}"
WEB_API_PORT="${WEB_API_PORT:-8000}"
ADMIN_API_HOST="${ADMIN_API_HOST:-127.0.0.1}"
ADMIN_API_PORT="${ADMIN_API_PORT:-8001}"
WORKER_LOG_LEVEL="${WORKER_LOG_LEVEL:-INFO}"
CONFIG_SOURCE="${CONFIG_SOURCE:-local}"
export CONFIG_SOURCE

WEB_APOLLO_APP_ID="${WEB_APOLLO_APP_ID:-zhizhi-web-api}"
ADMIN_APOLLO_APP_ID="${ADMIN_APOLLO_APP_ID:-zhizhi-admin-api}"
WORKER_APOLLO_APP_ID="${WORKER_APOLLO_APP_ID:-zhizhi-worker}"

PIDS=()
NAMES=()

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "Missing local configuration: $1" >&2
    echo "Create it from the matching conf/*.example.yml file." >&2
    exit 1
  fi
}

require_value() {
  local name="$1"
  local value="$2"
  if [[ -z "${value}" ]]; then
    echo "Missing required environment value: ${name}" >&2
    exit 1
  fi
}

start_service() {
  local name="$1"
  shift
  echo "Starting ${name}..."
  "$@" &
  PIDS+=("$!")
  NAMES+=("${name}")
}

cleanup() {
  local exit_code=$?
  local pid

  trap - EXIT INT TERM HUP
  if [[ ${#PIDS[@]} -gt 0 ]]; then
    echo
    echo "Stopping local services..."
    for pid in "${PIDS[@]}"; do
      kill "${pid}" >/dev/null 2>&1 || true
    done
    for pid in "${PIDS[@]}"; do
      wait "${pid}" >/dev/null 2>&1 || true
    done
  fi
  exit "${exit_code}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

require_command uv
if [[ "${CONFIG_SOURCE}" == "apollo" ]]; then
  require_value "APOLLO_BASE_URL" "${APOLLO_BASE_URL:-}"
  require_value "WEB_APOLLO_APP_ID" "${WEB_APOLLO_APP_ID}"
  require_value "ADMIN_APOLLO_APP_ID" "${ADMIN_APOLLO_APP_ID}"
  require_value "WORKER_APOLLO_APP_ID" "${WORKER_APOLLO_APP_ID}"
  if [[ "${APOLLO_STARTUP_POLICY:-cache_or_fail}" == "local_fallback" ]]; then
    require_file "${WEB_CONFIG}"
    require_file "${ADMIN_CONFIG}"
    require_file "${WORKER_CONFIG}"
  fi
else
  require_file "${WEB_CONFIG}"
  require_file "${ADMIN_CONFIG}"
  require_file "${WORKER_CONFIG}"
fi

if [[ "${SKIP_UV_SYNC:-0}" != "1" ]]; then
  echo "Synchronizing workspace dependencies..."
  uv sync --all-packages
fi

start_service \
  "Web API (${WEB_API_HOST}:${WEB_API_PORT})" \
  env CONFIG_FILE="${WEB_CONFIG}" APOLLO_APP_ID="${WEB_APOLLO_APP_ID}" \
  uv run --no-sync zhizhi-web-api \
  --host "${WEB_API_HOST}" \
  --port "${WEB_API_PORT}"

start_service \
  "Admin API (${ADMIN_API_HOST}:${ADMIN_API_PORT})" \
  env CONFIG_FILE="${ADMIN_CONFIG}" APOLLO_APP_ID="${ADMIN_APOLLO_APP_ID}" \
  uv run --no-sync zhizhi-admin-api \
  --host "${ADMIN_API_HOST}" \
  --port "${ADMIN_API_PORT}"

start_service \
  "Celery Worker with Beat" \
  env CONFIG_FILE="${WORKER_CONFIG}" APOLLO_APP_ID="${WORKER_APOLLO_APP_ID}" \
  uv run --no-sync zhizhi-worker \
  worker \
  --beat \
  --loglevel="${WORKER_LOG_LEVEL}"

echo
echo "Local services are running. Press Ctrl+C to stop all of them."

while true; do
  for index in "${!PIDS[@]}"; do
    pid="${PIDS[${index}]}"
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      if wait "${pid}"; then
        status=0
      else
        status=$?
      fi
      echo "${NAMES[${index}]} exited with status ${status}." >&2
      exit "${status}"
    fi
  done
  sleep 1
done
