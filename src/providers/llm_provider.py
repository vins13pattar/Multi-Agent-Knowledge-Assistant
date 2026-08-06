import os
import logging
from typing import Protocol, List, Dict, Any, Type, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LLMResponse(BaseModel):
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    structured_output: Optional[Any] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class LLMProvider(Protocol):
    name: str

    def generate(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.7,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> LLMResponse:
        ...


class OpenAIProvider:
    """OpenAI implementation of the LLMProvider."""

    name = "openai"

    def __init__(self):
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is not set")
        self.default_model = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4o-mini")

    def generate(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.7,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> LLMResponse:
        from langchain_openai import ChatOpenAI

        chosen_model = model or self.default_model
        llm = ChatOpenAI(model=chosen_model, temperature=temperature)

        if response_schema:
            structured_llm = llm.with_structured_output(response_schema)
            result = structured_llm.invoke(messages)
            return LLMResponse(content="", structured_output=result, provider=self.name, model=chosen_model)

        result = llm.invoke(messages)
        return LLMResponse(
            content=result.content,
            tool_calls=getattr(result, "tool_calls", None),
            provider=self.name,
            model=chosen_model,
        )


class AnthropicProvider:
    """Anthropic implementation of the LLMProvider, used as failover."""

    name = "anthropic"

    def __init__(self):
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ValueError("ANTHROPIC_API_KEY is not set")
        self.default_model = os.getenv("ANTHROPIC_DEFAULT_MODEL", "claude-3-5-haiku-20241022")

    def generate(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.7,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> LLMResponse:
        from langchain_anthropic import ChatAnthropic

        chosen_model = model or self.default_model
        llm = ChatAnthropic(model=chosen_model, temperature=temperature)

        if response_schema:
            structured_llm = llm.with_structured_output(response_schema)
            result = structured_llm.invoke(messages)
            return LLMResponse(content="", structured_output=result, provider=self.name, model=chosen_model)

        result = llm.invoke(messages)
        return LLMResponse(
            content=result.content,
            tool_calls=getattr(result, "tool_calls", None),
            provider=self.name,
            model=chosen_model,
        )


_PROVIDER_REGISTRY = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}


def get_llm_provider(provider_name: str = "openai") -> LLMProvider:
    """Factory to get a single named provider (no failover)."""
    key = provider_name.lower()
    if key not in _PROVIDER_REGISTRY:
        raise ValueError(f"Provider {provider_name} not implemented yet.")
    return _PROVIDER_REGISTRY[key]()


class FailoverLLMProvider:
    """Wraps an ordered list of providers, trying each in turn on failure."""

    name = "failover"

    def __init__(self, provider_names: List[str]):
        self.provider_names = provider_names

    def generate(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.7,
        response_schema: Optional[Type[BaseModel]] = None,
    ) -> LLMResponse:
        last_error: Optional[Exception] = None
        for provider_name in self.provider_names:
            try:
                provider = get_llm_provider(provider_name)
            except Exception as e:
                logger.warning("Skipping provider %s (not configured): %s", provider_name, e)
                last_error = e
                continue
            try:
                return provider.generate(
                    messages=messages,
                    model=model if provider_name == self.provider_names[0] else None,
                    temperature=temperature,
                    response_schema=response_schema,
                )
            except Exception as e:
                logger.warning("Provider %s failed, trying next: %s", provider_name, e)
                last_error = e
                continue
        raise RuntimeError(
            f"All LLM providers failed or unconfigured ({self.provider_names}): {last_error}"
        )


def get_default_llm_provider() -> LLMProvider:
    """
    Returns a failover-capable provider built from env config.
    PRIMARY_LLM_PROVIDER / FALLBACK_LLM_PROVIDER control order (default openai -> anthropic).
    """
    primary = os.getenv("PRIMARY_LLM_PROVIDER", "openai")
    fallback = os.getenv("FALLBACK_LLM_PROVIDER", "anthropic")
    order = [p for p in [primary, fallback] if p]
    # de-dupe, preserve order
    seen = set()
    ordered = [p for p in order if not (p in seen or seen.add(p))]
    return FailoverLLMProvider(ordered)
