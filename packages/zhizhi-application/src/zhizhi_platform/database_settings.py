"""Relational database configuration owned by the Zhizhi subscriber."""

from gewu_core.database import DatabaseSettings


class ZhizhiDatabaseSettings(DatabaseSettings):
    """Preserve Zhizhi's project-local SQLite database name."""

    sqlite_file_name: str = "zhizhi.db"
