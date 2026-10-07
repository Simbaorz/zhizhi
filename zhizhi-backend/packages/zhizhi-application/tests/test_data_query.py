from __future__ import annotations

import pytest

from zhizhi_platform.data_source.query import validate_query


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "SELECT 1; DROP TABLE orders",
        "WITH gone AS (DELETE FROM orders RETURNING *) SELECT * FROM gone",
        "SELECT * INTO copy FROM orders",
        "SELECT * FROM orders FOR UPDATE",
        "SELECT pg_sleep(10)",
        "SELECT 1 /* unclosed",
    ],
)
def test_mutations_and_side_effects_are_rejected(sql: str) -> None:
    with pytest.raises(ValueError):
        validate_query(sql, "postgresql", (), {})


def test_query_validation_preserves_bound_parameters_and_checks_schema() -> None:
    sql = "SELECT id FROM sales.orders WHERE id = :order_id"
    assert validate_query(sql, "postgresql", ("sales",), {"order_id": 7}) == sql
    with pytest.raises(ValueError):
        validate_query(sql, "postgresql", ("public",), {"order_id": 7})
    with pytest.raises(ValueError):
        validate_query(sql, "postgresql", ("sales",), {})


def test_row_limits_are_applied_to_the_database_query_and_cannot_be_overridden() -> None:
    assert validate_query("SELECT 1 -- trailing comment", "mysql", (), {}, 3).endswith("\nLIMIT 3")
    assert (
        validate_query("SELECT 1 LIMIT :count", "postgresql", (), {"count": 2}, 3)
        == "SELECT 1 LIMIT :count"
    )
    with pytest.raises(ValueError):
        validate_query("SELECT 1 LIMIT 1000", "postgresql", (), {}, 3)
