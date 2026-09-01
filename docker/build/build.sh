#!/usr/bin/env bash

set -Eeuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${script_dir}/../.." && pwd)"

if [[ -f "${script_dir}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${script_dir}/.env"
    set +a
fi

IMAGE_NAME="${IMAGE_NAME:-zhizhi-backend-base}"
IMAGE_VERSION="${IMAGE_VERSION:-dev}"
IMAGE_TAG="${IMAGE_TAG:-${IMAGE_NAME}:${IMAGE_VERSION}}"
PYTHON_IMAGE="${PYTHON_IMAGE:-python:3.12.6-slim-bookworm}"
UV_VERSION="${UV_VERSION:-0.11.14}"
PYPI_INDEX_URL="${PYPI_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple}"
GEWU_REPOSITORY_URL="${GEWU_REPOSITORY_URL:-https://github.com/Simbaorz/gewu.git}"
GEWU_REF="${GEWU_REF:-main}"
DEBIAN_MIRROR="${DEBIAN_MIRROR:-http://mirrors.aliyun.com/debian}"
DEBIAN_SECURITY_MIRROR="${DEBIAN_SECURITY_MIRROR:-http://mirrors.aliyun.com/debian-security}"
APP_UID="${APP_UID:-10001}"
APP_GID="${APP_GID:-10001}"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-}"
DOCKER_NETWORK="${DOCKER_NETWORK:-}"
NO_CACHE="${NO_CACHE:-false}"
PULL_BASE_IMAGE="${PULL_BASE_IMAGE:-false}"
PUSH_IMAGE="${PUSH_IMAGE:-false}"

build_args=(
    docker build
    --file "${script_dir}/Dockerfile"
    --tag "${IMAGE_TAG}"
    --build-arg "PYTHON_IMAGE=${PYTHON_IMAGE}"
    --build-arg "UV_VERSION=${UV_VERSION}"
    --build-arg "PYPI_INDEX_URL=${PYPI_INDEX_URL}"
    --build-arg "GEWU_REPOSITORY_URL=${GEWU_REPOSITORY_URL}"
    --build-arg "GEWU_REF=${GEWU_REF}"
    --build-arg "DEBIAN_MIRROR=${DEBIAN_MIRROR}"
    --build-arg "DEBIAN_SECURITY_MIRROR=${DEBIAN_SECURITY_MIRROR}"
    --build-arg "APP_UID=${APP_UID}"
    --build-arg "APP_GID=${APP_GID}"
)

if [[ -n "${DOCKER_PLATFORM}" ]]; then
    build_args+=(--platform "${DOCKER_PLATFORM}")
fi
if [[ -n "${DOCKER_NETWORK}" ]]; then
    build_args+=(--network "${DOCKER_NETWORK}")
fi
if [[ "${NO_CACHE}" == "true" ]]; then
    build_args+=(--no-cache)
fi
if [[ "${PULL_BASE_IMAGE}" == "true" ]]; then
    build_args+=(--pull)
fi
build_args+=("${project_root}")

export DOCKER_BUILDKIT=1
"${build_args[@]}"

if [[ "${PUSH_IMAGE}" == "true" ]]; then
    docker push "${IMAGE_TAG}"
fi

echo "Built ${IMAGE_TAG}"
