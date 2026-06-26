"""Phase 1 — Unit tests for ai_engine.providers (mocked, no external API calls).

Validates provider configuration, factory behaviour, and Ollama URL normalisation.
"""

from unittest.mock import patch

import pytest

from ai_engine.providers import (
    OpenAIProvider,
    GroqProvider,
    OllamaProvider,
    GoogleProvider,
    HuggingFaceProvider,
    ModelFactory,
)
from ai_engine.config import LLMConfig, EmbeddingConfig
from utils.exceptions import ProviderConfigurationError


@pytest.mark.unit
class TestOpenAIProvider:
    """ChatOpenAI and OpenAIEmbeddings instantiation paths."""

    @patch("langchain_openai.ChatOpenAI")
    def test_get_llm(self, mock_chat, ):
        config = LLMConfig(
            provider="openai",
            model_name="gpt-4",
            temperature=0.5,
            max_tokens=1024,
            api_key="sk-test"
        )
        provider = OpenAIProvider()
        provider.get_llm(config)
        mock_chat.assert_called_once_with(
            model="gpt-4",
            temperature=0.5,
            max_tokens=1024,
            api_key="sk-test"
        )

    @patch("langchain_openai.OpenAIEmbeddings")
    def test_get_embeddings(self, mock_emb, ):
        config = EmbeddingConfig(
            provider="openai",
            model_name="text-embedding-3-small",
            dimensions=1536,
            api_key="sk-test"
        )
        provider = OpenAIProvider()
        provider.get_embeddings(config)
        mock_emb.assert_called_once_with(
            model="text-embedding-3-small",
            dimensions=1536,
            api_key="sk-test"
        )

    def test_missing_model_name(self):
        config = LLMConfig(provider="openai", model_name="")
        provider = OpenAIProvider()
        with pytest.raises(ProviderConfigurationError) as exc_info:
            provider.get_llm(config)
        assert "model_name" in str(exc_info.value)

    def test_missing_api_key_for_remote(self):
        config = LLMConfig(provider="openai", model_name="gpt-4", location="remote")
        provider = OpenAIProvider()
        with pytest.raises(ProviderConfigurationError) as exc_info:
            provider.get_llm(config)
        assert "API key" in str(exc_info.value)

    def test_local_does_not_require_api_key(self):
        config = LLMConfig(provider="openai", model_name="gpt-4", location="local")
        provider = OpenAIProvider()
        with patch("langchain_openai.ChatOpenAI"):
            provider.get_llm(config)


@pytest.mark.unit
class TestGroqProvider:
    """Groq LLM support and explicit embedding absence."""

    @patch("langchain_groq.ChatGroq")
    def test_get_llm(self, mock_chat, ):
        config = LLMConfig(
            provider="groq",
            model_name="llama-3-70b",
            api_key="gsk-test"
        )
        provider = GroqProvider()
        provider.get_llm(config)
        mock_chat.assert_called_once_with(
            model="llama-3-70b",
            temperature=0.7,
            max_tokens=2048,
            api_key="gsk-test"
        )

    def test_embeddings_not_implemented(self):
        config = EmbeddingConfig(provider="groq", model_name="x")
        provider = GroqProvider()
        with pytest.raises(NotImplementedError) as exc_info:
            provider.get_embeddings(config)
        assert "Groq" in str(exc_info.value)

    def test_missing_api_key(self):
        config = LLMConfig(provider="groq", model_name="llama-3-70b", location="remote")
        provider = GroqProvider()
        with pytest.raises(ProviderConfigurationError):
            provider.get_llm(config)


@pytest.mark.unit
class TestOllamaProvider:
    """Ollama base-URL normalisation and ChatOllama instantiation."""

    def test_strip_v1_suffix(self):
        config = LLMConfig(
            provider="ollama",
            model_name="llama3",
            local_loading_params={"base_url": "http://localhost:11434/v1"}
        )
        provider = OllamaProvider()
        url = provider._get_base_url(config)
        assert url == "http://localhost:11434"

    def test_strip_v1_suffix_with_trailing_slash(self):
        config = LLMConfig(
            provider="ollama",
            model_name="llama3",
            local_loading_params={"base_url": "http://localhost:11434/v1/"}
        )
        provider = OllamaProvider()
        url = provider._get_base_url(config)
        assert url == "http://localhost:11434"

    def test_no_strip_needed(self):
        config = LLMConfig(
            provider="ollama",
            model_name="llama3",
            local_loading_params={"base_url": "http://localhost:11434"}
        )
        provider = OllamaProvider()
        url = provider._get_base_url(config)
        assert url == "http://localhost:11434"

    def test_no_local_params_uses_default(self):
        config = LLMConfig(provider="ollama", model_name="llama3")
        provider = OllamaProvider()
        url = provider._get_base_url(config)
        assert url == "http://localhost:11434"

    @patch("langchain_ollama.ChatOllama")
    def test_get_llm(self, mock_chat, ):
        config = LLMConfig(
            location="local",
            provider="ollama",
            model_name="llama3",
            local_loading_params={"base_url": "http://localhost:11434"}
        )
        provider = OllamaProvider()
        provider.get_llm(config)
        mock_chat.assert_called_once_with(
            base_url="http://localhost:11434",
            model="llama3",
            temperature=0.7
        )

    @patch("langchain_ollama.OllamaEmbeddings")
    def test_get_embeddings(self, mock_emb, ):
        config = EmbeddingConfig(
            location="local",
            provider="ollama",
            model_name="nomic-embed-text",
            local_loading_params={"base_url": "http://localhost:11434"}
        )
        provider = OllamaProvider()
        provider.get_embeddings(config)
        mock_emb.assert_called_once_with(
            base_url="http://localhost:11434",
            model="nomic-embed-text"
        )

    def test_missing_model_name(self):
        config = LLMConfig(provider="ollama", model_name="")
        provider = OllamaProvider()
        with pytest.raises(ProviderConfigurationError):
            provider.get_llm(config)


@pytest.mark.unit
class TestGoogleProvider:
    """Google Generative AI provider instantiation."""

    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    def test_get_llm(self, mock_chat, ):
        config = LLMConfig(
            provider="google",
            model_name="gemini-pro",
            api_key="test-key"
        )
        provider = GoogleProvider()
        provider.get_llm(config)
        mock_chat.assert_called_once_with(
            model="gemini-pro",
            temperature=0.7,
            max_tokens=2048,
            api_key="test-key"
        )

    @patch("langchain_google_genai.GoogleGenerativeAIEmbeddings")
    def test_get_embeddings(self, mock_emb, ):
        config = EmbeddingConfig(
            provider="google",
            model_name="embedding-001",
            api_key="test-key"
        )
        provider = GoogleProvider()
        provider.get_embeddings(config)
        mock_emb.assert_called_once_with(
            model="embedding-001",
            api_key="test-key"
        )

    def test_missing_api_key(self):
        config = LLMConfig(provider="google", model_name="gemini-pro", location="remote")
        provider = GoogleProvider()
        with pytest.raises(ProviderConfigurationError):
            provider.get_llm(config)


@pytest.mark.unit
class TestHuggingFaceProvider:
    """HuggingFace local (GGUF) and remote (endpoint) paths."""

    @patch("huggingface_hub.hf_hub_download")
    @patch("langchain_community.chat_models.ChatLlamaCpp")
    def test_local_llm(self, mock_llm, mock_download, ):
        mock_download.return_value = "/path/to/model.gguf"
        config = LLMConfig(
            provider="huggingface",
            model_name="TheBloke/Llama-2-7B-GGUF",
            location="local",
            local_loading_params={
                "gguf_file": "model.gguf",
                "context_window": 4096,
                "gpu_layers": 0
            }
        )
        provider = HuggingFaceProvider()
        provider.get_llm(config)
        mock_download.assert_called_once_with(
            repo_id="TheBloke/Llama-2-7B-GGUF",
            filename="model.gguf"
        )
        mock_llm.assert_called_once()
        call_kwargs = mock_llm.call_args.kwargs
        assert call_kwargs["model_path"] == "/path/to/model.gguf"
        assert call_kwargs["n_ctx"] == 4096
        assert call_kwargs["n_gpu_layers"] == 0

    def test_local_llm_missing_gguf(self):
        config = LLMConfig(
            provider="huggingface",
            model_name="test",
            location="local",
            local_loading_params=None
        )
        provider = HuggingFaceProvider()
        with pytest.raises(ProviderConfigurationError) as exc_info:
            provider.get_llm(config)
        assert "gguf_file" in str(exc_info.value)

    @patch("langchain_huggingface.HuggingFaceEndpoint")
    @patch("langchain_huggingface.ChatHuggingFace")
    def test_remote_llm(self, mock_chat_hf, mock_endpoint, ):
        config = LLMConfig(
            provider="huggingface",
            model_name="meta-llama/Llama-2-7b",
            location="remote",
            api_key="hf-test"
        )
        provider = HuggingFaceProvider()
        provider.get_llm(config)
        mock_endpoint.assert_called_once()
        mock_chat_hf.assert_called_once()

    @patch("langchain_huggingface.HuggingFaceEmbeddings")
    def test_local_embeddings(self, mock_emb, ):
        config = EmbeddingConfig(
            provider="huggingface",
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            location="local"
        )
        provider = HuggingFaceProvider()
        provider.get_embeddings(config)
        mock_emb.assert_called_once_with(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

    @patch("langchain_huggingface.HuggingFaceEndpointEmbeddings")
    def test_remote_embeddings(self, mock_emb, ):
        config = EmbeddingConfig(
            provider="huggingface",
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            location="remote",
            api_key="hf-test"
        )
        provider = HuggingFaceProvider()
        provider.get_embeddings(config)
        mock_emb.assert_called_once()

    def test_cache_hit(self):
        provider = HuggingFaceProvider()
        with patch("huggingface_hub.hf_hub_download") as mock_dl:
            mock_dl.return_value = "/path/to/model.gguf"
            provider._cached_hf_download("repo", "file.gguf")
            assert mock_dl.call_count == 1
            # Second call should hit LRU cache
            provider._cached_hf_download("repo", "file.gguf")
            assert mock_dl.call_count == 1


@pytest.mark.unit
class TestModelFactory:
    """Factory dispatch, validation, and caching behaviour."""

    def test_unsupported_llm_provider(self):
        config = LLMConfig(provider="anthropic", model_name="claude")
        with pytest.raises(ProviderConfigurationError) as exc_info:
            ModelFactory.get_llm(config)
        assert "anthropic" in str(exc_info.value)

    def test_unsupported_embedding_provider(self):
        config = EmbeddingConfig(provider="anthropic", model_name="claude")
        with pytest.raises(ProviderConfigurationError) as exc_info:
            ModelFactory.get_embeddings(config)
        assert "anthropic" in str(exc_info.value)

    def test_missing_model_name(self):
        config = LLMConfig(provider="openai", model_name="")
        with pytest.raises(ProviderConfigurationError):
            ModelFactory.get_llm(config)

    @patch("langchain_openai.ChatOpenAI")
    def test_provider_caching(self, mock_chat, ):
        if hasattr(ModelFactory, '_instances'):
            ModelFactory._instances.clear()

        config = LLMConfig(provider="openai", model_name="gpt-4", api_key="test")
        ModelFactory.get_llm(config)

        if hasattr(ModelFactory, '_instances'):
            first = ModelFactory._instances.get("openai")
            ModelFactory.get_llm(config)
            second = ModelFactory._instances.get("openai")
            assert first is second
        else:
            pytest.skip("Provider caching not yet implemented in ModelFactory")

    @patch("langchain_openai.ChatOpenAI")
    def test_case_insensitive_provider(self, mock_chat, ):
        config = LLMConfig(provider="OpenAI", model_name="gpt-4", api_key="test")
        ModelFactory.get_llm(config)
        mock_chat.assert_called_once()
