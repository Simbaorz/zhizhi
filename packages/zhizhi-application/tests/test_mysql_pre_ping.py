"""Regression coverage for SQLAlchemy's aiomysql pool pre-ping path."""

import pymysql
from sqlalchemy.dialects.mysql.aiomysql import MySQLDialect_aiomysql


class _PingConnection:
    def __init__(self) -> None:
        self.reconnect_values: list[bool] = []

    def ping(self, reconnect: bool) -> None:
        self.reconnect_values.append(reconnect)


def test_project_uses_embedded_goldendb_driver() -> None:
    assert pymysql.__version__ == "1.0.3"
    assert callable(pymysql.getinstance)
    assert callable(pymysql.closeinstance)


def test_aiomysql_pre_ping_passes_the_reconnect_argument() -> None:
    connection = _PingConnection()

    assert MySQLDialect_aiomysql().do_ping(connection) is True
    assert connection.reconnect_values == [False]
