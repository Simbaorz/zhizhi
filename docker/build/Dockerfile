ARG NODE_IMAGE=node:22-alpine

FROM ${NODE_IMAGE}

ARG ALPINE_MIRROR=https://mirrors.aliyun.com/alpine
ARG NPM_REGISTRY=https://registry.npmmirror.com

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:${PATH} \
    NPM_CONFIG_REGISTRY=${NPM_REGISTRY}

USER root

RUN set -eux; \
    sed -i "s|https://dl-cdn.alpinelinux.org/alpine|${ALPINE_MIRROR}|g" /etc/apk/repositories; \
    apk add --no-cache nginx; \
    npm install --global pnpm@9.15.0 --registry="${NPM_REGISTRY}"; \
    mkdir -p \
      /app \
      /etc/nginx/conf.d \
      /pnpm \
      /tmp/nginx/client_temp \
      /tmp/nginx/fastcgi_temp \
      /tmp/nginx/proxy_temp \
      /tmp/nginx/scgi_temp \
      /tmp/nginx/uwsgi_temp \
      /usr/share/nginx/html; \
    chown -R node:node \
      /app \
      /pnpm \
      /tmp/nginx \
      /usr/share/nginx/html

COPY --chown=root:root docker/build/nginx.conf /etc/nginx/nginx.conf

USER node
WORKDIR /app

COPY --chown=node:node package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
