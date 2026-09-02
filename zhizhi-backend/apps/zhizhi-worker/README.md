# Zhizhi Worker

[Back to Zhizhi Backend](../../README.md)

Some knowledge changes should not make an administrator wait on an HTTP request. Git repositories must be cloned and validated, Scene content must be synchronized safely, and expired chat attachments must eventually be removed.

Zhizhi Worker owns that asynchronous work.

## Responsibilities

The Celery application currently handles:

- dispatching and executing Scene Git synchronization jobs;
- applying synchronized Scene content to the managed Workspace;
- recording synchronization status and failures;
- cleaning up expired chat attachments;
- scheduling recurring work through Celery Beat.

The process exposes no HTTP API and does not execute Agent conversations.

Each Celery child process owns its process-local asynchronous resources. Job concurrency, queue names, soft/hard time limits, and dispatch intervals are controlled by `conf/worker.yml`.

## Shared-state contract

Worker, Admin API, and Web API must agree on:

- database configuration;
- Redis and Celery databases;
- `workspace.storage_root`;
- media filesystem or object-storage configuration;
- `storage_encryption.key`.

A mismatch can make a successfully queued job unreadable or cause a synchronized Scene to appear outside the Runtime's mounted storage.

## Configuration

Create the ignored local file at the backend root:

```bash
cp conf/worker.example.yml conf/worker.yml
```

The process loads `conf/worker.yml` by default. Use `CONFIG_FILE` to select another file, or use the shared Apollo bootstrap settings with `CONFIG_SOURCE=apollo`.

## Run

Start a worker:

```bash
CONFIG_FILE=conf/worker.yml uv run zhizhi-worker worker --loglevel=INFO
```

Start the scheduler separately:

```bash
CONFIG_FILE=conf/worker.yml uv run zhizhi-worker beat --loglevel=INFO
```

For local development, run both in one process:

```bash
CONFIG_FILE=conf/worker.yml uv run zhizhi-worker worker --beat --loglevel=INFO
```

On Windows, the CLI selects Celery's `solo` pool for a worker unless an explicit pool is supplied.

## Focused verification

```bash
uv run pytest apps/zhizhi-worker/tests
uv run ruff check apps/zhizhi-worker
uv run mypy
```

## License

[MIT](../../LICENSE)
