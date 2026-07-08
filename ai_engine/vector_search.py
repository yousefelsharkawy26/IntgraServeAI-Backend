import logging
import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any

from .config import ExecutionConfig, EmbeddingConfig
from utils.exceptions import (
    UnsupportedDatabaseDriver, EmbeddingGenerationError, VectorSearchError,
    CorrelationIdAdapter, ProviderConfigurationError
)
from .providers import ModelFactory

logger = CorrelationIdAdapter(logging.getLogger(__name__))


# Typed exceptions for embedding provider errors
class EmbeddingProviderError(EmbeddingGenerationError):
    """Base exception for embedding provider errors."""
    pass


class OllamaConnectionError(EmbeddingProviderError):
    """Raised when Ollama server is unreachable."""
    pass


class OllamaModelError(EmbeddingProviderError):
    """Raised when Ollama model is not available."""
    pass


class ProviderAuthenticationError(EmbeddingProviderError):
    """Raised when provider authentication fails."""
    pass


class ProviderTimeoutError(EmbeddingProviderError):
    """Raised when provider request times out."""
    pass


def generate_embedding(text: str, config: EmbeddingConfig) -> List[float]:
    """Generates a vector embedding using the configured provider dynamically."""
    if isinstance(config, EmbeddingConfig):
        try:
            embeddings_model = ModelFactory.get_embeddings(config)
            return embeddings_model.embed_query(text)
        except Exception as e:
            raise EmbeddingGenerationError(f"Failed to generate embedding: {str(e)}")
    raise ProviderConfigurationError(f" recieved config object type: '{str(type(config))}' instead of 'EmbeddingConfig' ")


def validate_embedding_provider(config: EmbeddingConfig) -> None:
    """
    Lightweight validation that the embedding provider is available.
    
    This performs inexpensive checks during startup:
    - For Ollama: Check server availability and model existence via API
    - For other providers: Initialize client and validate configuration
    
    Does NOT generate actual embeddings to avoid expensive operations at startup.
    
    Raises:
        OllamaConnectionError: If Ollama server is unreachable
        OllamaModelError: If Ollama model is not available
        ProviderAuthenticationError: If provider authentication fails
        ProviderTimeoutError: If provider request times out
        EmbeddingProviderError: For other provider errors
    """
    try:
        if config.provider == "ollama":
            # Lightweight Ollama validation: check server and model via API
            import httpx
            
            base_url = getattr(config, 'base_url', 'http://localhost:11434')
            
            # Check if Ollama server is running
            try:
                with httpx.Client(timeout=5.0) as client:
                    response = client.get(f"{base_url}/api/tags")
                    response.raise_for_status()
                    
                    # Check if the model exists
                    models = response.json().get("models", [])
                    model_names = [m["name"] for m in models]
                    
                    if config.model_name not in model_names:
                        raise OllamaModelError(
                            f"Model '{config.model_name}' not found in Ollama. "
                            f"Available models: {', '.join(model_names[:5])}{'...' if len(model_names) > 5 else ''}. "
                            f"Run: ollama pull {config.model_name}"
                        )
                    
            except httpx.ConnectError:
                raise OllamaConnectionError(
                    f"Cannot connect to Ollama server at {base_url}. "
                    f"Please ensure Ollama is running."
                )
            except httpx.TimeoutException:
                raise ProviderTimeoutError(
                    f"Ollama server at {base_url} did not respond within 5 seconds."
                )
            except httpx.HTTPStatusError as e:
                raise EmbeddingProviderError(
                    f"Ollama server returned HTTP {e.response.status_code}: {e.response.text}"
                )
        
        else:
            # For other providers (OpenAI, Cohere, etc.), just initialize the client
            # This validates API keys and configuration without making embedding requests
            embeddings_model = ModelFactory.get_embeddings(config)
            
            # Check if the model has required attributes
            if not hasattr(embeddings_model, 'embed_query'):
                raise EmbeddingProviderError(
                    f"Embedding model for provider '{config.provider}' does not have 'embed_query' method"
                )
        
        logger.info(f"✅ Embedding provider '{config.provider}' with model '{config.model_name}' is available")
        
    except (OllamaConnectionError, OllamaModelError, ProviderAuthenticationError, ProviderTimeoutError, EmbeddingProviderError):
        # Re-raise typed exceptions as-is
        raise
    except Exception as e:
        # Wrap unexpected exceptions
        error_msg = str(e)
        
        if "authentication" in error_msg.lower() or "api key" in error_msg.lower() or "401" in error_msg:
            raise ProviderAuthenticationError(
                f"Authentication failed for embedding provider '{config.provider}': {error_msg}"
            )
        elif "timeout" in error_msg.lower():
            raise ProviderTimeoutError(
                f"Provider '{config.provider}' request timed out: {error_msg}"
            )
        else:
            raise EmbeddingProviderError(
                f"Embedding provider validation failed: {error_msg}"
            )


def validate_embedding_config(config: EmbeddingConfig) -> None:
    """
    Legacy function - delegates to validate_embedding_provider.
    Kept for backward compatibility.
    """
    validate_embedding_provider(config)
    

class BaseVectorDriver(ABC):
    @abstractmethod
    def search(self, query_vector: List[float], config: ExecutionConfig) -> List[Dict[str, Any]]:
        pass

class PostgresVectorDriver(BaseVectorDriver):
    """Driver for PostgreSQL with the pgvector extension."""
    
    _VALID_COLLECTION_RE = re.compile(r"^[a-zA-Z0-9_]+$")
    
    def search(self, query_vector: List[float], config: ExecutionConfig) -> List[Dict[str, Any]]:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            from psycopg2 import sql
        except ImportError:
            raise VectorSearchError("Install 'psycopg2-binary' to use the postgres connector.")

        if not config.collection_name or not self._VALID_COLLECTION_RE.match(config.collection_name):
            raise VectorSearchError(
                f"Invalid collection name '{config.collection_name}'. "
                f"Must match pattern: {self._VALID_COLLECTION_RE.pattern}"
            )

        conn_kwargs = {}
        if config.auth:
            conn_kwargs.update(config.auth)
            if "pass" in conn_kwargs:
                conn_kwargs["password"] = conn_kwargs.pop("pass")
        
        try:
            with psycopg2.connect(config.connection_string, **conn_kwargs) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    vector_str = "[" + ",".join(map(str, query_vector)) + "]"
                    
                    limit = config.max_results if config.max_results is not None else 100
                    
                    query = sql.SQL("""
                        SELECT * 
                        FROM {} 
                        ORDER BY embedding <=> %s::vector 
                        LIMIT %s
                    """).format(sql.Identifier(config.collection_name))
                    
                    cur.execute(query, (vector_str, limit))
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
    
    _VALID_COLLECTION_RE = re.compile(r"^[a-zA-Z0-9_]+$")
    
    def search(self, query_vector: List[float], config: ExecutionConfig) -> List[Dict[str, Any]]:
        try:
            import sqlite3
            import struct
        except ImportError:
            raise VectorSearchError("sqlite3 is not available.")

        if not config.collection_name or not self._VALID_COLLECTION_RE.match(config.collection_name):
            raise VectorSearchError(
                f"Invalid collection name '{config.collection_name}'. "
                f"Must match pattern: {self._VALID_COLLECTION_RE.pattern}"
            )

        try:
            conn = sqlite3.connect(config.connection_string)
            conn.row_factory = sqlite3.Row
            
            if hasattr(conn, 'enable_load_extension'):
                conn.enable_load_extension(True)
                self._load_vector_extension(conn, config)
                conn.enable_load_extension(False)
            else:
                raise VectorSearchError(
                    "SQLite connection does not support extension loading. "
                    "Ensure your SQLite build supports extensions (e.g., use pysqlite3)."
                )
            
            vector_bytes = struct.pack(f"{len(query_vector)}f", *query_vector)
            
            limit = config.max_results if config.max_results is not None else 100
            
            query = f"""
                SELECT *
                FROM {config.collection_name}
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT ?
            """
            
            cur = conn.cursor()
            cur.execute(query, (vector_bytes, limit))
            
            results = [dict(row) for row in cur.fetchall()]
            for r in results:
                r.pop('embedding', None)
            return results
        except Exception as e:
            raise VectorSearchError(f"SQLite Search Failed: {str(e)}")
        finally:
            if 'conn' in locals():
                conn.close()
    
    def _load_vector_extension(self, conn, config: ExecutionConfig):
        """Load the SQLite vector extension (e.g., sqlite-vec).
        
        Tries multiple strategies:
        1. sqlite_vec.load() if the sqlite-vec Python package is installed
        2. conn.load_extension() with a configurable name (default: 'vec0')
        
        Raises:
            VectorSearchError: If the extension cannot be loaded.
        """
        extension_name = "vec0"
        if config.driver_options and isinstance(config.driver_options, dict):
            extension_name = config.driver_options.get("extension_name", "vec0")
        
        try:
            import sqlite_vec
            sqlite_vec.load(conn)
            logger.info("Loaded sqlite-vec extension via sqlite_vec.load()")
            return
        except ImportError:
            logger.debug("sqlite-vec Python package not installed, trying load_extension()")
        except Exception as e:
            logger.warning(f"sqlite_vec.load() failed: {e}, trying load_extension()")
        
        try:
            conn.load_extension(extension_name)
            logger.info(f"Loaded SQLite vector extension '{extension_name}' via load_extension()")
        except Exception as e:
            raise VectorSearchError(
                f"Failed to load SQLite vector extension '{extension_name}'. "
                f"Ensure sqlite-vec is installed (pip install sqlite-vec) or the extension "
                f"file ({extension_name}.so / {extension_name}.dylib / {extension_name}.dll) "
                f"is in your SQLite extension search path. Original error: {e}"
            )

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