"""Regression coverage for SQLAlchemy's aiomysql pool pre-ping path."""

from sqlalchemy.dialects.mysql.aiomysql import MySQLDialect_aiomysql


class _PingConnection:
    def __init__(self) -> None:
        self.reconnect_values: list[bool] = []

    def ping(self, reconnect: bool) -> None:
        self.reconnect_values.append(reconnect)


def test_aiomysql_pre_ping_passes_the_reconnect_argument() -> None:
    connection = _PingConnection()

    assert MySQLDialect_aiomysql().do_ping(connection) is True
    assert connection.reconnect_values == [False]
