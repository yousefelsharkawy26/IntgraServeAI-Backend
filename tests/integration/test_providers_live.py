"""
Integration Tests: Live Provider Smoke Tests

Optional tests that exercise real LLM/Embedding provider endpoints.
These are skipped by default unless the required environment or service is available.

Coverage targets:
  - PRV-I12: Real Ollama chat completion.
  - PRV-I13: Real Groq chat completion.
  - VEC-I09: Real Ollama embedding generation.
  - VEC-I10: Real OpenAI embedding generation.

Markers: integration, slow, requires_ollama, requires_openai_key, requires_groq_key
"""

import os
import pytest

from ai_engine.providers import ModelFactory
from ai_engine.config import LLMConfig, EmbeddingConfig

pytestmark = [pytest.mark.integration, pytest.mark.slow]


class TestOllamaLive:
    """
    PRV-I12, VEC-I09: Real Ollama instance on localhost:11434.
    """

    @pytest.mark.requires_ollama
    def test_ollama_chat_completion(self):
        pytest.importorskip("langchain_ollama")
        config = LLMConfig(
            provider="ollama",
            model_name="llama3",
            location="local",
            local_loading_params={"base_url": "http://localhost:11434"}
        )
        llm = ModelFactory.get_llm(config)
        result = llm.invoke("Say hello in one word.")
        assert result.content
        assert len(result.content) > 0

    @pytest.mark.requires_ollama
    def test_ollama_embedding(self):
        pytest.importorskip("langchain_ollama")
        config = EmbeddingConfig(
            provider="ollama",
            model_name="nomic-embed-text",
            location="local",
            local_loading_params={"base_url": "http://localhost:11434"}
        )
        emb = ModelFactory.get_embeddings(config)
        vector = emb.embed_query("test query")
        assert isinstance(vector, list)
        assert len(vector) > 0
        assert all(isinstance(v, float) for v in vector)


class TestGroqLive:
    """
    PRV-I13: Real Groq API.
    """

    @pytest.mark.requires_groq_key
    def test_groq_chat_completion(self):
        pytest.importorskip("langchain_groq")
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            pytest.skip("GROQ_API_KEY not set")

        config = LLMConfig(
            provider="groq",
            model_name="llama-3.3-70b-versatile",
            location="remote",
            api_key=api_key
        )
        llm = ModelFactory.get_llm(config)
        result = llm.invoke("Say hello in one word.")
        assert result.content
        assert len(result.content) > 0


class TestOpenAILive:
    """
    VEC-I10: Real OpenAI embedding.
    """

    @pytest.mark.requires_openai_key
    def test_openai_embedding(self):
        pytest.importorskip("langchain_openai")
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        config = EmbeddingConfig(
            provider="openai",
            model_name="text-embedding-3-small",
            location="remote",
            api_key=api_key
        )
        emb = ModelFactory.get_embeddings(config)
        vector = emb.embed_query("test query")
        assert isinstance(vector, list)
        assert len(vector) > 0
