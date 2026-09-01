#!/usr/bin/env bash

set -Eeuo pipefail

# This entrypoint is part of the pipeline-managed Kubernetes runtime contract.

service="${1:-web-api}"
if (($# > 0)); then
    shift
fi

CONFIG_ROOT="${CONFIG_ROOT:-/etc/zhizhi}"
PROJECT_HOME="${PROJECT_HOME:-/data/zhizhi}"
SOURCE_ROOT="${SOURCE_ROOT:-/opt/zhizhi/source}"
RUNTIME_STATE_ROOT="${RUNTIME_STATE_ROOT:-/var/lib/zhizhi/runtime}"

WEB_API_HOST="${WEB_API_HOST:-${WEB_API_HOST:-0.0.0.0}}"
WEB_API_PORT="${WEB_API_PORT:-${WEB_API_PORT:-8000}}"
WEB_API_WORKERS="${WEB_API_WORKERS:-${WEB_API_WORKERS:-1}}"
ADMIN_API_HOST="${ADMIN_API_HOST:-0.0.0.0}"
ADMIN_API_PORT="${ADMIN_API_PORT:-8001}"
ADMIN_API_WORKERS="${ADMIN_API_WORKERS:-1}"
WORKER_LOG_LEVEL="${WORKER_LOG_LEVEL:-INFO}"
BEAT_LOG_LEVEL="${BEAT_LOG_LEVEL:-INFO}"
CELERY_BEAT_SCHEDULE_PATH="${CELERY_BEAT_SCHEDULE_PATH:-${RUNTIME_STATE_ROOT}/celerybeat-schedule}"
CELERY_BEAT_PID_PATH="${CELERY_BEAT_PID_PATH:-${RUNTIME_STATE_ROOT}/celerybeat.pid}"

export PROJECT_HOME
export APOLLO_CACHE_DIR="${APOLLO_CACHE_DIR:-${RUNTIME_STATE_ROOT}/apollo}"

die() {
    echo "$*" >&2
    exit 2
}

require_file() {
    local path="$1"
    local description="$2"
    [[ -f "${path}" ]] || die "Missing ${description}: ${path}"
}

validate_source_root() {
    case "${SOURCE_ROOT}" in
        /|"${HOME}"|"${PROJECT_HOME}")
            die "Refusing unsafe SOURCE_ROOT: ${SOURCE_ROOT}"
            ;;
    esac
}

activate_pipeline_source() {
    local active_source_root="${SOURCE_ROOT}"
    local joined_python_path
    local -a python_paths=()

    validate_source_root
    for source_group in apps packages; do
        if [[ -d "${active_source_root}/${source_group}" ]]; then
            while IFS= read -r -d '' python_source; do
                python_paths+=("${python_source}")
            done < <(
                find "${active_source_root}/${source_group}" -type d -name src -print0 \
                    | LC_ALL=C sort -z
            )
        fi
    done
    if [[ -d "${active_source_root}/lib/python_driver" ]]; then
        python_paths+=("${active_source_root}/lib/python_driver")
    fi
    ((${#python_paths[@]} > 0)) || die \
        "No runtime Python source directories found under ${active_source_root}."

    joined_python_path="$(IFS=:; echo "${python_paths[*]}")"
    export PYTHONPATH="${joined_python_path}${PYTHONPATH:+:${PYTHONPATH}}"
    cd "${active_source_root}"
}

prepare_service_config() {
    local default_file="$1"
    local apollo_app_id_variable="$2"
    local service_apollo_app_id="${!apollo_app_id_variable:-}"
    local config_source="${CONFIG_SOURCE:-local}"

    export CONFIG_FILE="${CONFIG_FILE:-${CONFIG_ROOT}/${default_file}}"
    if [[ -z "${APOLLO_APP_ID:-}" && -n "${service_apollo_app_id}" ]]; then
        export APOLLO_APP_ID="${service_apollo_app_id}"
    fi

    if [[ "${config_source}" == "local" || \
        "${APOLLO_STARTUP_POLICY:-cache_or_fail}" == "local_fallback" ]]; then
        require_file "${CONFIG_FILE}" "service configuration"
    fi
}

mkdir -p "${PROJECT_HOME}" "${RUNTIME_STATE_ROOT}" "${APOLLO_CACHE_DIR}"
umask 027

case "${service}" in
    web-api)
        activate_pipeline_source
        prepare_service_config web.yml WEB_APOLLO_APP_ID
        exec zhizhi-web-api \
            --host "${WEB_API_HOST}" \
            --port "${WEB_API_PORT}" \
            --workers "${WEB_API_WORKERS}" \
            "$@"
        ;;
    admin-api)
        activate_pipeline_source
        prepare_service_config admin.yml ADMIN_APOLLO_APP_ID
        exec zhizhi-admin-api \
            --host "${ADMIN_API_HOST}" \
            --port "${ADMIN_API_PORT}" \
            --workers "${ADMIN_API_WORKERS}" \
            "$@"
        ;;
    worker)
        activate_pipeline_source
        prepare_service_config worker.yml WORKER_APOLLO_APP_ID
        exec zhizhi-worker worker \
            --loglevel="${WORKER_LOG_LEVEL}" \
            "$@"
        ;;
    beat)
        activate_pipeline_source
        prepare_service_config worker.yml WORKER_APOLLO_APP_ID
        mkdir -p "$(dirname "${CELERY_BEAT_SCHEDULE_PATH}")"
        mkdir -p "$(dirname "${CELERY_BEAT_PID_PATH}")"
        exec zhizhi-worker beat \
            --loglevel="${BEAT_LOG_LEVEL}" \
            --schedule="${CELERY_BEAT_SCHEDULE_PATH}" \
            --pidfile="${CELERY_BEAT_PID_PATH}" \
            "$@"
        ;;
    *)
        die "Unknown service '${service}'. Expected web-api, admin-api, worker, or beat."
        ;;
esac
