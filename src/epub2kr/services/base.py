"""Abstract base class for translation services."""
from abc import ABC, abstractmethod
from typing import List


class BaseTranslationService(ABC):
    """Abstract base for all translation service providers."""

    @abstractmethod
    def translate(self, texts: List[str], source_lang: str, target_lang: str) -> List[str]:
        """Translate a batch of text segments.

        Args:
            texts: List of text strings to translate
            source_lang: Source language code (e.g., 'en', 'zh-CN')
            target_lang: Target language code (e.g., 'en', 'zh-CN')

        Returns:
            List of translated strings in the same order as input
        """
        pass

    @abstractmethod
    def name(self) -> str:
        """Return service name.

        Returns:
            String identifier for the service
        """
        pass
