"""Translation service backends."""
from typing import Dict, Type

from .base import BaseTranslationService
from .google import GoogleTranslateService
from .deepl import DeepLService
from .openai_service import OpenAIService
from .ollama import OllamaService


# Service registry
_SERVICES: Dict[str, Type[BaseTranslationService]] = {
    'google': GoogleTranslateService,
    'deepl': DeepLService,
    'openai': OpenAIService,
    'ollama': OllamaService,
}


def get_service(name: str, **kwargs) -> BaseTranslationService:
    """Factory to create translation service by name.

    Args:
        name: Service name ('google', 'deepl', 'openai', 'ollama')
        **kwargs: Service-specific initialization parameters

    Returns:
        Initialized translation service instance

    Raises:
        ValueError: If service name is not recognized

    Examples:
        >>> # Google Translate (no API key needed)
        >>> service = get_service('google')

        >>> # DeepL with API key
        >>> service = get_service('deepl', api_key='your-key')

        >>> # OpenAI with custom model
        >>> service = get_service('openai', api_key='your-key', model='gpt-4')

        >>> # OpenAI-compatible API (e.g., local LLM)
        >>> service = get_service('openai',
        ...                       api_key='dummy',
        ...                       base_url='http://localhost:8000/v1')

        >>> # Ollama with specific model
        >>> service = get_service('ollama', model='llama2')
    """
    name_lower = name.lower()

    if name_lower not in _SERVICES:
        available = ', '.join(_SERVICES.keys())
        raise ValueError(
            f"Unknown service '{name}'. Available services: {available}"
        )

    service_class = _SERVICES[name_lower]
    return service_class(**kwargs)


def list_services() -> list:
    """List all available translation services.

    Returns:
        List of service names
    """
    return list(_SERVICES.keys())


__all__ = [
    'BaseTranslationService',
    'GoogleTranslateService',
    'DeepLService',
    'OpenAIService',
    'OllamaService',
    'get_service',
    'list_services',
]
