# 致知 Worker

`zhizhi-worker` is the Celery worker and scheduler process for 致知.
It executes Scene Git synchronization and expired chat attachment cleanup jobs. The process owns
its broker configuration and process-local asynchronous resources; it does not expose HTTP APIs.

The process loads `conf/worker.yml` by default and accepts `CONFIG_FILE` as an explicit override.
Initialize the ignored local file from `conf/worker.example.yml`, then run the worker and scheduler:

```bash
uv run zhizhi-worker worker --loglevel=INFO
uv run zhizhi-worker beat --loglevel=INFO
```

Admin API, Web API, and Worker must use the same database, Workspace storage root, Redis
deployment, and storage-encryption key.
