# ai_engine/providers.py

import functools
import logging
import os
from abc import ABC, abstractmethod

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.embeddings import Embeddings

from .config import LLMConfig, EmbeddingConfig
from .exceptions import ProviderConfigurationError, CorrelationIdAdapter

logger = CorrelationIdAdapter(logging.getLogger(__name__))


class BaseProvider(ABC):
    @abstractmethod
    def get_llm(self, config: LLMConfig) -> BaseChatModel:
        pass

    @abstractmethod
    def get_embeddings(self, config: EmbeddingConfig) -> Embeddings:
        pass

    def _validate_llm_config(self, config: LLMConfig) -> None:
        """Validate LLM configuration before instantiation.
        
        Raises:
            ProviderConfigurationError: If model_name is missing/invalid or
                a remote API key is absent.
        """
        if not config.model_name or not isinstance(config.model_name, str):
            raise ProviderConfigurationError(
                f"model_name must be a non-empty string, got {config.model_name!r}"
            )
        if config.location == "remote" and not config.api_key:
            raise ProviderConfigurationError(
                f"API key is required for remote {self.__class__.__name__}"
            )

    def _validate_embedding_config(self, config: EmbeddingConfig) -> None:
        """Validate embedding configuration before instantiation.
        
        Raises:
            ProviderConfigurationError: If model_name is missing/invalid or
                a remote API key is absent.
        """
        if not config.model_name or not isinstance(config.model_name, str):
            raise ProviderConfigurationError(
                f"model_name must be a non-empty string, got {config.model_name!r}"
            )
        if config.location == "remote" and not config.api_key:
            raise ProviderConfigurationError(
                f"API key is required for remote {self.__class__.__name__} embeddings"
            )


class OpenAIProvider(BaseProvider):
    def get_llm(self, config: LLMConfig) -> BaseChatModel:
        self._validate_llm_config(config)
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=config.model_name,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            api_key=config.api_key,
        )

    def get_embeddings(self, config: EmbeddingConfig) -> Embeddings:
        self._validate_embedding_config(config)
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model=config.model_name,
            dimensions=config.dimensions,
            api_key=config.api_key
        )


class GroqProvider(BaseProvider):
    def get_llm(self, config: LLMConfig) -> BaseChatModel:
        self._validate_llm_config(config)
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=config.model_name,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            api_key=config.api_key,
        )

    def get_embeddings(self, config: EmbeddingConfig) -> Embeddings:
        raise NotImplementedError("Groq does not provide an embeddings endpoint yet.")


class OllamaProvider(BaseProvider):
    def _get_base_url(self, config) -> str:
        base_url = "http://localhost:11434"
        if config.local_loading_params and config.local_loading_params.base_url:
            base_url = config.local_loading_params.base_url
        
        if base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/")[:-3]
        return base_url.rstrip("/")

    def get_llm(self, config: LLMConfig) -> BaseChatModel:
        self._validate_llm_config(config)
        from langchain_ollama import ChatOllama
        base_url = self._get_base_url(config)
        return ChatOllama(
            base_url=base_url,
            model=config.model_name,
            temperature=config.temperature,
        )

    def get_embeddings(self, config: EmbeddingConfig) -> Embeddings:
        self._validate_embedding_config(config)
        from langchain_ollama import OllamaEmbeddings
        base_url = self._get_base_url(config)
        return OllamaEmbeddings(
            base_url=base_url,
            model=config.model_name,
        )


class GoogleProvider(BaseProvider):
    def get_llm(self, config: LLMConfig) -> BaseChatModel:
        self._validate_llm_config(config)
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=config.model_name,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            api_key=config.api_key,
        )

    def get_embeddings(self, config: EmbeddingConfig) -> Embeddings:
        self._validate_embedding_config(config)
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        return GoogleGenerativeAIEmbeddings(
            model=config.model_name,
            api_key=config.api_key
        )


class HuggingFaceProvider(BaseProvider):
    @staticmethod
    @functools.lru_cache(maxsize=32)
    def _cached_hf_download(repo_id: str, filename: str) -> str:
        from huggingface_hub import hf_hub_download
        return hf_hub_download(repo_id=repo_id, filename=filename)

    def get_llm(self, config: LLMConfig) -> BaseChatModel:
        self._validate_llm_config(config)
        if config.location == "local":
            from langchain_community.chat_models import ChatLlamaCpp
            if not config.local_loading_params or not config.local_loading_params.gguf_file:
                raise ProviderConfigurationError(
                    "local_loading_params.gguf_file is required for local HuggingFace LLM loading"
                )
            gguf_file = config.local_loading_params.gguf_file
            model_path = self._cached_hf_download(
                repo_id=config.model_name,
                filename=gguf_file
            )
            
            return ChatLlamaCpp(
                model_path=os.path.realpath(model_path),
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                n_ctx=config.local_loading_params.context_window,
                n_gpu_layers=config.local_loading_params.gpu_layers,
                verbose=False
            )
        else:
            from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
            llm_backend = HuggingFaceEndpoint(
                repo_id=config.model_name,
                temperature=config.temperature,
                max_new_tokens=config.max_tokens,
                huggingfacehub_api_token=config.api_key,
            )
            return ChatHuggingFace(llm=llm_backend)

    def get_embeddings(self, config: EmbeddingConfig) -> Embeddings:
        self._validate_embedding_config(config)
        if config.location == "local":
            from langchain_huggingface import HuggingFaceEmbeddings
            return HuggingFaceEmbeddings(model_name=config.model_name)
        else:
            from langchain_huggingface import HuggingFaceEndpointEmbeddings
            return HuggingFaceEndpointEmbeddings(
                model=config.model_name, 
                huggingfacehub_api_token=config.api_key
            )


class ModelFactory:
    _providers: dict[str, type[BaseProvider]] = {
        "openai": OpenAIProvider,
        "ollama": OllamaProvider,
        "huggingface": HuggingFaceProvider,
        "google": GoogleProvider,
        "groq": GroqProvider,
    }
    _instances: dict[str, BaseProvider] = {}

    @classmethod
    def _get_provider(cls, name: str) -> BaseProvider:
        if name not in cls._instances:
            cls._instances[name] = cls._providers[name]()
        return cls._instances[name]

    @classmethod
    def get_llm(cls, config: LLMConfig) -> BaseChatModel:
        provider_name = config.provider.lower()
        if provider_name not in cls._providers:
            raise ProviderConfigurationError(
                f"Unsupported LLM Provider '{provider_name}'. "
                f"Supported: {list(cls._providers.keys())}"
            )
        
        provider = cls._get_provider(config.provider.lower())
        return provider.get_llm(config)

    @classmethod
    def get_embeddings(cls, config: EmbeddingConfig) -> Embeddings:
        provider_name = config.provider.lower()
        if provider_name not in cls._providers:
            raise ProviderConfigurationError(
                f"Unsupported Embedding Provider '{provider_name}'. "
                f"Supported: {list(cls._providers.keys())}"
            )
        
        provider = cls._get_provider(config.provider.lower())
        return provider.get_embeddings(config)