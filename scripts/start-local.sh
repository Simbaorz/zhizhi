#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_ROOT="${PROJECT_ROOT}/zhizhi-backend"
ADMIN_WEB_ROOT="${PROJECT_ROOT}/zhizhi-admin-web"
WEB_ROOT="${PROJECT_ROOT}/zhizhi-web"
PORTAL_ADMIN_ROOT="${PROJECT_ROOT}/zhizhi-portal-admin-web"

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
DATA_MCP_CONFIG="${PROJECT_ROOT}/conf/data-mcp.yml"
PORTAL_CONFIG="${PROJECT_ROOT}/conf/portal.yml"
if [[ ! -f "${PORTAL_CONFIG}" ]]; then
  cp "${PROJECT_ROOT}/conf/portal.example.yml" "${PORTAL_CONFIG}"
fi

WEB_API_HOST="${WEB_API_HOST:-127.0.0.1}"
WEB_API_PORT="${WEB_API_PORT:-8000}"
DATA_MCP_PORT="${DATA_MCP_PORT:-8002}"
PORTAL_API_PORT="${PORTAL_API_PORT:-8003}"
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

run_in_directory() {
  local directory="$1"
  shift
  cd "${directory}"
  exec "$@"
}

check_services() {
  local index pid status
  for index in "${!PIDS[@]}"; do
    pid="${PIDS[${index}]}"
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      if wait "${pid}"; then
        status=1
      else
        status=$?
      fi
      echo "${NAMES[${index}]} exited with status ${status}." >&2
      exit "${status}"
    fi
  done
}

wait_ready() {
  local name="$1" url="$2" deadline=$((SECONDS + 120))
  echo "Waiting for ${name}..."
  until curl --noproxy '*' --fail --silent --output /dev/null --max-time 2 "${url}"; do
    check_services
    if (( SECONDS >= deadline )); then
      echo "${name} did not become ready within 120 seconds: ${url}" >&2
      exit 1
    fi
    sleep 1
  done
  check_services
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
require_command corepack
require_command curl
require_file "${DATA_MCP_CONFIG}"
# The local test Portal reads platform infrastructure from Admin's local YAML.
require_file "${ADMIN_CONFIG}"
require_file "${PORTAL_CONFIG}"
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
  echo "Synchronizing backend dependencies..."
  (
    cd "${BACKEND_ROOT}"
    uv sync --all-packages --frozen
  )
fi

# Use the adjacent Runtime checkout for local development; deployments keep the Git pin.
GEWU_RUNTIME_SOURCE="${GEWU_RUNTIME_SOURCE:-${PROJECT_ROOT}/../gewu/packages/agent-runtime}"
if [[ -d "${GEWU_RUNTIME_SOURCE}" ]]; then
  GEWU_RUNTIME_SOURCE="$(cd "${GEWU_RUNTIME_SOURCE}" && pwd)"
  echo "Installing local Gewu Runtime: ${GEWU_RUNTIME_SOURCE}"
  uv pip install --python "${BACKEND_ROOT}/.venv/bin/python" --no-deps \
    --editable "${GEWU_RUNTIME_SOURCE}"
fi

# Apollo deployments may use remote dependencies unavailable in the local YAML.
if [[ "${CONFIG_SOURCE}" == "apollo" ]]; then
  START_LOCAL_DOCKER="${START_LOCAL_DOCKER:-0}"
else
  START_LOCAL_DOCKER="${START_LOCAL_DOCKER:-1}"
fi
if [[ "${START_LOCAL_DOCKER}" == "1" ]]; then
  require_command docker
  echo "Starting configured local MySQL/Redis dependencies..."
  (
    cd "${BACKEND_ROOT}"
    uv run --no-sync python "${SCRIPT_DIR}/local_dependencies.py"
  )
fi

if [[ "${SKIP_PNPM_INSTALL:-0}" != "1" ]]; then
  echo "Installing Admin Web dependencies..."
  (
    cd "${ADMIN_WEB_ROOT}"
    corepack pnpm install --frozen-lockfile
  )
  echo "Installing Web dependencies..."
  (
    cd "${WEB_ROOT}"
    corepack pnpm install --frozen-lockfile
  )
  echo "Installing Portal Admin dependencies..."
  (
    cd "${PORTAL_ADMIN_ROOT}"
    corepack pnpm install --frozen-lockfile
  )
fi

# Fail before launching anything if another stack owns one of these ports.
(
  cd "${BACKEND_ROOT}"
  uv run --no-sync python - \
    "${WEB_API_HOST}" "${WEB_API_PORT}" \
    "${ADMIN_API_HOST}" "${ADMIN_API_PORT}" \
    127.0.0.1 "${DATA_MCP_PORT}" 127.0.0.1 "${PORTAL_API_PORT}" \
    127.0.0.1 5173 127.0.0.1 5174 127.0.0.1 5175 <<'PY'
import socket
import sys

for host, port in zip(sys.argv[1::2], sys.argv[2::2]):
    try:
        with socket.create_server((host, int(port))):
            pass
    except (OSError, ValueError):
        sys.exit(f"Cannot listen on {host}:{port}. Check the configured host/port and stop the existing service before restarting.")
PY
)

start_service \
  "Web API (${WEB_API_HOST}:${WEB_API_PORT})" \
  run_in_directory "${BACKEND_ROOT}" \
  env CONFIG_FILE="${WEB_CONFIG}" APOLLO_APP_ID="${WEB_APOLLO_APP_ID}" \
  uv run --no-sync zhizhi-web-api \
  --host "${WEB_API_HOST}" \
  --port "${WEB_API_PORT}"

start_service \
  "Admin API (${ADMIN_API_HOST}:${ADMIN_API_PORT})" \
  run_in_directory "${BACKEND_ROOT}" \
  env CONFIG_FILE="${ADMIN_CONFIG}" APOLLO_APP_ID="${ADMIN_APOLLO_APP_ID}" \
  uv run --no-sync zhizhi-admin-api \
  --host "${ADMIN_API_HOST}" \
  --port "${ADMIN_API_PORT}"

start_service \
  "Celery Worker with Beat" \
  run_in_directory "${BACKEND_ROOT}" \
  env CONFIG_FILE="${WORKER_CONFIG}" APOLLO_APP_ID="${WORKER_APOLLO_APP_ID}" \
  uv run --no-sync zhizhi-worker \
  worker \
  --beat \
  --loglevel="${WORKER_LOG_LEVEL}"

start_service "Data MCP (127.0.0.1:${DATA_MCP_PORT})" \
  run_in_directory "${BACKEND_ROOT}" \
  env CONFIG_FILE="${DATA_MCP_CONFIG}" \
  uv run --no-sync zhizhi-data-mcp --host 127.0.0.1 --port "${DATA_MCP_PORT}"

start_service "Test Portal (127.0.0.1:${PORTAL_API_PORT})" \
  run_in_directory "${BACKEND_ROOT}" \
  env CONFIG_SOURCE=local CONFIG_FILE="${PORTAL_CONFIG}" \
  PORTAL_PLATFORM_CONFIG_FILE="${ADMIN_CONFIG}" PORTAL_AGENT_API_URL="http://${WEB_API_HOST}:${WEB_API_PORT}" \
  uv run --no-sync zhizhi-portal-api --host 127.0.0.1 --port "${PORTAL_API_PORT}"

wait_ready "Admin API" "http://${ADMIN_API_HOST}:${ADMIN_API_PORT}/readyz"
wait_ready "Web API" "http://${WEB_API_HOST}:${WEB_API_PORT}/readyz"
wait_ready "Test Portal" "http://127.0.0.1:${PORTAL_API_PORT}/readyz"

start_service "Portal Admin (127.0.0.1:5175)" \
  run_in_directory "${PORTAL_ADMIN_ROOT}" \
  env ZHIZHI_PORTAL_API_PROXY_TARGET="http://127.0.0.1:${PORTAL_API_PORT}" \
  corepack pnpm run dev --host 127.0.0.1 --strictPort

start_service \
  "Admin Web (127.0.0.1:5173)" \
  run_in_directory "${ADMIN_WEB_ROOT}" \
  env ZHIZHI_ADMIN_API_PROXY_TARGET="http://${ADMIN_API_HOST}:${ADMIN_API_PORT}" \
  corepack pnpm run dev --host 127.0.0.1 --strictPort

start_service \
  "Web (127.0.0.1:5174)" \
  run_in_directory "${WEB_ROOT}" \
  env ZHIZHI_PORTAL_API_PROXY_TARGET="http://127.0.0.1:${PORTAL_API_PORT}" \
  corepack pnpm run dev --host 127.0.0.1 --strictPort

wait_ready "Admin Web" "http://127.0.0.1:5173"
wait_ready "Web" "http://127.0.0.1:5174"
wait_ready "Portal Admin" "http://127.0.0.1:5175"

echo
echo "Local services are running:"
echo "  Admin Web: http://127.0.0.1:5173"
echo "  Web:       http://127.0.0.1:5174"
echo "  Web API:   http://${WEB_API_HOST}:${WEB_API_PORT}"
echo "  Admin API: http://${ADMIN_API_HOST}:${ADMIN_API_PORT}"
echo "  Portal:    http://127.0.0.1:${PORTAL_API_PORT}"
echo "  Portal Admin: http://127.0.0.1:5175"
echo "  Data MCP:  http://127.0.0.1:${DATA_MCP_PORT}/mcp"
echo "Press Ctrl+C to stop all of them."

while true; do
  check_services
  sleep 1
done
