# 致知 Admin Web image

This directory builds a Node.js, pnpm, and Nginx image with the locked frontend dependencies.
Run from the repository root:

```bash
bash docker/build/build.sh
```

Override the image tag directly when needed:

```bash
IMAGE_NAME=registry.example.com/zhizhi-admin-web \
IMAGE_VERSION=v0.1.0 \
PUSH_IMAGE=true \
bash docker/build/build.sh
```

`NODE_IMAGE`, `ALPINE_MIRROR`, and `NPM_REGISTRY` may be overridden for the build environment.
Local `.env`, credentials, archives, and `docker/build/dist/` must remain outside Git.

To export the image as a compressed archive:

```bash
bash docker/build/package.sh
```

The archive is written to `docker/build/dist/` by default. Set
`SKIP_BUILD=true` to package an existing local image and
`OVERWRITE_PACKAGE=true` to replace an existing archive.
