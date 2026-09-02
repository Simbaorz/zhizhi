#!/usr/bin/env bash

set -Eeuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${script_dir}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${script_dir}/.env"
    set +a
fi

IMAGE_NAME="${IMAGE_NAME:-zhizhi-admin-web-base}"
IMAGE_VERSION="${IMAGE_VERSION:-v0.1.1}"
IMAGE_TAG="${IMAGE_TAG:-${IMAGE_NAME}:${IMAGE_VERSION}}"
OUTPUT_DIR="${OUTPUT_DIR:-${script_dir}/dist}"
SKIP_BUILD="${SKIP_BUILD:-false}"
OVERWRITE_PACKAGE="${OVERWRITE_PACKAGE:-false}"

safe_image_name="${IMAGE_NAME//\//_}"
archive_path="${OUTPUT_DIR}/${safe_image_name}_${IMAGE_VERSION}.tar.gz"

if [[ "${SKIP_BUILD}" != "true" ]]; then
    bash "${script_dir}/build.sh"
fi

docker image inspect "${IMAGE_TAG}" >/dev/null
mkdir -p "${OUTPUT_DIR}"

if [[ -e "${archive_path}" && "${OVERWRITE_PACKAGE}" != "true" ]]; then
    echo "Package already exists: ${archive_path}" >&2
    echo "Set OVERWRITE_PACKAGE=true to replace it." >&2
    exit 2
fi

temporary_tar="$(mktemp "${OUTPUT_DIR}/.zhizhi-admin-web-base-image.XXXXXX.tar")"
cleanup() {
    rm -f "${temporary_tar}"
}
trap cleanup EXIT

docker image save --output "${temporary_tar}" "${IMAGE_TAG}"
gzip --stdout "${temporary_tar}" >"${archive_path}"
chmod 0644 "${archive_path}"

echo "${archive_path}"
