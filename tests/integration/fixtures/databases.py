"""
Database Test Fixtures — Phase 2 Integration Infrastructure

Provides real vector database instances for the ActionEngine's
_execute_vector method:
  1. PostgreSQL + pgvector via testcontainers (Docker required).
  2. SQLite + sqlite-vec via temporary file and extension loading.

Each fixture:
  - Creates the target collection/table.
  - Inserts seed vectors with associated metadata.
  - Yields a connection string and collection name.
  - Cleans up on teardown.

Dependencies:
  - testcontainers[postgres]  (for Postgres fixture)
  - psycopg2-binary           (for seeding Postgres)
  - sqlite-vec                (for SQLite fixture)
"""

import os
import tempfile
from typing import Generator, Tuple

import pytest


# ---------------------------------------------------------------------------
# Seed Data
# ---------------------------------------------------------------------------

SEED_VECTORS = [
    # id, name, category, embedding (768-dim, but we use smaller for tests)
    (1, "Nike Air Zoom", "running shoes", [0.1] * 768),
    (2, "Adidas Ultraboost", "running shoes", [0.15] * 768),
    (3, "North Face Parka", "winter jacket", [0.9] * 768),
    (4, "Patagonia Puffer", "winter jacket", [0.85] * 768),
    (5, "Cotton T-Shirt", "casual wear", [0.5] * 768),
]


# ---------------------------------------------------------------------------
# PostgreSQL + pgvector Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def postgres_vector_db() -> Generator[Tuple[str, str], None, None]:
    """
    Spins up a Postgres container with pgvector, creates a collection,
    inserts seed vectors, and yields (connection_string, collection_name).

    Skipped if Docker is unavailable or testcontainers is not installed.
    """
    pytest.importorskip("testcontainers")
    pytest.importorskip("psycopg2")

    from testcontainers.postgres import PostgresContainer

    postgres = PostgresContainer("pgvector/pgvector:pg16", driver="psycopg2")
    postgres.start()

    conn_str = postgres.get_connection_url()
    collection = "products_embeddings"

    if conn_str.startswith("postgresql+psycopg2://"):
        conn_str = conn_str.replace("postgresql+psycopg2://", "postgresql://", 1)

    import psycopg2
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor()

    # Enable pgvector and create table
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    cur.execute(f"""
        CREATE TABLE {collection} (
            id INT PRIMARY KEY,
            name TEXT,
            category TEXT,
            embedding VECTOR(768)
        );
    """)

    for row in SEED_VECTORS:
        cur.execute(
            f"INSERT INTO {collection} (id, name, category, embedding) VALUES (%s, %s, %s, %s);",
            (row[0], row[1], row[2], row[3])
        )

    conn.commit()
    cur.close()
    conn.close()

    yield conn_str, collection

    postgres.stop()


# ---------------------------------------------------------------------------
# SQLite + sqlite-vec Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def sqlite_vector_db() -> Generator[Tuple[str, str], None, None]:
    """
    Creates a temporary SQLite database with sqlite-vec extension loaded,
    creates a virtual table, inserts seed vectors, and yields
    (db_path, collection_name).
    """
    pytest.importorskip("sqlite_vec")

    import sqlite3
    import sqlite_vec
    import struct

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    collection = "products_embeddings"
    conn.execute(f"""
        CREATE VIRTUAL TABLE {collection} USING vec0(
            id INTEGER PRIMARY KEY,
            name TEXT,
            category TEXT,
            embedding FLOAT[768]
        );
    """)

    for row in SEED_VECTORS:
        vec_bytes = struct.pack(f"{len(row[3])}f", *row[3])
        conn.execute(
            f"INSERT INTO {collection} (id, name, category, embedding) VALUES (?, ?, ?, ?);",
            (row[0], row[1], row[2], vec_bytes)
        )

    conn.commit()
    conn.close()

    yield db_path, collection

    os.unlink(db_path)
