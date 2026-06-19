# ai_engine/providers.py

import logging
import os
from abc import ABC, abstractmethod

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.embeddings import Embeddings

from .config import LLMConfig, EmbeddingConfig

logger = logging.getLogger(__name__)


class BaseProvider(ABC):
    @abstractmethod
    def get_llm(self, config: LLMConfig) -> BaseChatModel:
        pass

    @abstractmethod
    def get_embeddings(self, config: EmbeddingConfig) -> Embeddings:
        pass

class OpenAIProvider(BaseProvider):
    def get_llm(self, config: LLMConfig) -> BaseChatModel:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=config.model_name,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            api_key=config.api_key,
        )

    def get_embeddings(self, config: EmbeddingConfig) -> Embeddings:
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model=config.model_name,
            dimensions=config.dimensions,
            api_key=config.api_key
        )

class GroqProvider(BaseProvider):
    def get_llm(self, config: LLMConfig) -> BaseChatModel:
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
        if config.local_loading_params and config.local_loading_params.base_url:
            return config.local_loading_params.base_url
        return "http://localhost:11434"

    def get_llm(self, config: LLMConfig) -> BaseChatModel:
        from langchain_ollama import ChatOllama
        base_url = self._get_base_url(config)
        return ChatOllama(
            base_url=base_url,
            model=config.model_name,
            temperature=config.temperature,
        )

    def get_embeddings(self, config: EmbeddingConfig) -> Embeddings:
        from langchain_ollama import OllamaEmbeddings
        base_url = self._get_base_url(config)
        return OllamaEmbeddings(
            base_url=base_url,
            model=config.model_name,
        )

class GoogleProvider(BaseProvider):
    def get_llm(self, config: LLMConfig) -> BaseChatModel:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=config.model_name,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            api_key=config.api_key,
        )

    def get_embeddings(self, config: EmbeddingConfig) -> Embeddings:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        return GoogleGenerativeAIEmbeddings(
            model=config.model_name,
            api_key=config.api_key
        )

class HuggingFaceProvider(BaseProvider):
    def get_llm(self, config: LLMConfig) -> BaseChatModel:
        if config.location == "local":
            from langchain_community.chat_models import ChatLlamaCpp
            from huggingface_hub import hf_hub_download
            
            gguf_file = config.local_loading_params.gguf_file
            model_path = hf_hub_download(repo_id=config.model_name, filename=gguf_file)
            
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
    _providers: dict[str, BaseProvider] = {
        "openai": OpenAIProvider,
        "ollama": OllamaProvider,
        "huggingface": HuggingFaceProvider,
        "google": GoogleProvider,
        "groq": GroqProvider,
    }

    @classmethod
    def get_llm(cls, config: LLMConfig) -> BaseChatModel:
        provider_name = config.provider.lower()
        if provider_name not in cls._providers:
            raise ValueError(
                f"Unsupported LLM Provider '{provider_name}'. "
                f"Supported: {list(cls._providers.keys())}"
            )
        
        provider_instance = cls._providers[provider_name]()
        # P2.4: Rate limiting is now handled asynchronously in AgentRunner.
        # The blocking RateLimitCallback has been removed to prevent event-loop
        # starvation during streaming.
        return provider_instance.get_llm(config)

    @classmethod
    def get_embeddings(cls, config: EmbeddingConfig) -> Embeddings:
        provider_name = config.provider.lower()
        if provider_name not in cls._providers:
            raise ValueError(
                f"Unsupported Embedding Provider '{provider_name}'. "
                f"Supported: {list(cls._providers.keys())}"
            )
        
        provider_instance = cls._providers[provider_name]()
        return provider_instance.get_embeddings(config)