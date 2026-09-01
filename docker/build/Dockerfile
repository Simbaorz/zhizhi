ARG PYTHON_IMAGE=python:3.12.6-slim-bookworm

FROM ${PYTHON_IMAGE} AS runtime-base

ARG DEBIAN_MIRROR=http://mirrors.aliyun.com/debian
ARG DEBIAN_SECURITY_MIRROR=http://mirrors.aliyun.com/debian-security

ENV DEBIAN_FRONTEND=noninteractive

RUN set -eux; \
    rm -f /etc/apt/sources.list.d/*; \
    printf '%s\n' \
      "deb ${DEBIAN_MIRROR} bookworm main contrib non-free non-free-firmware" \
      "deb ${DEBIAN_MIRROR} bookworm-updates main contrib non-free non-free-firmware" \
      "deb ${DEBIAN_SECURITY_MIRROR} bookworm-security main contrib non-free non-free-firmware" \
      > /etc/apt/sources.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      bash \
      ca-certificates \
      coreutils \
      diffutils \
      findutils \
      git \
      openssh-client \
      tzdata \
      unzip \
      zip; \
    rm -rf /var/lib/apt/lists/*

FROM runtime-base AS builder

ARG UV_VERSION=0.11.14
ARG PYPI_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ARG GEWU_REPOSITORY_URL=https://github.com/Simbaorz/gewu.git
ARG GEWU_REF=main

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/zhizhi/template/.venv \
    UV_DEFAULT_INDEX=${PYPI_INDEX_URL}

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends build-essential curl; \
    pip install --no-cache-dir --index-url "${PYPI_INDEX_URL}" "uv==${UV_VERSION}"; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/zhizhi

RUN git clone --depth 1 --branch "${GEWU_REF}" "${GEWU_REPOSITORY_URL}" gewu

WORKDIR /opt/zhizhi/template

COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --all-packages

ENV TIKTOKEN_CACHE_DIR=/opt/zhizhi/tiktoken-cache

RUN set -eux; \
    mkdir -p "${TIKTOKEN_CACHE_DIR}"; \
    curl -fsSL \
      "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken" \
      -o "${TIKTOKEN_CACHE_DIR}/9b5ad71b2ce5302211f9c61530b329a4922fc6a4"; \
    curl -fsSL \
      "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken" \
      -o "${TIKTOKEN_CACHE_DIR}/fb374d419588a4632f3f557e76b4b70aebbca790"; \
    printf '%s  %s\n' \
      '223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7' "${TIKTOKEN_CACHE_DIR}/9b5ad71b2ce5302211f9c61530b329a4922fc6a4" \
      '446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d' "${TIKTOKEN_CACHE_DIR}/fb374d419588a4632f3f557e76b4b70aebbca790" \
      | sha256sum -c -

FROM runtime-base AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

ENV APOLLO_CACHE_DIR=/var/lib/zhizhi/runtime/apollo \
    CONFIG_ROOT=/etc/zhizhi \
    CONFIG_SOURCE=local \
    HOME=/home/zhizhi \
    MODE=prod \
    PATH=/opt/zhizhi/template/.venv/bin:${PATH} \
    PROJECT_HOME=/data/zhizhi \
    PROJECT_NAME=zhizhi \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RUNTIME_STATE_ROOT=/var/lib/zhizhi/runtime \
    SOURCE_ROOT=/opt/zhizhi/source \
    TIKTOKEN_CACHE_DIR=/opt/zhizhi/tiktoken-cache \
    TIMEZONE=Asia/Shanghai

RUN set -eux; \
    groupadd --gid "${APP_GID}" zhizhi; \
    useradd --create-home --uid "${APP_UID}" --gid "${APP_GID}" --shell /bin/bash zhizhi; \
    mkdir -p \
      /data/zhizhi \
      /etc/zhizhi \
      /opt/zhizhi/source \
      /var/lib/zhizhi/runtime; \
    chown -R zhizhi:zhizhi \
      /data/zhizhi \
      /etc/zhizhi \
      /opt/zhizhi/source \
      /var/lib/zhizhi

COPY --from=builder --chown=zhizhi:zhizhi /opt/zhizhi /opt/zhizhi
COPY --chown=root:root docker/k8s/runtime-entrypoint.sh /usr/local/bin/runtime-entrypoint.sh

RUN chmod 0755 /usr/local/bin/runtime-entrypoint.sh

USER zhizhi
WORKDIR /opt/zhizhi/template

EXPOSE 8000 8001

STOPSIGNAL SIGTERM

ENTRYPOINT ["runtime-entrypoint.sh"]
CMD ["web-api"]
