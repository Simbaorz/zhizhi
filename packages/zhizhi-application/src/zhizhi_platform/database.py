"""Relational metadata owned by the Zhizhi subscriber application."""

from sqlalchemy.orm import DeclarativeBase


class ZhizhiBase(DeclarativeBase):
    """Declarative base for tables owned by Zhizhi subscriber packages."""
