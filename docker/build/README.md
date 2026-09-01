# Zhizhi Backend container image

Run the build from the backend repository root:

```bash
./docker/build/build.sh
```

The image contains Python, the public Gewu source, all locked Python dependencies, the Zhizhi
backend, and the runtime entrypoint. By default it clones the `main` branch from
`https://github.com/Simbaorz/gewu.git`. Override `GEWU_REPOSITORY_URL` or `GEWU_REF` when building
against another public fork or revision.

Set `IMAGE_NAME` to a registry path and `PUSH_IMAGE=true` to push after a successful build. To
package the image as a file:

```bash
./docker/build/package.sh
```

The archive is written under `docker/build/dist/` and can be imported with `docker load` or the
equivalent container-runtime command. Local `.env`, image archives, credentials, and build output
must not be committed.
