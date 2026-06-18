# ai_engine/vector_search.py

import json
import logging
import requests
from abc import ABC, abstractmethod
from typing import List, Dict, Any

from .config import ExecutionConfig, EmbeddingConfig
from .exceptions import UnsupportedDatabaseDriver, EmbeddingGenerationError, VectorSearchError
from .providers import ModelFactory

import re

logger = logging.getLogger("VectorSearch")


def generate_embedding(text: str, config: EmbeddingConfig) -> List[float]:
    """Generates a vector embedding using the configured provider dynamically."""
    try:
        embeddings_model = ModelFactory.get_embeddings(config)
        return embeddings_model.embed_query(text)
    except Exception as e:
        raise EmbeddingGenerationError(f"Failed to generate embedding: {str(e)}")
    

class BaseVectorDriver(ABC):
    @abstractmethod
    def search(self, query_vector: List[float], config: ExecutionConfig) -> List[Dict[str, Any]]:
        pass

class PostgresVectorDriver(BaseVectorDriver):
    """Driver for PostgreSQL with the pgvector extension."""
    def search(self, query_vector: List[float], config: ExecutionConfig) -> List[Dict[str, Any]]:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            from psycopg2 import sql
        except ImportError:
            raise VectorSearchError("Install 'psycopg2-binary' to use the postgres connector.")

        conn_str = config.connection_string
        if config.auth and "user=" not in conn_str:
            conn_str += f" user={config.auth.get('user')} password={config.auth.get('pass')}"
        
        try:
            with psycopg2.connect(conn_str) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    vector_str = "[" + ",".join(map(str, query_vector)) + "]"
                    
                    query = sql.SQL("""
                        SELECT * 
                        FROM {} 
                        ORDER BY embedding <=> %s::vector 
                        LIMIT %s
                    """).format(sql.Identifier(config.collection_name))
                    
                    cur.execute(query, (vector_str, config.max_results))
                    results = cur.fetchall()
                    
                    cleaned_results = []
                    for row in results:
                        row_dict = dict(row)
                        row_dict.pop('embedding', None) 
                        cleaned_results.append(row_dict)
                    return cleaned_results
        except Exception as e:
            raise VectorSearchError(f"PostgreSQL Search Failed: {str(e)}")

class SQLiteVectorDriver(BaseVectorDriver):
    """Driver for SQLite using sqlite-vec or similar extensions."""
    def search(self, query_vector: List[float], config: ExecutionConfig) -> List[Dict[str, Any]]:
        try:
            import sqlite3
            import struct
        except ImportError:
            raise VectorSearchError("sqlite3 is not available.")

        if not re.match(r"^[a-zA-Z0-9_]+$", config.collection_name):
            raise VectorSearchError("Invalid collection name format.")

        try:
            conn = sqlite3.connect(config.connection_string)
            conn.row_factory = sqlite3.Row
            conn.enable_load_extension(True)
            
            vector_bytes = struct.pack(f"{len(query_vector)}f", *query_vector)
            
            query = f"""
                SELECT *
                FROM {config.collection_name}
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT ?
            """
            
            cur = conn.cursor()
            cur.execute(query, (vector_bytes, config.max_results))
            
            results = [dict(row) for row in cur.fetchall()]
            for r in results:
                r.pop('embedding', None)
            return results
        except Exception as e:
            raise VectorSearchError(f"SQLite Search Failed: {str(e)}")
        finally:
            if 'conn' in locals():
                conn.close()

DRIVER_REGISTRY = {
    "postgres": PostgresVectorDriver,
    "sqlite": SQLiteVectorDriver
}

def get_vector_driver(connector_name: str) -> BaseVectorDriver:
    driver_class = DRIVER_REGISTRY.get(connector_name.lower())
    if not driver_class:
        valid_connectors = ", ".join(DRIVER_REGISTRY.keys())
        raise UnsupportedDatabaseDriver(f"Connector '{connector_name}' is not supported. Use one of: {valid_connectors}")
    return driver_class()