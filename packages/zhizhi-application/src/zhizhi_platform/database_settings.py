"""Relational database configuration owned by the 致知 subscriber."""

from gewu_core.database import DatabaseSettings


class ZhizhiDatabaseSettings(DatabaseSettings):
    """Preserve 致知's project-local SQLite database name."""

    sqlite_file_name: str = "zhizhi.db"
