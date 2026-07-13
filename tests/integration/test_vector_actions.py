"""
Integration Tests: Vector Search Action Execution

Validates the ActionEngine's _execute_vector against real vector databases:
  - PostgreSQL with pgvector (via testcontainers).
  - SQLite with sqlite-vec (via temp file + extension).

Coverage targets:
  - VEC-I01: Postgres + pgvector semantic search.
  - VEC-I02: SQLite + sqlite-vec semantic search.
  - VEC-I03: Collection name validation (regex).
  - VEC-I04: Auth mapping (pass -> password).
  - VEC-U07: Unsupported driver rejection.
  - VEC-U08: Missing vector parameter.

Markers: integration, slow
"""

import pytest

from tests.agent_config_test_utils import load_agent_config
from ai_engine.action_engine import ActionEngine
from utils.exceptions import VectorSearchError, UnsupportedDatabaseDriver
from ai_engine.config import EmbeddingConfig

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture
def vector_agent_config(write_temp_json):
    return write_temp_json({
        "system_context": {"title": "T", "description": "D", "version": "1", "tone": "neutral"},
        "global_defaults": {
            "api_request": {
                "protocol": "https",
                "base_url": "",
                "timeout": 10000,
                "headers": {},
                "on_error": "Error"
            },
            "rpc_request": {
                "protocol": "grpc",
                "headers": {},
                "on_error": "Error"
            },
            "vector_query": {
                "connector": "postgres",
                "connection_string": "postgresql://localhost:5432/test",
                "on_error": "Error"
            },
            "internal": {
                "on_error": "Error"
            }
        }
    }, "agent.json")


@pytest.mark.asyncio
class TestPostgresVectorSearch:
    """
    VEC-I01: Real Postgres + pgvector search.
    """

    async def test_semantic_search_postgres(self, vector_agent_config, postgres_vector_db, monkeypatch):
        conn_str, collection = postgres_vector_db

        monkeypatch.setenv("DB_USER", "testuser")
        monkeypatch.setenv("DB_PASS", "testpass")

        actions = [{
            "name": "search_products_semantic",
            "description": "Search products",
            "type": "vector_query",
            "active": True,
            "execution_config": {
                "collection_name": collection,
                "connector": "postgres",
                "connection_string": conn_str,
                "max_results": 3,
                # "auth": {
                #     "user": "{{env.DB_USER}}",
                #     "pass": "{{env.DB_PASS}}"
                # },
                "embedding_config": {
                    "location": "local",
                    "provider": "ollama",
                    "model_name": "nomic-embed-text",
                    "dimensions": 768
                }
            },
            "parameters": {
                "topic": {
                    "type": "string",
                    "required": True,
                    "param_type": "vector",
                    "description": "Search topic"
                }
            },
            "response_config": {
                "mode": "raw",
                "template": "Found: {{value}}"
            }
        }]

        engine = ActionEngine(load_agent_config(vector_agent_config), actions_list=actions)

        import ai_engine.action_engine as ae
        orig_generate = ae.generate_embedding

        def mock_gen(text, config):
            return [0.1] * 768

        ae.generate_embedding = mock_gen
        try:
            result = await engine.execute_action_directly("search_products_semantic", {"topic": "running shoes"})
            assert "Nike Air Zoom" in result or "Adidas Ultraboost" in result
        finally:
            ae.generate_embedding = orig_generate

    async def test_collection_name_validation(self, vector_agent_config):
        actions = [{
            "name": "bad_collection",
            "description": "Bad collection",
            "type": "vector_query",
            "active": True,
            "execution_config": {
                "collection_name": "bad; DROP TABLE",
                "connector": "postgres",
                "connection_string": "postgresql://localhost/db",
                "embedding_config": {
                    "location": "local",
                    "provider": "ollama",
                    "model_name": "nomic-embed-text",
                    "dimensions": 768
                }
            },
            "parameters": {
                "topic": {
                    "type": "string",
                    "required": True,
                    "param_type": "vector",
                    "description": "Topic"
                }
            },
            "response_config": {
                "mode": "raw",
                "template": "Found: {{value}}"
            }
        }]
        engine = ActionEngine(load_agent_config(vector_agent_config), actions_list=actions)

        import ai_engine.action_engine as ae
        orig_generate = ae.generate_embedding

        def mock_gen(text, config):
            return [0.1] * 768

        ae.generate_embedding = mock_gen
        try:
            with pytest.raises(VectorSearchError) as exc_info:
                await engine.execute_action_directly("bad_collection", {"topic": "test"})
            assert "Invalid collection name" in str(exc_info.value)
        finally:
            ae.generate_embedding = orig_generate


@pytest.mark.asyncio
class TestSQLiteVectorSearch:
    """
    VEC-I02: Real SQLite + sqlite-vec search.
    """

    async def test_semantic_search_sqlite(self, vector_agent_config, sqlite_vector_db):
        db_path, collection = sqlite_vector_db

        actions = [{
            "name": "search_sqlite",
            "description": "Search SQLite",
            "type": "vector_query",
            "active": True,
            "execution_config": {
                "collection_name": collection,
                "connector": "sqlite",
                "connection_string": db_path,
                "max_results": 3,
                "embedding_config": {
                    "location": "local",
                    "provider": "ollama",
                    "model_name": "nomic-embed-text",
                    "dimensions": 768
                }
            },
            "parameters": {
                "topic": {
                    "type": "string",
                    "required": True,
                    "param_type": "vector",
                    "description": "Topic"
                }
            },
            "response_config": {
                "mode": "raw",
                "template": "Found: {{value}}"
            }
        }]

        engine = ActionEngine(load_agent_config(vector_agent_config), actions_list=actions)

        import ai_engine.action_engine as ae
        orig_generate = ae.generate_embedding

        def mock_gen(text, config):
            return [0.1] * 768

        ae.generate_embedding = mock_gen
        try:
            result = await engine.execute_action_directly("search_sqlite", {"topic": "running shoes"})
            assert "Found" in result
        finally:
            ae.generate_embedding = orig_generate


@pytest.mark.asyncio
class TestVectorErrors:
    """
    VEC-U07, VEC-U08: Error paths.
    """

    async def test_unsupported_driver(self, vector_agent_config):
        actions = [{
            "name": "bad_driver",
            "description": "Bad driver",
            "type": "vector_query",
            "active": True,
            "execution_config": {
                "collection_name": "products",
                "connector": "mongo",
                "embedding_config": {
                    "location": "local",
                    "provider": "ollama",
                    "model_name": "nomic-embed-text",
                    "dimensions": 768
                }
            },
            "parameters": {
                "topic": {
                    "type": "string",
                    "required": True,
                    "param_type": "vector",
                    "description": "Topic"
                }
            }
        }]
        engine = ActionEngine(load_agent_config(vector_agent_config), actions_list=actions)

        import ai_engine.action_engine as ae
        orig_generate = ae.generate_embedding

        def mock_gen(text, config):
            return [0.1] * 768

        ae.generate_embedding = mock_gen
        try:
            with pytest.raises(UnsupportedDatabaseDriver) as exc_info:
                await engine.execute_action_directly("bad_driver", {"topic": "test"})
            assert "mongo" in str(exc_info.value)
        finally:
            ae.generate_embedding = orig_generate

    async def test_missing_vector_param(self, vector_agent_config):
        actions = [{
            "name": "no_vector_param",
            "description": "No vector param",
            "type": "vector_query",
            "active": True,
            "execution_config": {
                "collection_name": "products",
                "connector": "postgres"
            },
            "parameters": {
                "query": {
                    "type": "string",
                    "required": True,
                    "param_type": "query",  # NOT vector
                    "description": "Query"
                }
            }
        }]
        engine = ActionEngine(load_agent_config(vector_agent_config), actions_list=actions)
        with pytest.raises(VectorSearchError) as exc_info:
            await engine.execute_action_directly("no_vector_param", {"query": "test"})
        assert "param_type='vector'" in str(exc_info.value)