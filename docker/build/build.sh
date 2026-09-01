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

IMAGE_NAME="${IMAGE_NAME:-zhizhi-admin-web-base}"
IMAGE_VERSION="${IMAGE_VERSION:-v0.1.1}"
IMAGE_TAG="${IMAGE_TAG:-${IMAGE_NAME}:${IMAGE_VERSION}}"
NODE_IMAGE="${NODE_IMAGE:-node:22-alpine}"
ALPINE_MIRROR="${ALPINE_MIRROR:-https://mirrors.aliyun.com/alpine}"
NPM_REGISTRY="${NPM_REGISTRY:-https://registry.npmmirror.com}"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-}"
DOCKER_NETWORK="${DOCKER_NETWORK:-}"
NO_CACHE="${NO_CACHE:-false}"
PULL_BASE_IMAGE="${PULL_BASE_IMAGE:-false}"
PUSH_IMAGE="${PUSH_IMAGE:-false}"

build_args=(
    docker build
    --file "${script_dir}/Dockerfile"
    --tag "${IMAGE_TAG}"
    --build-arg "NODE_IMAGE=${NODE_IMAGE}"
    --build-arg "ALPINE_MIRROR=${ALPINE_MIRROR}"
    --build-arg "NPM_REGISTRY=${NPM_REGISTRY}"
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
