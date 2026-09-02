"""Dedicated 致知 background worker process."""

from zhizhi_worker.celery_app import create_celery_app

__all__ = ["create_celery_app"]
