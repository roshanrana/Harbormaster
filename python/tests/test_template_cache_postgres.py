"""The durable template cache, against a real Postgres.

Shared across Inspector instances on purpose: a per-process cache would make
model cost scale with how many consumers happen to be running, which is exactly
the wrong dependency.
"""

from __future__ import annotations

import os

import pytest

from inspector.mapping.tier3 import PostgresCache

DSN = os.environ.get("HM_TEST_POSTGRES_DSN", "")

pytestmark = pytest.mark.skipif(not DSN, reason="set HM_TEST_POSTGRES_DSN")


@pytest.fixture
def cache() -> PostgresCache:
    import psycopg

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS template_mapping")
        cur.execute(
            """
            CREATE TABLE template_mapping (
                template_fingerprint TEXT NOT NULL,
                client_id            TEXT NOT NULL,
                mappings             JSONB NOT NULL,
                tier                 TEXT NOT NULL,
                confirmed_by         TEXT,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (template_fingerprint, client_id)
            )
            """
        )
        conn.commit()
    return PostgresCache(DSN)


def test_miss_then_hit(cache: PostgresCache) -> None:
    assert cache.get("tf_1", "CLNT004") is None
    assert cache.misses == 1

    cache.put("tf_1", "CLNT004", {"Px_Sett": "settlement_price"}, tier="LLM")
    assert cache.get("tf_1", "CLNT004") == {"Px_Sett": "settlement_price"}
    assert cache.hits == 1


def test_cache_survives_a_new_instance(cache: PostgresCache) -> None:
    # Durability is the point: a restarted Inspector must not re-adjudicate
    # every layout it had already learned.
    cache.put("tf_2", "CLNT004", {"Fld7": "currency"}, tier="LLM")
    fresh = PostgresCache(DSN)
    assert fresh.get("tf_2", "CLNT004") == {"Fld7": "currency"}


def test_scoped_per_client(cache: PostgresCache) -> None:
    cache.put("tf_3", "CLNT004", {"A": "quantity"}, tier="LLM")
    assert cache.get("tf_3", "CLNT011") is None


def test_reviewer_confirmation_is_recorded(cache: PostgresCache) -> None:
    import psycopg

    cache.put("tf_4", "CLNT004", {"A": "quantity"}, tier="HUMAN", confirmed_by="r.chen")
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT tier, confirmed_by FROM template_mapping WHERE template_fingerprint = %s",
            ("tf_4",),
        )
        row = cur.fetchone()
    assert row == ("HUMAN", "r.chen")


def test_put_is_idempotent_and_updates(cache: PostgresCache) -> None:
    cache.put("tf_5", "CLNT004", {"A": "quantity"}, tier="LLM")
    cache.put("tf_5", "CLNT004", {"A": "quantity", "B": "currency"}, tier="HUMAN", confirmed_by="r")
    assert cache.get("tf_5", "CLNT004") == {"A": "quantity", "B": "currency"}
